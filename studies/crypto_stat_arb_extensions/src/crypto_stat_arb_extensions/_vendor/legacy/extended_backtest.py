"""Isolated extended time-scale signals; the original project stays unchanged.

Schedules use elapsed UTC hours from Monday 2022-01-03 00:00, not the clock's
hour-of-day. A 72-hour cadence really means every three days; 168 hours means
weekly. Price validation and the documented no-execution halt policy come from
the frozen core. Evaluation continues to use its simulate/metrics functions.
"""

from numbers import Integral

import numpy as np
import pandas as pd

from crypto_stat_arb.backtest import _halt_bridges, _positive_integer, _validate_prices


SCHEDULE_EPOCH = pd.Timestamp("2022-01-03 00:00:00", tz="UTC")
SUPPORTED_REBALANCE_HOURS = (1, 4, 12, 24, 72, 168)


def generate_scaled_targets(
    prices: pd.DataFrame,
    family: str,
    lookback_h: int,
    rebalance_h: int,
    phase_hours: int = 0,
) -> pd.DataFrame:
    """Rank trailing relative returns on a genuinely elapsed-time UTC schedule.

    Positive integer lookbacks are supported, including 2160 hours (90 days).
    The schedule condition is ``(hours_since_epoch - phase_hours) % cadence == 0``.
    Phase must be an integer in ``[0, rebalance_h)`` to avoid duplicate offsets.
    Targets, never prices, carry forward between decisions. An unavailable
    current price/lookback denominator or a declared halt interior defers the
    decision without flattening prior exposure; initial warm-up remains cash.
    Valid all-equal ranks are a genuine flat decision, not missing observations.
    """
    _validate_prices(prices)
    lookback_h = _positive_integer(lookback_h, "lookback_h")
    rebalance_h = _positive_integer(rebalance_h, "rebalance_h")
    if rebalance_h not in SUPPORTED_REBALANCE_HOURS:
        raise ValueError(f"rebalance_h must be one of {SUPPORTED_REBALANCE_HOURS}.")
    if family not in ("momentum", "reversal"):
        raise ValueError("family must be 'momentum' or 'reversal'.")
    if (isinstance(phase_hours, bool) or not isinstance(phase_hours, Integral)
            or not 0 <= phase_hours < rebalance_h):
        raise ValueError("phase_hours must be an integer in [0, rebalance_h).")

    numeric_prices = prices.astype(float)
    score = numeric_prices.div(numeric_prices.shift(lookback_h)) - 1.0
    if family == "reversal":
        score = -score
    ranks = score.rank(axis=1, method="average")
    centered = ranks.sub(ranks.mean(axis=1), axis=0)
    denominator = centered.abs().sum(axis=1)
    targets = centered.div(denominator.replace(0.0, np.nan), axis=0).fillna(0.0)

    # Timedelta division handles both nanosecond and microsecond index storage.
    elapsed_hours = ((prices.index - SCHEDULE_EPOCH) / pd.Timedelta(hours=1)).to_numpy(dtype=np.int64)
    scheduled = (elapsed_hours - int(phase_hours)) % rebalance_h == 0
    scheduled &= score.notna().all(axis=1).to_numpy()
    for start, end in _halt_bridges(prices):
        scheduled &= ~((prices.index > start) & (prices.index < end))
    targets.loc[~scheduled, :] = np.nan
    targets = targets.ffill().fillna(0.0)
    targets.index.name = prices.index.name
    return targets
