"""Pure, idealized course-style cross-sectional crypto backtests.

Bars are indexed by completed UTC hour endpoints. A target observed at ``t``
earns the return ending at ``t + execution_lag hours``. The default lag of one
still assumes a fill at the observed close; an extra lag is a robustness test.
Turnover is full L1 target change, not half-turnover or drift-adjusted turnover.
"""

from dataclasses import dataclass
from numbers import Integral

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    frame: pd.DataFrame
    held_weights: pd.DataFrame


def _validate_hourly_index(index: pd.Index, *, require_complete: bool = True) -> None:
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("Expected a timezone-aware UTC DatetimeIndex.")
    if str(index.tz) != "UTC":
        raise ValueError("Hourly endpoints must use UTC.")
    if index.empty or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Hourly endpoints must be nonempty, sorted, and unique.")
    if not index.equals(index.floor("h")):
        raise ValueError("Timestamps must be exact completed hour endpoints.")
    if require_complete and len(index) > 1 and not (index[1:] - index[:-1] == pd.Timedelta(hours=1)).all():
        raise ValueError("Missing/nonhourly bars: a complete hourly grid is required.")


def _halt_bridges(prices: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Read declared, source-audited suspension intervals, never infer gaps."""
    bridges = []
    for item in prices.attrs.get("halt_bridges", []):
        if not isinstance(item, dict) or not {"start", "end", "source"}.issubset(item):
            raise ValueError("Halt bridges require start, end, and a source citation.")
        start, end = _utc_endpoint(item["start"]), _utc_endpoint(item["end"])
        if end <= start + pd.Timedelta(hours=1) or not item["source"]:
            raise ValueError("Halt bridges must cover multiple hours and cite a source.")
        if start.floor("D") != (end - pd.Timedelta(nanoseconds=1)).floor("D"):
            raise ValueError("Halt bridges cannot cross an interval-day boundary.")
        # Slices inherit full-history attrs; bridges wholly outside a slice do not apply.
        if end <= prices.index[0] or start >= prices.index[-1]:
            continue
        if start not in prices.index or end not in prices.index:
            raise ValueError("Prices must contain both endpoints of an applicable halt bridge.")
        bridges.append((start, end))
    bridges.sort()
    if any(right[0] < left[1] for left, right in zip(bridges, bridges[1:])):
        raise ValueError("Declared halt bridges cannot overlap.")
    return bridges


def _validate_prices(prices: pd.DataFrame) -> None:
    if not isinstance(prices, pd.DataFrame) or prices.shape[1] == 0:
        raise ValueError("Prices must be a DataFrame with at least one asset.")
    _validate_hourly_index(prices.index)
    if prices.columns.has_duplicates:
        raise ValueError("Asset names must be unique.")
    try:
        values = prices.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Prices must be numeric.") from exc
    bridges = _halt_bridges(prices)
    allowed = {_utc_endpoint(value) for value in prices.attrs.get("allowed_missing_endpoints", [])}
    missing_rows = np.isnan(values).any(axis=1)
    for position in np.flatnonzero(missing_rows):
        endpoint = prices.index[position]
        in_bridge = any(start < endpoint < end for start, end in bridges)
        if endpoint not in allowed or not in_bridge or not np.isnan(values[position]).all():
            raise ValueError("Missing prices require an explicit all-asset audited halt exemption.")
    finite_values = values[~np.isnan(values)]
    if not np.isfinite(finite_values).all() or not (finite_values > 0).all():
        raise ValueError("Prices must be finite and strictly positive; no filling is allowed.")


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return int(value)


def _utc_endpoint(value) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("Evaluation endpoints cannot be missing.")
    timestamp = timestamp.tz_localize("UTC") if timestamp.tz is None else timestamp.tz_convert("UTC")
    if timestamp != timestamp.floor("h"):
        raise ValueError("Evaluation endpoints must be exact hours.")
    return timestamp


def observed_asset_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Return observed interval P&L with explicitly declared suspension bridges.

    Raw partial/no-trade interior bars remain in the price audit but are not
    valuation or execution endpoints. A bridge from 11:00 to 15:00 earns
    ``P15 / P11 - 1`` once, covering four elapsed hours with no fictional marks.
    The first input price is a starting mark, so it has no return row.
    """
    _validate_prices(prices)
    result = prices.astype(float).div(prices.astype(float).shift(1)) - 1.0
    retained = np.ones(len(prices), dtype=bool)
    retained[0] = False
    durations = {}
    for start, end in _halt_bridges(prices):
        retained &= ~((prices.index > start) & (prices.index < end))
        result.loc[end] = prices.loc[end].astype(float).div(prices.loc[start].astype(float)) - 1.0
        durations[end.isoformat()] = int((end - start) / pd.Timedelta(hours=1))
    result = result.loc[retained].copy()
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError("Missing/nonfinite asset returns outside an audited observed interval.")
    result.attrs = {"interval_hours": durations}
    return result


def generate_targets(
    prices: pd.DataFrame, family: str, lookback_h: int, rebalance_h: int
) -> pd.DataFrame:
    """Generate rank/demean/L1 targets; incomplete warm-up and ties stay flat.

    Rebalance phases are fixed to UTC midnight: supported schedules are every
    1, 4, or 24 hours. Signals use trailing *price-ratio* returns, not the mean
    of individual hourly returns. Intervening rows repeat the last target.
    """
    _validate_prices(prices)
    lookback_h = _positive_integer(lookback_h, "lookback_h")
    rebalance_h = _positive_integer(rebalance_h, "rebalance_h")
    if rebalance_h not in (1, 4, 24):
        raise ValueError("rebalance_h must be one of 1, 4, or 24.")
    if family not in ("momentum", "reversal"):
        raise ValueError("family must be 'momentum' or 'reversal'.")
    score = prices.astype(float).div(prices.astype(float).shift(lookback_h)) - 1.0
    if family == "reversal":
        score = -score
    ranked = score.rank(axis=1, method="average")
    demeaned = ranked.sub(ranked.mean(axis=1), axis=0)
    normalizer = demeaned.abs().sum(axis=1)
    weights = demeaned.div(normalizer.replace(0.0, np.nan), axis=0).fillna(0.0)
    scheduled = prices.index.hour % rebalance_h == 0
    for start, end in _halt_bridges(prices):
        scheduled &= ~((prices.index > start) & (prices.index < end))
    # Missing elapsed-time denominators defer a decision, rather than liquidate.
    scheduled &= score.notna().all(axis=1).to_numpy()
    # Forward-fill targets only: never fill prices or missing asset returns.
    weights.loc[~scheduled, :] = np.nan
    weights = weights.ffill().fillna(0.0)
    weights.index.name = prices.index.name
    return weights


def simulate(
    prices: pd.DataFrame,
    targets: pd.DataFrame,
    start,
    end,
    cost_bps: float = 20,
    execution_lag: int = 1,
) -> BacktestResult:
    """Evaluate returns ending in ``(start, end]``, from cash to liquidation.

    Reset exposure to cash just before the first held return. Entry, implemented
    target changes, and terminal liquidation are charged once. Last-row turnover
    includes liquidation, but last-row held weights retain the exposure that
    earned that row's return. Combined targets need not be gross-renormalized.
    Audited halt intervals retain the holdings established at their start and
    aggregate the real endpoint return once, without intermediate trades/marks.
    Costs are subtracted arithmetically from the observed interval return, as in
    the course convention; this is not an exchange/execution simulator.
    """
    _validate_prices(prices)
    execution_lag = _positive_integer(execution_lag, "execution_lag")
    if not np.isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("cost_bps must be finite and nonnegative.")
    if not isinstance(targets, pd.DataFrame):
        raise ValueError("Targets must be a DataFrame.")
    if not targets.index.equals(prices.index) or not targets.columns.equals(prices.columns):
        raise ValueError("Targets must have exactly the prices' index and asset columns.")
    try:
        target_values = targets.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Targets must be numeric.") from exc
    if not np.isfinite(target_values).all():
        raise ValueError("Targets must be finite; missing weights cannot be filled.")
    start, end = _utc_endpoint(start), _utc_endpoint(end)
    if end <= start:
        raise ValueError("end must be later than start.")
    if start not in prices.index or end not in prices.index:
        raise ValueError("Prices must cover both evaluation endpoints, including the start price.")
    bridges = _halt_bridges(prices)
    if any(left < endpoint < right for left, right in bridges for endpoint in (start, end)):
        raise ValueError("Evaluation cannot start or liquidate inside a suspended halt bridge.")
    asset_returns = observed_asset_returns(prices)
    window = (asset_returns.index > start) & (asset_returns.index <= end)
    # Only prehistory unavailable because of the execution lag is initially cash.
    desired = targets.astype(float).shift(execution_lag, fill_value=0.0)
    held = desired.reindex(asset_returns.index).copy()
    for left, right in bridges:
        # The bridge retains holdings established at its start, never a target
        # inferred at its end. Under lag 1 this is target(left); under lag 2 it
        # is target(left - 1h). No rebalance takes place within the bridge.
        held.loc[right] = desired.loc[left + pd.Timedelta(hours=1)]
    held = held.loc[window].copy()
    asset_returns = asset_returns.loc[window].copy()
    if not np.isfinite(asset_returns.to_numpy()).all():
        raise ValueError("Missing/nonfinite asset returns in the held evaluation window.")
    gross = (held * asset_returns).sum(axis=1)
    changes = held.diff()
    changes.iloc[0] = held.iloc[0]  # evaluation starts from cash, not inherited holdings
    turnover = changes.abs().sum(axis=1)
    turnover.iloc[-1] += held.iloc[-1].abs().sum()  # terminal liquidation, once
    cost = turnover * (float(cost_bps) * 1e-4)
    net = gross - cost
    if not np.isfinite(net.to_numpy()).all() or (net <= -1.0).any():
        raise ValueError("Net hourly return <= -1 or nonfinite: the portfolio cannot be compounded.")
    equity = (1.0 + net).cumprod()
    if not np.isfinite(equity.to_numpy()).all():
        raise ValueError("Compounded equity overflowed.")
    peak = equity.cummax().clip(lower=1.0)  # include initial wealth 1 in the peak
    frame = pd.DataFrame(
        {
            "gross_return": gross,
            "net_return": net,
            "turnover": turnover,
            "cost": cost,
            "equity": equity,
            "drawdown": equity.div(peak) - 1.0,
        }
    )
    duration_map = {
        key: value for key, value in asset_returns.attrs.get("interval_hours", {}).items()
        if pd.Timestamp(key) in frame.index
    }
    frame["interval_hours"] = [duration_map.get(endpoint.isoformat(), 1) for endpoint in frame.index]
    frame.attrs = {"interval_hours": duration_map}
    return BacktestResult(frame=frame, held_weights=held)
