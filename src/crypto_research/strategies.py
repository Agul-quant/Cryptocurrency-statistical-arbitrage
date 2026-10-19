"""Causal fixed-slot N-coin signals with availability, lifecycle and whole-target buffering controls."""
from __future__ import annotations
from dataclasses import dataclass
from numbers import Integral
import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.stattools import adfuller

SCHEDULE_EPOCH = pd.Timestamp("2022-01-03 00:00:00", tz="UTC")
SUPPORTED_REBALANCE_HOURS = (1, 4, 12, 24, 72, 168)

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
    """The 169 current unique strategy definitions."""
    import json
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[2] / 'configs/configuration_space.json').read_text())['cases']


def _validate_prices(prices: pd.DataFrame) -> None:
    """Validate real hourly marks without filling per-asset lifecycle gaps."""
    if not isinstance(prices, pd.DataFrame) or not prices.shape[1]:
        raise ValueError("Prices must be a nonempty asset DataFrame.")
    index = prices.index
    if (not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC" or not len(index)
            or index.has_duplicates or not index.is_monotonic_increasing
            or not index.equals(index.floor("h"))):
        raise ValueError("A sorted, unique, completed-hour UTC index is required.")
    if len(index) > 1 and not (index[1:] - index[:-1] == pd.Timedelta(hours=1)).all():
        raise ValueError("Prices require the complete hourly time grid, with NaN marks where unavailable.")
    if prices.columns.has_duplicates:
        raise ValueError("Asset columns must be unique.")
    values = prices.to_numpy(dtype=float)
    finite = values[~np.isnan(values)]
    if not np.isfinite(finite).all() or not (finite > 0).all():
        raise ValueError("Every observed price must be finite and strictly positive.")


def _bool_panel(value, prices, name, *, default=False):
    if value is None:
        return pd.DataFrame(default, index=prices.index, columns=prices.columns, dtype=bool)
    if (not isinstance(value, pd.DataFrame) or not value.index.equals(prices.index)
            or not value.columns.equals(prices.columns) or value.isna().to_numpy().any()
            or not all(pd.api.types.is_bool_dtype(dtype) for dtype in value.dtypes)):
        raise ValueError(f"{name} must be a nonmissing bool DataFrame exactly matching prices.")
    return value.copy()


def _halt_bridges(prices):
    """Preserve only explicit, source-audited whole-venue suspension bridges."""
    bridges = []
    for item in prices.attrs.get("halt_bridges", []):
        if not isinstance(item, dict) or not {"start", "end", "source"}.issubset(item) or not item["source"]:
            raise ValueError("Halt bridge requires start/end/source.")
        left, right = pd.Timestamp(item["start"]), pd.Timestamp(item["end"])
        if str(left.tz) != "UTC" or str(right.tz) != "UTC" or right <= left + pd.Timedelta(hours=1):
            raise ValueError("Invalid UTC halt bridge.")
        if left.floor("D") != (right - pd.Timedelta(nanoseconds=1)).floor("D"):
            raise ValueError("Halt bridges cannot cross interval-day boundaries.")
        if right <= prices.index[0] or left >= prices.index[-1]:
            continue
        if left not in prices.index or right not in prices.index:
            raise ValueError("Applicable bridge must have both grid endpoints.")
        bridges.append((left, right))
    bridges.sort()
    if any(second[0] < first[1] for first, second in zip(bridges, bridges[1:])):
        raise ValueError("Halt bridges cannot overlap.")
    return bridges


def _halt_interior(index, bridges):
    interior = np.zeros(len(index), dtype=bool)
    for left, right in bridges:
        interior |= (index > left) & (index < right)
    return interior


def _controls(prices, tradable, observed, decision_allowed, mandatory_exit):
    _validate_prices(prices)
    active = _bool_panel(tradable, prices, "tradable", default=True)
    observed = _bool_panel(observed, prices, "observed", default=True)
    observed &= prices.notna()
    exits = _bool_panel(mandatory_exit, prices, "mandatory_exit")
    if decision_allowed is None:
        decisions = pd.Series(True, index=prices.index, dtype=bool)
    elif isinstance(decision_allowed, pd.Series):
        if not decision_allowed.index.equals(prices.index) or not pd.api.types.is_bool_dtype(decision_allowed.dtype) or decision_allowed.isna().any():
            raise ValueError("decision_allowed Series must be bool and match prices index.")
        decisions = decision_allowed.copy()
    else:
        decisions = _bool_panel(decision_allowed, prices, "decision_allowed", default=True)
    bridges = _halt_bridges(prices)
    if isinstance(decisions, pd.Series):
        decisions.loc[_halt_interior(prices.index, bridges)] = False
    else:
        decisions.loc[_halt_interior(prices.index, bridges)] = False
    return active, observed, decisions, exits, bridges


def _schedule(index, spec):
    lookback, cadence = spec.get("lookback_h"), spec.get("rebalance_h")
    if isinstance(lookback, bool) or not isinstance(lookback, Integral) or lookback < 1:
        raise ValueError("lookback_h must be a positive integer.")
    if isinstance(cadence, bool) or cadence not in SUPPORTED_REBALANCE_HOURS:
        raise ValueError("Unsupported rebalance_h.")
    phase = spec.get("phase_hours", 0)
    if isinstance(phase, bool) or not isinstance(phase, Integral) or not 0 <= phase < cadence:
        raise ValueError("phase_hours must be an integer in [0, cadence).")
    if spec.get("grid_id") == "original":
        if cadence not in (1, 4, 24) or phase:
            raise ValueError("Hour-of-day scheduling supports zero-phase 1/4/24h.")
        return index.hour % cadence == 0
    elapsed = ((index - SCHEDULE_EPOCH) / pd.Timedelta(hours=1)).to_numpy(dtype=np.int64)
    return (elapsed - phase) % cadence == 0


def _cross_target(scores, eligible):
    """Average ties, demean and full L1 normalize only eligible observations."""
    scores = pd.Series(scores).where(eligible)
    if scores.notna().sum() < 2:
        return np.zeros(len(scores), dtype=float)
    ranks = scores.rank(method="average")
    centered = ranks - ranks.mean()
    normalizer = float(centered.abs().sum())
    return np.zeros(len(scores)) if normalizer <= 1e-15 else centered.fillna(0).to_numpy() / normalizer


def generate_targets(prices: pd.DataFrame, spec: dict, tradable: pd.DataFrame | None = None, *,
                     observed: pd.DataFrame | None = None, decision_allowed=None,
                     mandatory_exit: pd.DataFrame | None = None) -> pd.DataFrame:
    """N-slot targets using actual marks and causal lifecycle permissions.

    Unavailable current/lookback marks cannot become signals. A trailing interval
    with any inactive lifecycle hour is invalid, preventing returns across inactive gaps.
    Whole-venue halt interiors defer all decisions and retain exposure. Per-asset
    forced exits bypass buffering and scheduling; for cross-sectional families
    they rerank the full remaining eligible target, preserving neutrality.
    The caller must stop future tradability after a removal and implement the
    exact real quote/execution time, including subhour forced executions.
    """
    active, observed, allowed, exits, bridges = _controls(prices, tradable, observed, decision_allowed, mandatory_exit)
    family = spec.get("family")
    if family not in ("momentum", "reversal", "cross_momentum", "trend_long_cash", "trend_long_short"):
        raise ValueError("Use generate_factor_targets for factor_residual.")
    scheduled = _schedule(prices.index, spec)
    lookback = int(spec["lookback_h"])
    buffer = spec.get("buffer_l1", 0.0)
    if isinstance(buffer, bool) or not isinstance(buffer, (int, float)) or buffer not in (0.0, 0.25):
        raise ValueError("buffer_l1 must be 0 or 0.25.")
    cross = family in ("momentum", "reversal", "cross_momentum")
    if not cross and buffer:
        raise ValueError("Own-trend candidates do not support buffering.")
    score = prices.astype(float).div(prices.astype(float).shift(lookback)) - 1.0
    if family == "reversal":
        score = -score
    continuous = active.rolling(lookback + 1, min_periods=lookback + 1).sum().eq(lookback + 1)
    eligible = continuous & observed & observed.shift(lookback, fill_value=False) & np.isfinite(score)
    eligible.loc[_halt_interior(prices.index - pd.Timedelta(hours=lookback), bridges)] = False
    if isinstance(allowed, pd.DataFrame):
        eligible &= allowed
        global_allowed = allowed.any(axis=1).to_numpy()
    else:
        global_allowed = allowed.to_numpy()
    eligible &= ~exits
    if cross:
        ranks = score.where(eligible).rank(axis=1, method="average")
        centered = ranks.sub(ranks.mean(axis=1), axis=0)
        denominator = centered.abs().sum(axis=1)
        proposed = centered.div(denominator.replace(0, np.nan), axis=0).fillna(0).to_numpy()
    elif family == "trend_long_cash":
        proposed = score.gt(0).where(eligible, False).to_numpy(dtype=float) / prices.shape[1]
    else:
        proposed = np.sign(score).where(eligible, 0).to_numpy(dtype=float) / prices.shape[1]
    eligible_values = eligible.to_numpy(dtype=bool)
    exits_values = exits.to_numpy(dtype=bool)
    active_values = active.to_numpy(dtype=bool)
    observed_values = observed.to_numpy(dtype=bool)
    n = prices.shape[1]
    current = np.zeros(n, dtype=float)
    result = np.zeros(prices.shape, dtype=float)
    for i in range(len(prices)):
        forced = exits_values[i]
        # Never invent a trade or target decision in an audited venue halt.
        if global_allowed[i] and (scheduled[i] or forced.any()):
            valid = eligible_values[i] & ~exits_values[i]
            # A temporarily missing mark for an already-active symbol defers
            # the whole ordinary rebalance rather than liquidating at no quote.
            missing_active = active_values[i] & ~observed_values[i] & ~exits_values[i]
            if missing_active.any() and not forced.any():
                result[i] = current
                continue
            # A venue-halt denominator may invalidate every score. It is an
            # unavailable decision, unlike an observed all-equal rank target.
            if not valid.any() and active_values[i].any() and not forced.any():
                result[i] = current
                continue
            target = proposed[i]
            if forced.any() or float(np.abs(target - current).sum()) + 1e-12 >= buffer:
                current = target
        result[i] = current
    targets = pd.DataFrame(result, index=prices.index, columns=prices.columns)
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


def _fit_month_models(daily: pd.DataFrame, refit_time: pd.Timestamp, symbols: list[str], bridges,
                      formation_allowed: pd.DataFrame | None = None) -> list[dict]:
    """Fit beta on 30 returns, then screen a disjoint 60-endpoint level spread.

    The initial 91 prices generate exactly 90 daily log-return observations.
    Beta's return endpoints end t-61d; spread calibration begins t-60d.
    All N-1 fixed-budget pairs participate in Holm correction, including failed models
    represented by p=1. ADF is pinned: constant, maxlag=3, autolag='AIC'.
    """
    p = FACTOR_PARAMETERS
    desired = pd.date_range(refit_time - pd.Timedelta(days=p["formation_days"] + p["formation_lag_days"]),
                            refit_time - pd.Timedelta(days=p["formation_lag_days"]), freq="D", tz="UTC")
    formation = daily.reindex(desired)
    permission_times = desired
    if formation_allowed is not None and len(formation_allowed.index) > 1:
        if (formation_allowed.index[1] - formation_allowed.index[0]) == pd.Timedelta(hours=1):
            permission_times = pd.date_range(desired[0], desired[-1], freq="h", tz="UTC")
    models = []
    for symbol in symbols:
        model = _model_template(refit_time, symbol)
        pair = formation[[symbol, "BTCUSDT"]]
        values = pair.to_numpy(dtype=float)
        failures = []
        permission = (formation_allowed is None or formation_allowed.reindex(permission_times, fill_value=False)[[symbol, "BTCUSDT"]].to_numpy(dtype=bool).all())
        if not np.isfinite(values).all() or not permission or _halt_interior(desired, bridges).any():
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


def generate_factor_targets(prices: pd.DataFrame, tradable: pd.DataFrame | None = None, *,
                            observed: pd.DataFrame | None = None, decision_allowed=None,
                            mandatory_exit: pd.DataFrame | None = None) -> FactorResult:
    """The fixed BTC-factor residual model with 1/(N-1) capital per alt.

    Beta uses earliest 30 log returns, spread calibration the following 60
    disjoint endpoints; monthly coefficients freeze. All N-1 candidates enter
    Holm correction even if inactive or invalid. Monthly refit decisions force
    cash, with entries only on a later calendar day. Actual BTC legs aggregate
    before costs. No price or unavailable return is filled. Lifecycle exits may
    occur off the daily schedule; exact execution remains the caller's job.
    """
    active, observed, allowed, exits, bridges = _controls(prices, tradable, observed, decision_allowed, mandatory_exit)
    if "BTCUSDT" not in prices.columns or len(prices.columns) < 2:
        raise ValueError("Factor requires BTCUSDT and at least one non-BTC asset.")
    symbols = [s for s in prices.columns if s != "BTCUSDT"]
    budget = 1.0 / len(symbols)
    daily_mask = prices.index.hour == 0
    daily = prices.loc[daily_mask].astype(float).where(observed.loc[daily_mask])
    # Permissions cover exactly the formation start-price through last endpoint,
    # not an extra day before its first price. Whole-venue halts keep active=True.
    formation_permission = active
    state = {s: {"side": 0, "entry_time": None} for s in symbols}
    active_models = {}
    model_records, events = [], []
    updates = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    blocked_today = {s: None for s in symbols}
    allow_values = allowed.to_numpy(dtype=bool)
    active_values, observed_values, exit_values = [v.to_numpy(dtype=bool) for v in (active, observed, exits)]
    columns = list(prices.columns)
    btc_i = columns.index("BTCUSDT")
    alt_i = {s: columns.index(s) for s in symbols}
    current = np.zeros(len(columns), dtype=float)

    def emit(time, symbol, event, z=np.nan, prior_side=0, age=0):
        events.append({"decision_time": time, "symbol": symbol, "event": event,
                       "z": float(z), "side": state[symbol]["side"], "prior_side": prior_side,
                       "holding_days": age,
                       "model_refit_time": active_models.get(symbol, {}).get("refit_time", pd.NaT)})

    def clear(time, symbol, event):
        prior = state[symbol]["side"]
        age = int((time - state[symbol]["entry_time"]) / pd.Timedelta(days=1)) if prior else 0
        state[symbol] = {"side": 0, "entry_time": None}
        blocked_today[symbol] = time.floor("D")
        if prior:
            emit(time, symbol, event, prior_side=prior, age=age)

    for i, time in enumerate(prices.index):
        permitted = (bool(allow_values[i]) if allowed.ndim == 1 else bool(allow_values[i].any()))
        if not permitted:
            continue
        forced = exit_values[i]
        if forced.any():
            # Removal of the hedge unwinds all pairs, not merely its net leg.
            for symbol in symbols:
                if forced[btc_i] or forced[alt_i[symbol]]:
                    clear(time, symbol, "lifecycle_exit")
        if time.hour == 0:
            row = daily.loc[time]
            if time.day == 1:
                for symbol in symbols:
                    clear(time, symbol, "monthly_exit")
                fitted = _fit_month_models(daily, time, symbols, bridges, formation_permission)
                model_records.extend(fitted)
                active_models = {m["symbol"]: m for m in fitted}
                for symbol in symbols:
                    emit(time, symbol, "monthly_refit_cash")
            else:
                for symbol in symbols:
                    model = active_models.get(symbol)
                    if model is None or not model["eligible"]:
                        continue
                    pair = [alt_i[symbol], btc_i]
                    pair_allowed = permitted if allowed.ndim == 1 else bool(allow_values[i, pair].all())
                    if (not pair_allowed or not active_values[i, pair].all()
                            or not observed_values[i, pair].all() or forced[pair].any()
                            or blocked_today[symbol] == time.floor("D")):
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
                            blocked_today[symbol] = time.floor("D")
                            emit(time, symbol, exit_reason, z, prior_side=side, age=age)
                    elif FACTOR_PARAMETERS["entry_z"] <= abs(z) < FACTOR_PARAMETERS["stop_z"]:
                        state[symbol] = {"side": -int(np.sign(z)), "entry_time": time}
                        emit(time, symbol, "entry", z)
                    elif abs(z) >= FACTOR_PARAMETERS["stop_z"]:
                        emit(time, symbol, "entry_skipped_extreme", z)
        if time.hour == 0 or forced.any():
            current = np.zeros(len(columns), dtype=float)
            for symbol in symbols:
                side = state[symbol]["side"]
                if side:
                    beta = active_models[symbol]["beta"]
                    alt_weight = side * budget / (1.0 + abs(beta))
                    current[alt_i[symbol]] = alt_weight
                    current[btc_i] -= beta * alt_weight
            updates.loc[time] = current
    targets = updates.ffill().fillna(0.0)
    targets.attrs = dict(prices.attrs)
    return FactorResult(targets=targets, models=pd.DataFrame(model_records, columns=MODEL_COLUMNS),
                        events=pd.DataFrame(events, columns=EVENT_COLUMNS))
