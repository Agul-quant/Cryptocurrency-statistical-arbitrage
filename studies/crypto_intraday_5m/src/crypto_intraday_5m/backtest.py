"""Pure course-style five-minute rank backtests with explicit halt intervals.

Targets observed at t earn the interval ending t+5 minutes at lag1. Lag2
delays this by one additional bar. Turnover is full L1 target-weight change;
ordinary drift, borrow, funding, and execution capacity are not modeled.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

import numpy as np
import pandas as pd


BAR_MINUTES = 5


@dataclass(frozen=True)
class BacktestResult:
    frame: pd.DataFrame
    held_weights: pd.DataFrame


def candidate_grid() -> list[dict]:
    return [{"strategy_id": f"{family}_m{lookback:03d}_r{cadence:03d}",
             "family": family, "lookback_minutes": lookback, "rebalance_minutes": cadence}
            for family in ("momentum", "reversal") for lookback in (5, 15, 30)
            for cadence in (5, 15, 60)]


def _positive_integer(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return int(value)


def _utc_endpoint(value) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if pd.isna(result):
        raise ValueError("Evaluation endpoints cannot be missing.")
    result = result.tz_localize("UTC") if result.tz is None else result.tz_convert("UTC")
    if result != result.floor("5min"):
        raise ValueError("Endpoints must be exact five-minute UTC boundaries.")
    return result


def _validate_index(index: pd.Index, *, require_complete: bool = True) -> None:
    if not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC":
        raise ValueError("Expected a timezone-aware UTC DatetimeIndex.")
    if index.empty or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Endpoints must be nonempty, sorted, and unique.")
    if not index.equals(index.floor("5min")):
        raise ValueError("Endpoints must be exact five-minute boundaries.")
    if require_complete and len(index) > 1 and not (index[1:] - index[:-1] == pd.Timedelta(minutes=5)).all():
        raise ValueError("Keep a complete five-minute calendar; unknown gaps cannot be compressed.")


def _halt_bridges(prices: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    bridges = []
    for item in prices.attrs.get("halt_bridges", []):
        if not isinstance(item, dict) or not {"start", "end", "source"}.issubset(item):
            raise ValueError("Halt bridges require start, end, and a source.")
        start, end = _utc_endpoint(item["start"]), _utc_endpoint(item["end"])
        if end <= start + pd.Timedelta(minutes=BAR_MINUTES) or not item["source"]:
            raise ValueError("A sourced halt bridge must cover more than one five-minute interval.")
        if start.floor("D") != (end - pd.Timedelta(nanoseconds=1)).floor("D"):
            raise ValueError("Halt bridges cannot cross UTC interval-day boundaries.")
        # Price slices retain full-history attrs; irrelevant bridges are ignored.
        if end <= prices.index[0] or start >= prices.index[-1]:
            continue
        if start not in prices.index or end not in prices.index:
            raise ValueError("Both endpoints of an applicable halt bridge must be present.")
        bridges.append((start, end))
    bridges.sort()
    if any(right[0] < left[1] for left, right in zip(bridges, bridges[1:])):
        raise ValueError("Declared halt bridges cannot overlap.")
    return bridges


def _halt_interior(index: pd.DatetimeIndex, bridges) -> np.ndarray:
    result = np.zeros(len(index), dtype=bool)
    for start, end in bridges:
        result |= (index > start) & (index < end)
    return result


def _validate_prices(prices: pd.DataFrame) -> None:
    if not isinstance(prices, pd.DataFrame) or not len(prices.columns):
        raise ValueError("Prices must be a DataFrame with asset columns.")
    _validate_index(prices.index)
    if prices.attrs.get("bar_minutes", BAR_MINUTES) != BAR_MINUTES:
        raise ValueError("Price metadata must identify five-minute bars.")
    if prices.columns.has_duplicates:
        raise ValueError("Asset names must be unique.")
    try:
        values = prices.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Prices must be numeric.") from exc
    bridges = _halt_bridges(prices)
    allowed = {_utc_endpoint(value) for value in prices.attrs.get("allowed_missing_endpoints", [])}
    for position in np.flatnonzero(np.isnan(values).any(axis=1)):
        endpoint = prices.index[position]
        if (endpoint not in allowed or not np.isnan(values[position]).all()
                or not any(start < endpoint < end for start, end in bridges)):
            raise ValueError("Missing prices require an explicit all-asset audited halt exemption.")
    observed = values[~np.isnan(values)]
    if not np.isfinite(observed).all() or not (observed > 0).all():
        raise ValueError("Observed prices must be finite and strictly positive; no filling is permitted.")


def observed_asset_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Observed simple returns; an audited bridge is one real price ratio."""
    _validate_prices(prices)
    result = prices.astype(float).div(prices.astype(float).shift(1)) - 1.0
    retained = np.ones(len(prices), dtype=bool)
    retained[0] = False
    durations = {}
    for start, end in _halt_bridges(prices):
        retained &= ~((prices.index > start) & (prices.index < end))
        result.loc[end] = prices.loc[end].astype(float).div(prices.loc[start].astype(float)) - 1.0
        durations[end.isoformat()] = int((end - start) / pd.Timedelta(minutes=1))
    result = result.loc[retained].copy()
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError("Nonfinite asset returns outside an audited observed interval.")
    result.attrs = {"interval_minutes": durations}
    return result


def generate_targets(prices: pd.DataFrame, family: str, lookback_minutes: int,
                     rebalance_minutes: int) -> pd.DataFrame:
    """Average-tie rank/demean/L1 targets, scheduled from UTC midnight.

    Signals use completed trailing price-ratio returns. Current and lookback
    endpoints inside a suspension are unavailable even when partial source
    prices exist. Unknown scores defer a decision; genuine all-tie scores are
    flat. Only targets, never prices or asset returns, carry forward.
    """
    _validate_prices(prices)
    if len(prices.columns) != 8:
        raise ValueError("The fixed pilot universe must contain eight assets.")
    lookback_minutes = _positive_integer(lookback_minutes, "lookback_minutes")
    rebalance_minutes = _positive_integer(rebalance_minutes, "rebalance_minutes")
    if lookback_minutes not in (5, 15, 30) or rebalance_minutes not in (5, 15, 60):
        raise ValueError("Use the predeclared 5/15/30-minute lookbacks and 5/15/60-minute cadences.")
    if family not in ("momentum", "reversal"):
        raise ValueError("family must be momentum or reversal.")
    score = prices.astype(float).div(prices.astype(float).shift(lookback_minutes // BAR_MINUTES)) - 1.0
    if family == "reversal":
        score = -score
    ranks = score.rank(axis=1, method="average")
    centered = ranks.sub(ranks.mean(axis=1), axis=0)
    weights = centered.div(centered.abs().sum(axis=1).replace(0.0, np.nan), axis=0).fillna(0.0)
    since_midnight = prices.index.hour * 60 + prices.index.minute
    scheduled = np.asarray(since_midnight % rebalance_minutes == 0)
    scheduled &= np.isfinite(score.to_numpy()).all(axis=1)
    bridges = _halt_bridges(prices)
    scheduled &= ~_halt_interior(prices.index, bridges)
    scheduled &= ~_halt_interior(prices.index - pd.Timedelta(minutes=lookback_minutes), bridges)
    weights.loc[~scheduled] = np.nan
    result = weights.ffill().fillna(0.0)
    result.index.name = prices.index.name
    result.attrs = dict(prices.attrs)
    return result


def _validate_cached_returns(prices: pd.DataFrame, returns: pd.DataFrame, bridges) -> None:
    if not isinstance(returns, pd.DataFrame) or not returns.columns.equals(prices.columns):
        raise ValueError("Cached asset returns must have exactly the price asset columns.")
    expected = prices.index[1:]
    expected = expected[~_halt_interior(expected, bridges)]
    values = returns.to_numpy(dtype=float)
    if (not returns.index.equals(expected) or not np.isfinite(values).all()
            or (values <= -1.0).any()):
        raise ValueError("Cached asset returns must cover every admissible observed interval.")
    required = {end.isoformat(): int((end - start) / pd.Timedelta(minutes=1)) for start, end in bridges}
    if returns.attrs.get("interval_minutes", {}) != required:
        raise ValueError("Cached return durations disagree with the audited halt policy.")


def simulate(prices: pd.DataFrame, targets: pd.DataFrame, start, end,
             cost_bps: float = 20, execution_lag: int = 1,
             asset_returns: pd.DataFrame | None = None) -> BacktestResult:
    """Evaluate observed intervals ending in (start,end], cash to liquidation.

    At a bridge endpoint, lag1 uses the target at bridge start; lag2 uses the
    target one five-minute bar before that start. No interior execution or mark
    is fabricated. Optional precomputed asset returns avoid recalculating all
    asset ratios. Cost scenarios should reuse a zero-cost result via apply_costs.
    """
    _validate_prices(prices)
    execution_lag = _positive_integer(execution_lag, "execution_lag")
    if not isinstance(targets, pd.DataFrame) or not targets.index.equals(prices.index) or not targets.columns.equals(prices.columns):
        raise ValueError("Targets must match the full price index and asset columns exactly.")
    if not np.isfinite(targets.to_numpy(dtype=float)).all():
        raise ValueError("Target weights must be finite; missing weights cannot be filled.")
    start, end = _utc_endpoint(start), _utc_endpoint(end)
    if end <= start or start not in prices.index or end not in prices.index:
        raise ValueError("Prices must cover increasing evaluation endpoints, including the start mark.")
    bridges = _halt_bridges(prices)
    if any(left < endpoint < right for left, right in bridges for endpoint in (start, end)):
        raise ValueError("Evaluation cannot start or liquidate inside a halt bridge.")
    if asset_returns is None:
        asset_returns = observed_asset_returns(prices)
    else:
        _validate_cached_returns(prices, asset_returns, bridges)
    desired = targets.astype(float).shift(execution_lag, fill_value=0.0)
    held = desired.reindex(asset_returns.index).copy()
    for left, right in bridges:
        held.loc[right] = desired.loc[left + pd.Timedelta(minutes=BAR_MINUTES)]
    window = (asset_returns.index > start) & (asset_returns.index <= end)
    held = held.loc[window].copy()
    observed = asset_returns.loc[window]
    gross = (held * observed).sum(axis=1)
    changes = held.diff()
    changes.iloc[0] = held.iloc[0]
    turnover = changes.abs().sum(axis=1)
    turnover.iloc[-1] += held.iloc[-1].abs().sum()
    duration_map = {key: value for key, value in asset_returns.attrs.get("interval_minutes", {}).items()
                    if pd.Timestamp(key) in gross.index}
    frame = pd.DataFrame({"gross_return": gross, "turnover": turnover,
                          "interval_minutes": [duration_map.get(t.isoformat(), BAR_MINUTES) for t in gross.index]})
    frame.attrs = {"interval_minutes": duration_map}
    return apply_costs(BacktestResult(frame=frame, held_weights=held), cost_bps)


def apply_costs(gross_result: BacktestResult, cost_bps: float) -> BacktestResult:
    """Reprice unchanged holdings at a cost without revalidating price panels.

    Always recomputes from gross_return and full-L1 turnover, so it never
    subtracts a second cost from an already costed return. Held weights remain
    shared/read-only by convention; the newly calculated frame is independent.
    """
    if isinstance(cost_bps, bool) or not np.isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("cost_bps must be finite and nonnegative.")
    frame = gross_result.frame
    if not {"gross_return", "turnover", "interval_minutes"}.issubset(frame):
        raise ValueError("Gross result requires gross_return, turnover, and interval_minutes.")
    values = frame[["gross_return", "turnover", "interval_minutes"]].to_numpy(dtype=float)
    if (frame.empty or not np.isfinite(values).all() or (values[:, 1] < 0).any()
            or (values[:, 2] <= 0).any() or (values[:, 2] % BAR_MINUTES != 0).any()):
        raise ValueError("Invalid gross return, turnover, or elapsed duration.")
    cost = frame["turnover"] * (float(cost_bps) * 1e-4)
    net = frame["gross_return"] - cost
    if not np.isfinite(net.to_numpy()).all() or (net <= -1).any():
        raise ValueError("Net observed-interval return <= -1 or nonfinite: cannot compound.")
    log_equity = np.log1p(net).cumsum()
    if not np.isfinite(log_equity.to_numpy()).all():
        raise ValueError("Cumulative log wealth became nonfinite.")
    with np.errstate(under="ignore", over="ignore"):
        equity = np.exp(log_equity)
    if not np.isfinite(equity.to_numpy()).all():
        raise ValueError("Displayed equity overflowed; log wealth remains available only internally.")
    # High-cost valid paths can underflow exp(log wealth) to zero. Preserve
    # their mathematical positive wealth through log_equity, not an epsilon
    # floor or a false insolvency error. Drawdown also uses log wealth peaks.
    log_peak = log_equity.cummax().clip(lower=0.0)
    drawdown = np.expm1(log_equity - log_peak)
    calculated = pd.DataFrame({"gross_return": frame["gross_return"], "net_return": net,
        "turnover": frame["turnover"], "cost": cost, "equity": equity,
        "log_equity": log_equity, "drawdown": drawdown,
        "interval_minutes": frame["interval_minutes"]})
    calculated.attrs = dict(frame.attrs)
    return BacktestResult(frame=calculated, held_weights=gross_result.held_weights)
