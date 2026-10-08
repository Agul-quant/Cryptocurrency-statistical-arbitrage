"""Causal, bounded extension signals; no data loading or evaluation occurs here.

The price grid and audited suspension policy are inherited from the frozen
course backtest. Only targets carry forward. Cross-sectional buffers skip a
whole rebalance, preserving neutrality. Trend portfolios keep a fixed 1/8
allocation per coin. Factor signals trade a *price-level* BTC-hedged spread,
never a cumulative, demeaned return-residual bridge.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.stattools import adfuller

from crypto_stat_arb.backtest import _halt_bridges, _validate_prices

from .core import get_scaled_generator


SCHEDULE_EPOCH = pd.Timestamp("2022-01-03 00:00:00", tz="UTC")
FACTOR_PARAMETERS = {
    "benchmark": "BTCUSDT", "formation_days": 90, "beta_days": 30,
    "calibration_days": 60, "formation_lag_days": 1,
    "beta_min": 0.1, "beta_max": 5.0, "sigma_min": 1e-8,
    "adf_regression": "c", "adf_maxlag": 3, "adf_autolag": "AIC",
    "holm_alpha": 0.05, "half_life_min_days": 1.0, "half_life_max_days": 20.0,
    "entry_z": 2.0, "exit_z": 0.5, "stop_z": 4.0, "max_holding_days": 20,
    "monthly_reset_to_cash": True, "same_day_reentry": False,
}
MODEL_COLUMNS = [
    "refit_time", "symbol", "formation_price_start", "fit_start", "fit_end",
    "calibration_start", "calibration_end", "beta", "alpha_daily_log_return",
    "mu", "sigma", "adf_pvalue", "adf_pvalue_holm", "phi", "half_life_days",
    "eligible", "reason",
]
EVENT_COLUMNS = ["decision_time", "symbol", "event", "z", "side", "prior_side",
                 "holding_days", "model_refit_time"]


@dataclass(frozen=True)
class FactorResult:
    targets: pd.DataFrame
    models: pd.DataFrame
    events: pd.DataFrame


def candidate_grid() -> list[dict]:
    """The predeclared 8 cross-sectional, 8 own-trend, and 1 factor specs."""
    result = []
    for family in ("cross_momentum", "trend_long_cash", "trend_long_short"):
        for lookback in (336, 672):
            for cadence in (24, 168):
                for buffer in ((0.0, 0.25) if family == "cross_momentum" else (0.0,)):
                    result.append({
                        "strategy_id": f"{family}_h{lookback:03d}_r{cadence:03d}_b{round(buffer * 100):03d}",
                        "family": family, "lookback_h": lookback,
                        "rebalance_h": cadence, "buffer_l1": buffer,
                    })
    result.append({"strategy_id": "factor_residual_fixed", "family": "factor_residual",
                   "lookback_h": 0, "rebalance_h": 24, "buffer_l1": 0.0})
    return result


def _validate_universe(prices: pd.DataFrame, *, factor: bool = False) -> None:
    _validate_prices(prices)
    if len(prices.columns) != 8:
        raise ValueError("Extension strategies require the fixed eight-asset universe.")
    if factor and "BTCUSDT" not in prices.columns:
        raise ValueError("The factor strategy requires BTCUSDT as its tradable hedge.")


def _halt_interior(index: pd.DatetimeIndex, bridges) -> np.ndarray:
    interior = np.zeros(len(index), dtype=bool)
    for start, end in bridges:
        interior |= (index > start) & (index < end)
    return interior


def _scheduled(index: pd.DatetimeIndex, cadence: int) -> np.ndarray:
    hours = ((index - SCHEDULE_EPOCH) / pd.Timedelta(hours=1)).to_numpy(dtype=np.int64)
    return hours % cadence == 0


def generate_targets(prices: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Generate nonfactor targets on midnight / Monday-midnight schedules.

    In a buffered cross-sectional candidate, a proposed *whole target* is
    adopted only if its full-L1 distance from the current target is at least
    0.25 (with 1e-12 floating tolerance). All-tie scores are genuinely flat.
    A halt-interior current or lookback endpoint defers the decision, even if
    the archive contains a partial-bar price at that endpoint.
    """
    _validate_universe(prices)
    family = spec.get("family")
    if family not in ("cross_momentum", "trend_long_cash", "trend_long_short"):
        raise ValueError("Use generate_factor_targets for the factor family.")
    lookback, cadence, buffer = spec.get("lookback_h"), spec.get("rebalance_h"), spec.get("buffer_l1", 0.0)
    if isinstance(lookback, bool) or lookback not in (336, 672):
        raise ValueError("Predeclared lookback_h must be 336 or 672.")
    if isinstance(cadence, bool) or cadence not in (24, 168):
        raise ValueError("Predeclared rebalance_h must be 24 or 168.")
    if isinstance(buffer, bool) or buffer not in (0.0, 0.25):
        raise ValueError("buffer_l1 must be 0 or 0.25.")
    if family != "cross_momentum" and buffer != 0:
        raise ValueError("Own-trend candidates do not include a rank-turnover buffer.")
    numeric = prices.astype(float)
    score = numeric.div(numeric.shift(int(lookback))) - 1.0
    bridges = _halt_bridges(prices)
    decisions = _scheduled(prices.index, int(cadence))
    decisions &= np.isfinite(score.to_numpy()).all(axis=1)
    decisions &= ~_halt_interior(prices.index, bridges)
    decisions &= ~_halt_interior(prices.index - pd.Timedelta(hours=int(lookback)), bridges)
    if family == "cross_momentum":
        # Reuse the already audited genuine elapsed-time rank generator.
        proposed = get_scaled_generator()(prices, "momentum", int(lookback), int(cadence))
    elif family == "trend_long_cash":
        proposed = score.gt(0).astype(float) / 8.0
    else:
        proposed = np.sign(score) / 8.0
    updates = np.full(prices.shape, np.nan, dtype=float)
    current = np.zeros(8, dtype=float)
    values = proposed.to_numpy(dtype=float)
    for position in np.flatnonzero(decisions):
        target = values[position]
        if float(np.abs(target - current).sum()) + 1e-12 >= float(buffer):
            current = target.copy()
            updates[position] = current
    targets = pd.DataFrame(updates, index=prices.index, columns=prices.columns).ffill().fillna(0.0)
    targets.index.name = prices.index.name
    targets.attrs = dict(prices.attrs)
    return targets


def _model_template(refit_time: pd.Timestamp, symbol: str) -> dict:
    p = FACTOR_PARAMETERS
    price_start = refit_time - pd.Timedelta(days=p["formation_days"] + p["formation_lag_days"])
    fit_start = price_start + pd.Timedelta(days=1)
    fit_end = fit_start + pd.Timedelta(days=p["beta_days"] - 1)
    return {
        "refit_time": refit_time, "symbol": symbol,
        "formation_price_start": price_start, "fit_start": fit_start, "fit_end": fit_end,
        "calibration_start": fit_end + pd.Timedelta(days=1),
        "calibration_end": refit_time - pd.Timedelta(days=p["formation_lag_days"]),
        "beta": np.nan, "alpha_daily_log_return": np.nan,
        "mu": np.nan, "sigma": np.nan, "adf_pvalue": 1.0,
        "adf_pvalue_holm": 1.0, "phi": np.nan, "half_life_days": np.nan,
        "eligible": False, "reason": "",
    }


def _fit_month_models(daily: pd.DataFrame, refit_time: pd.Timestamp, symbols: list[str], bridges) -> list[dict]:
    """Fit beta on 30 returns, then screen a disjoint 60-endpoint level spread.

    The initial 91 prices generate exactly 90 daily log-return observations.
    Beta's return endpoints end t-61d; spread calibration begins t-60d.
    All seven pairs participate in Holm correction, including failed models
    represented by p=1. ADF is pinned: constant, maxlag=3, autolag='AIC'.
    """
    p = FACTOR_PARAMETERS
    desired = pd.date_range(refit_time - pd.Timedelta(days=p["formation_days"] + p["formation_lag_days"]),
                            refit_time - pd.Timedelta(days=p["formation_lag_days"]), freq="D", tz="UTC")
    formation = daily.reindex(desired)
    models = []
    for symbol in symbols:
        model = _model_template(refit_time, symbol)
        pair = formation[[symbol, "BTCUSDT"]]
        values = pair.to_numpy(dtype=float)
        failures = []
        if not np.isfinite(values).all() or _halt_interior(desired, bridges).any():
            model["reason"] = "insufficient_or_unobserved_formation"
            models.append(model)
            continue
        logged = np.log(values)
        returns = np.diff(logged, axis=0)
        y, market = returns[:p["beta_days"], 0], returns[:p["beta_days"], 1]
        if float(np.std(market, ddof=1)) <= 1e-12:
            model["reason"] = "constant_market_factor"
            models.append(model)
            continue
        alpha, beta = np.linalg.lstsq(np.column_stack([np.ones(p["beta_days"]), market]), y, rcond=None)[0]
        model["beta"], model["alpha_daily_log_return"] = float(beta), float(alpha)
        if not np.isfinite(beta) or not p["beta_min"] <= beta <= p["beta_max"]:
            failures.append("beta_out_of_bounds")
        spread = logged[-p["calibration_days"]:, 0] - beta * logged[-p["calibration_days"]:, 1]
        mu, sigma = float(spread.mean()), float(spread.std(ddof=1))
        model["mu"], model["sigma"] = mu, sigma
        if not np.isfinite(sigma) or sigma <= p["sigma_min"]:
            failures.append("spread_scale_too_small")
        else:
            try:
                pvalue = float(adfuller(spread, maxlag=p["adf_maxlag"], regression=p["adf_regression"],
                                       autolag=p["adf_autolag"])[1])
                if np.isfinite(pvalue) and 0 <= pvalue <= 1:
                    model["adf_pvalue"] = pvalue
                else:
                    failures.append("adf_failed")
            except (ValueError, np.linalg.LinAlgError):
                failures.append("adf_failed")
            _, phi = np.linalg.lstsq(np.column_stack([np.ones(len(spread) - 1), spread[:-1]]), spread[1:], rcond=None)[0]
            model["phi"] = float(phi)
            if np.isfinite(phi) and 0 < phi < 1:
                half_life = float(np.log(0.5) / np.log(phi))
                model["half_life_days"] = half_life
                if not p["half_life_min_days"] <= half_life <= p["half_life_max_days"]:
                    failures.append("half_life_out_of_bounds")
            else:
                failures.append("non_mean_reverting_ar1")
        model["reason"] = ";".join(failures)
        models.append(model)
    _, adjusted, _, _ = multipletests([m["adf_pvalue"] for m in models], alpha=p["holm_alpha"], method="holm")
    for model, pvalue in zip(models, adjusted):
        model["adf_pvalue_holm"] = float(pvalue)
        reasons = [r for r in model["reason"].split(";") if r]
        if pvalue > p["holm_alpha"]:
            reasons.append("adf_holm_not_rejected")
        model["eligible"] = not reasons
        model["reason"] = ";".join(reasons) if reasons else "eligible"
    return models


def generate_factor_targets(prices: pd.DataFrame) -> FactorResult:
    """Monthly fixed BTC-factor level-spread model with daily causal decisions.

    Long/short side denotes the *alt-minus-beta-BTC spread*. Each coin has a
    fixed 1/7 budget, never active-pair rescaling; BTC hedges are aggregated
    into the actual asset target before turnover/cost calculation. All-cash
    months are valid. The monthly refit day is always cash; daily entries start
    the next day. No exit can flip/reenter on the same decision.
    """
    _validate_universe(prices, factor=True)
    symbols = [s for s in prices.columns if s != "BTCUSDT"]
    daily = prices.loc[prices.index.hour == 0].astype(float)
    bridges = _halt_bridges(prices)
    state = {s: {"side": 0, "entry_time": None} for s in symbols}
    active_models = {}
    model_records, events = [], []
    updates = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)

    def emit(time, symbol, event, z=np.nan, prior_side=0, age=0):
        events.append({"decision_time": time, "symbol": symbol, "event": event,
                       "z": float(z), "side": state[symbol]["side"], "prior_side": prior_side,
                       "holding_days": age,
                       "model_refit_time": active_models.get(symbol, {}).get("refit_time", pd.NaT)})

    for time, row in daily.iterrows():
        if time.day == 1:
            for symbol in symbols:
                prior = state[symbol]["side"]
                age = int((time - state[symbol]["entry_time"]) / pd.Timedelta(days=1)) if prior else 0
                state[symbol] = {"side": 0, "entry_time": None}
                if prior:
                    emit(time, symbol, "monthly_exit", prior_side=prior, age=age)
            fitted = _fit_month_models(daily, time, symbols, bridges)
            model_records.extend(fitted)
            active_models = {m["symbol"]: m for m in fitted}
            for symbol in symbols:
                emit(time, symbol, "monthly_refit_cash")
        else:
            for symbol in symbols:
                model = active_models.get(symbol)
                if model is None or not model["eligible"]:
                    continue
                if (_halt_interior(pd.DatetimeIndex([time]), bridges).any()
                        or not np.isfinite([row[symbol], row["BTCUSDT"]]).all()):
                    emit(time, symbol, "decision_deferred", prior_side=state[symbol]["side"])
                    continue
                z = (np.log(row[symbol]) - model["beta"] * np.log(row["BTCUSDT"]) - model["mu"]) / model["sigma"]
                if not np.isfinite(z):
                    emit(time, symbol, "decision_deferred", prior_side=state[symbol]["side"])
                    continue
                side = state[symbol]["side"]
                if side:
                    age = int((time - state[symbol]["entry_time"]) / pd.Timedelta(days=1))
                    exit_reason = ("adverse_stop" if side * z <= -FACTOR_PARAMETERS["stop_z"] else
                                   "max_holding_exit" if age >= FACTOR_PARAMETERS["max_holding_days"] else
                                   "mean_reversion_exit" if side * z >= -FACTOR_PARAMETERS["exit_z"] else None)
                    if exit_reason:
                        state[symbol] = {"side": 0, "entry_time": None}
                        emit(time, symbol, exit_reason, z, prior_side=side, age=age)
                elif FACTOR_PARAMETERS["entry_z"] <= abs(z) < FACTOR_PARAMETERS["stop_z"]:
                    state[symbol] = {"side": -int(np.sign(z)), "entry_time": time}
                    emit(time, symbol, "entry", z)
                elif abs(z) >= FACTOR_PARAMETERS["stop_z"]:
                    emit(time, symbol, "entry_skipped_extreme", z)
        weights = pd.Series(0.0, index=prices.columns)
        for symbol in symbols:
            side = state[symbol]["side"]
            if side:
                beta = active_models[symbol]["beta"]
                alt_weight = side / (7.0 * (1.0 + abs(beta)))
                weights[symbol] = alt_weight
                weights["BTCUSDT"] -= beta * alt_weight
        updates.loc[time] = weights
    targets = updates.ffill().fillna(0.0)
    targets.index.name = prices.index.name
    targets.attrs = dict(prices.attrs)
    return FactorResult(targets=targets, models=pd.DataFrame(model_records, columns=MODEL_COLUMNS),
                        events=pd.DataFrame(events, columns=EVENT_COLUMNS))
