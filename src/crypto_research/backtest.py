"""Portfolio result container and UTC endpoint validators."""
from dataclasses import dataclass
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


def _utc_endpoint(value) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("Evaluation endpoints cannot be missing.")
    timestamp = timestamp.tz_localize("UTC") if timestamp.tz is None else timestamp.tz_convert("UTC")
    if timestamp != timestamp.floor("h"):
        raise ValueError("Evaluation endpoints must be exact hours.")
    return timestamp

