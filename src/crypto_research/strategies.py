"""Causal fixed-slot N-coin signals with availability, lifecycle and whole-target buffering controls."""
from __future__ import annotations
from numbers import Integral
import numpy as np
import pandas as pd

SCHEDULE_EPOCH = pd.Timestamp("2022-01-03 00:00:00", tz="UTC")
SUPPORTED_REBALANCE_HOURS = (1, 4, 12, 24, 72, 168)

def candidate_grid() -> list[dict]:
    """The 168 current unique strategy definitions."""
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
        raise ValueError("Unsupported strategy family.")
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
