"""Causal daily signal and regime diagnostics, never trading filters.

Inference uses circular moving blocks of *calendar dates*. Missing observations
remain in that grid, and each replicate resamples the same dates for every
hypothesis. Intervals and centered-null p values are nominal block-bootstrap
inference; Holm correction addresses the declared within-period test family,
not strategy selection or previous exploratory research.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

import numpy as np
import pandas as pd


REGIME_COLUMNS = ("relative_quote_volume", "btc_volatility_30d", "return_dispersion_24h")


def _utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("Dates cannot be missing")
    return stamp.tz_localize("UTC") if stamp.tz is None else stamp.tz_convert("UTC")


def _windows(splits: Mapping) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    result = []
    for name, window in splits.items():
        start, end = _utc(window["start"]), _utc(window["end"])
        if start >= end or start != start.normalize() or end != end.normalize():
            raise ValueError("Diagnostic periods require increasing midnight UTC bounds")
        result.append((str(name), start, end))
    ordered = sorted(result, key=lambda item: item[1])
    if any(left[2] > right[1] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("Diagnostic periods cannot overlap")
    return result


def _validate_panel(panel: pd.DataFrame, *, positive: bool) -> None:
    if not isinstance(panel, pd.DataFrame) or panel.empty or not len(panel.columns):
        raise ValueError("Expected a nonempty hourly panel")
    index = panel.index
    if (not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC" or
            index.has_duplicates or not index.is_monotonic_increasing or
            not index.equals(index.floor("h")) or panel.columns.has_duplicates):
        raise ValueError("Expected unique sorted UTC hourly endpoints and asset columns")
    if len(index) > 1 and not ((index[1:] - index[:-1]) == pd.Timedelta(hours=1)).all():
        raise ValueError("Keep the full hourly calendar; do not compress missing dates")
    values = panel.to_numpy(dtype=float)
    observed = values[~np.isnan(values)]
    if not np.isfinite(observed).all() or (positive and (observed <= 0).any()):
        raise ValueError("Observed panel values must be finite and prices positive")
    if not positive and (observed < 0).any():
        raise ValueError("Quote volume must be nonnegative")


def _halt_interior(index: pd.DatetimeIndex, prices: pd.DataFrame) -> np.ndarray:
    inside = np.zeros(len(index), dtype=bool)
    for bridge in prices.attrs.get("halt_bridges", []):
        if not isinstance(bridge, dict) or not {"start", "end", "source"}.issubset(bridge):
            raise ValueError("Halt metadata needs exact boundaries and source")
        start, end = _utc(bridge["start"]), _utc(bridge["end"])
        if end <= start or not bridge["source"]:
            raise ValueError("Invalid documented halt bridge")
        inside |= (index > start) & (index < end)
    return inside


def _bootstrap_settings(n_bootstrap: int, block_days: int) -> None:
    for value, name in ((n_bootstrap, "n_bootstrap"), (block_days, "block_days")):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
            raise ValueError(f"{name} must be a positive integer")


def _circular_block_indices(n_dates: int, n_replicates: int, block_days: int,
                            rng: np.random.Generator) -> np.ndarray:
    """Draw contiguous date blocks, including missing rows and calendar wrap."""
    length = min(block_days, n_dates)
    starts = rng.integers(0, n_dates, size=(n_replicates, math.ceil(n_dates / length)))
    blocks = (starts[..., None] + np.arange(length)) % n_dates
    return blocks.reshape(n_replicates, -1)[:, :n_dates]


def _means(values: np.ndarray, axis: int) -> np.ndarray:
    observed = np.isfinite(values)
    numerator = np.where(observed, values, 0.0).sum(axis=axis)
    denominator = observed.sum(axis=axis)
    return np.divide(numerator, denominator, out=np.full_like(numerator, np.nan, dtype=float),
                     where=denominator > 0)


def _bootstrap_means(values: np.ndarray, n_bootstrap: int, block_days: int,
                     seed: int) -> np.ndarray:
    """Shared-calendar resampling across all matrix columns, bounded memory."""
    _bootstrap_settings(n_bootstrap, block_days)
    n_dates, n_columns = values.shape
    result = np.full((n_bootstrap, n_columns), np.nan)
    if n_dates < 2 * block_days:
        return result  # A single effective block cannot justify a precise CI.
    rng = np.random.default_rng(seed)
    for begin in range(0, n_bootstrap, 100):
        count = min(100, n_bootstrap - begin)
        sample = _circular_block_indices(n_dates, count, block_days, rng)
        result[begin:begin + count] = _means(values[sample], axis=1)
    return result


def _infer(estimate: float, replicates: np.ndarray, *, null_center: float = 0.0) -> dict:
    finite = replicates[np.isfinite(replicates)]
    if not np.isfinite(estimate) or len(finite) < 2:
        return {"ci_low": np.nan, "ci_high": np.nan, "p_value": np.nan,
                "n_bootstrap_valid": len(finite)}
    # The bootstrap distribution translated to the null uses sample centering.
    centered_null = finite - estimate + null_center
    p_value = (1 + np.count_nonzero(np.abs(centered_null - null_center) >=
                                   abs(estimate - null_center))) / (len(finite) + 1)
    low, high = np.quantile(finite, [0.025, 0.975])
    return {"ci_low": float(low), "ci_high": float(high), "p_value": float(p_value),
            "n_bootstrap_valid": len(finite)}


def _holm(p_values: Sequence[float]) -> np.ndarray:
    """Holm over the entire declared family; undefined tests count as p=1."""
    values = np.asarray(p_values, dtype=float)
    defined = np.isfinite(values)
    safe = np.where(defined, values, 1.0)
    order = np.argsort(safe, kind="stable")
    adjusted = np.minimum(1.0, np.maximum.accumulate(
        safe[order] * (len(safe) - np.arange(len(safe)))))
    result = np.full(len(values), np.nan)
    result[order] = adjusted
    result[~defined] = np.nan
    return result


def _rank_ic(score: np.ndarray, future: np.ndarray) -> np.ndarray:
    left = pd.DataFrame(score).rank(axis=1, method="average").to_numpy()
    right = pd.DataFrame(future).rank(axis=1, method="average").to_numpy()
    left -= left.mean(axis=1, keepdims=True)
    right -= right.mean(axis=1, keepdims=True)
    denominator = np.sqrt((left * left).sum(axis=1) * (right * right).sum(axis=1))
    return np.divide((left * right).sum(axis=1), denominator,
                     out=np.full(len(score), np.nan), where=denominator > 0)


def signal_ic(prices: pd.DataFrame, splits: dict,
              lookbacks: Sequence[int] = (1, 4, 12, 24, 72, 168, 336, 672),
              forward_horizons: Sequence[int] = (1, 24, 168),
              n_bootstrap: int = 4000, block_days: int = 28,
              seed: int = 20261006) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily cross-sectional Spearman IC of raw positive trailing returns.

    Decisions occur at 00:00 UTC in [start,end). Future endpoints can equal,
    but never exceed, the period end. Reversal uses the interpretation of a
    negative IC, not an independently negated/retested hypothesis. A fixed
    asset panel must be wholly observed; ties use average ranks and all-equal
    score/outcome vectors have undefined IC. Interior halt endpoints are
    inadmissible even if their partial source candle contains a price.
    """
    _validate_panel(prices, positive=True)
    _bootstrap_settings(n_bootstrap, block_days)
    for horizon in (*lookbacks, *forward_horizons):
        if isinstance(horizon, bool) or not isinstance(horizon, (int, np.integer)) or horizon < 1:
            raise ValueError("Lookbacks and forward horizons must be positive integer hours")
    if not lookbacks or not forward_horizons or len(set(lookbacks)) != len(lookbacks) or len(set(forward_horizons)) != len(forward_horizons):
        raise ValueError("Provide nonempty unique lookbacks and forward horizons")
    daily_rows, summary_rows = [], []
    hypotheses = [(int(back), int(forward)) for back in lookbacks for forward in forward_horizons]
    for period_number, (name, start, end) in enumerate(_windows(splits)):
        dates = pd.date_range(start, end, freq="D", inclusive="left", name="decision_date")
        current = prices.reindex(dates).to_numpy(dtype=float)
        matrix = np.full((len(dates), len(hypotheses)), np.nan)
        for column, (back, forward) in enumerate(hypotheses):
            past_dates, future_dates = dates - pd.Timedelta(hours=back), dates + pd.Timedelta(hours=forward)
            past, future = prices.reindex(past_dates).to_numpy(dtype=float), prices.reindex(future_dates).to_numpy(dtype=float)
            crossed = future_dates > end
            interior = (_halt_interior(dates, prices) | _halt_interior(past_dates, prices) |
                        _halt_interior(future_dates, prices))
            complete = np.isfinite(current).all(axis=1) & np.isfinite(past).all(axis=1) & np.isfinite(future).all(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                ic = _rank_ic(current / past - 1.0, future / current - 1.0)
            ic[crossed | interior | ~complete] = np.nan
            matrix[:, column] = ic
            reason = np.where(crossed, "crosses_split_end", np.where(interior, "halt_interior",
                     np.where(~complete, "unavailable_endpoint", np.where(~np.isfinite(ic),
                     "undefined_rank_variance", "eligible"))))
            daily_rows.append(pd.DataFrame({"split": name, "decision_date": dates,
                "lookback_h": back, "forward_horizon_h": forward, "ic": ic,
                "eligible": np.isfinite(ic), "exclusion_reason": reason}))
        replicates = _bootstrap_means(matrix, n_bootstrap, block_days, seed + period_number)
        estimates = _means(matrix, axis=0)
        period_rows = []
        for column, (back, forward) in enumerate(hypotheses):
            observed = matrix[np.isfinite(matrix[:, column]), column]
            inference = _infer(float(estimates[column]), replicates[:, column]) if len(observed) >= 2 else _infer(np.nan, replicates[:, column])
            period_rows.append({"split": name, "lookback_h": back, "forward_horizon_h": forward,
                "n_calendar_days": len(dates), "n_valid": len(observed),
                "mean_ic": float(estimates[column]),
                "median_ic": float(np.median(observed)) if len(observed) else np.nan,
                "positive_fraction": float((observed > 0).mean()) if len(observed) else np.nan,
                **inference, "block_days": block_days, "bootstrap_seed": seed + period_number,
                "holm_family_size": len(hypotheses), "inference": "nominal circular calendar-day moving-block bootstrap"})
        adjusted = _holm([row["p_value"] for row in period_rows])
        summary_rows.extend({**row, "p_holm": value} for row, value in zip(period_rows, adjusted))
    daily = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()
    return daily, pd.DataFrame(summary_rows)


def regime_features(prices: pd.DataFrame, quote_volume: pd.DataFrame) -> pd.DataFrame:
    """Completed-bar midnight features, with strict complete volume windows."""
    _validate_panel(prices, positive=True)
    _validate_panel(quote_volume, positive=False)
    if not prices.index.equals(quote_volume.index) or not prices.columns.equals(quote_volume.columns):
        raise ValueError("Prices and quote volume must have matching hourly endpoints/assets")
    if "BTCUSDT" not in prices:
        raise ValueError("BTCUSDT is required for the volatility diagnostic")
    dates = pd.date_range(prices.index.min().normalize(), prices.index.max().normalize(),
                          freq="D", name="decision_date")
    daily_prices = prices.reindex(dates)
    prior_prices = prices.reindex(dates - pd.Timedelta(days=1)).set_axis(dates)
    returns = daily_prices.div(prior_prices) - 1.0
    invalid_endpoint = _halt_interior(dates, prices) | _halt_interior(dates - pd.Timedelta(days=1), prices)
    returns.loc[invalid_endpoint] = np.nan
    # Each daily column requires all 24 hourly observations; then every asset.
    daily_volume = quote_volume.resample("D", closed="right", label="right").sum(min_count=24)
    daily_total = daily_volume.sum(axis=1, min_count=len(prices.columns)).reindex(dates)
    preceding_average = daily_total.shift(1).rolling(7, min_periods=7).mean()
    relative = daily_total.div(preceding_average.where(preceding_average > 0))
    volatility = returns["BTCUSDT"].rolling(30, min_periods=30).std(ddof=1)
    dispersion = returns.std(axis=1, ddof=1).where(returns.notna().all(axis=1))
    result = pd.DataFrame({"relative_quote_volume": relative,
                           "btc_volatility_30d": volatility,
                           "return_dispersion_24h": dispersion}, index=dates)
    result.attrs["definitions"] = {
        "relative_quote_volume": "Complete preceding 24h quote volume across fixed assets / strictly previous seven complete daily totals mean",
        "btc_volatility_30d": "Sample standard deviation of preceding 30 complete BTC 24h simple returns; unannualized",
        "return_dispersion_24h": "Sample cross-asset standard deviation of preceding 24h simple returns; full asset universe required"}
    return result


def fit_regime_thresholds(features: pd.DataFrame, start, end) -> dict:
    """Fit median cutoffs on the explicit development-only decision window."""
    start, end = _utc(start), _utc(end)
    if start >= end or start != start.normalize() or end != end.normalize():
        raise ValueError("Threshold training requires increasing UTC midnight bounds")
    if (not isinstance(features.index, pd.DatetimeIndex) or str(features.index.tz) != "UTC" or
            features.index.has_duplicates or not features.index.is_monotonic_increasing or
            not features.index.equals(features.index.normalize())):
        raise ValueError("Regime features require unique sorted UTC midnight decisions")
    training = features.loc[(features.index >= start) & (features.index < end)]
    cutoffs, counts = {}, {}
    for column in REGIME_COLUMNS:
        values = pd.to_numeric(training[column], errors="raise").replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty:
            raise ValueError(f"No finite development observations for {column}")
        cutoffs[column], counts[column] = float(values.median()), len(values)
    return {"thresholds": cutoffs, "n_training_observations": counts,
            "training_start": start.isoformat(), "training_end_exclusive": end.isoformat(),
            "rule": "high >= development median; low < median; missing is unknown",
            "definitions": features.attrs.get("definitions", {})}


def regime_diagnostics(return_frames: pd.DataFrame, features: pd.DataFrame,
                       thresholds: dict, splits: dict, n_bootstrap: int = 4000,
                       block_days: int = 28, seed: int = 20261006) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compound complete daily P&L; label using the preceding decision day.

    An interval ending at midnight belongs to the day that just ended. The
    documented four-hour halt bridge counts as four elapsed hours. Unknown
    features remain explicit observations and are never trading filters.
    Report conditional daily means, not a Sharpe on discontinuous strata.
    """
    _bootstrap_settings(n_bootstrap, block_days)
    required = {"bar_end", "strategy_id", "split", "cost_bps", "execution_lag",
                "gross_return", "net_return", "turnover", "interval_hours"}
    if not required.issubset(return_frames):
        raise ValueError(f"Missing return-frame fields: {sorted(required - set(return_frames.columns))}")
    if (not isinstance(features.index, pd.DatetimeIndex) or str(features.index.tz) != "UTC" or
            features.index.has_duplicates or not features.index.is_monotonic_increasing or
            not features.index.equals(features.index.normalize())):
        raise ValueError("Regime features require unique sorted UTC midnight decisions")
    cutoff = thresholds.get("thresholds", thresholds)
    if any(column not in cutoff or not np.isfinite(cutoff[column]) for column in REGIME_COLUMNS):
        raise ValueError("All regime thresholds must be finite and already frozen")
    frame = return_frames.copy()
    frame["bar_end"] = pd.to_datetime(frame["bar_end"], utc=True)
    if frame["bar_end"].isna().any() or not frame["bar_end"].equals(frame["bar_end"].dt.floor("h")):
        raise ValueError("Return endpoints must be finite UTC hours")
    keys = ["strategy_id", "split", "cost_bps", "execution_lag"]
    if frame.duplicated(keys + ["bar_end"]).any():
        raise ValueError("Duplicate portfolio return endpoints")
    values = frame[["gross_return", "net_return", "turnover", "interval_hours"]].to_numpy(dtype=float)
    if (not np.isfinite(values).all() or (values[:, :2] <= -1).any() or
            (values[:, 2] < 0).any() or (values[:, 3] <= 0).any()):
        raise ValueError("Invalid return, turnover, or elapsed interval")
    frame["decision_date"] = (frame["bar_end"] - pd.Timedelta(nanoseconds=1)).dt.floor("D")
    windows = _windows(splits)
    permitted = {name: (start, end) for name, start, end in windows}
    if not set(frame["split"].astype(str)).issubset(permitted):
        raise ValueError("Return frames contain an undeclared period")
    for name, (start, end) in permitted.items():
        actual = frame.loc[frame["split"].eq(name), "bar_end"]
        if ((actual <= start) | (actual > end)).any():
            raise ValueError("Portfolio returns cross their declared split boundaries")
    grouped_rows = []
    for group, part in frame.groupby(keys + ["decision_date"], sort=False):
        part = part.sort_values("bar_end")
        elapsed = float(part["interval_hours"].sum())
        if elapsed != 24:
            raise ValueError("Conditional daily P&L requires exactly 24 elapsed hours, including audited bridges")
        # Sum alone cannot certify coverage: each interval must tile the day.
        endpoints = pd.DatetimeIndex(part["bar_end"])
        beginnings = endpoints - pd.to_timedelta(part["interval_hours"].to_numpy(), unit="h")
        day = group[-1]
        if (beginnings[0] != day or endpoints[-1] != day + pd.Timedelta(days=1) or
                (len(part) > 1 and not np.array_equal(beginnings[1:].asi8, endpoints[:-1].asi8))):
            raise ValueError("Daily intervals must tile their calendar day without gaps or overlap")
        grouped_rows.append({**dict(zip(keys + ["decision_date"], group)),
            "gross_return": float(np.prod(1 + part["gross_return"]) - 1),
            "net_return": float(np.prod(1 + part["net_return"]) - 1),
            "turnover": float(part["turnover"].sum()), "interval_hours": elapsed,
            "n_return_observations": len(part)})
    daily = pd.DataFrame(grouped_rows)
    observation_parts, summary_rows = [], []
    for period_number, (name, start, end) in enumerate(windows):
        if daily.empty:
            continue
        period = daily.loc[daily["split"].eq(name)]
        dates = pd.date_range(start, end, freq="D", inclusive="left", name="decision_date")
        aligned_features = features.reindex(dates)
        contrast_specs, high_columns, low_columns = [], [], []
        period_summaries = []
        for group, part in period.groupby(keys, sort=True):
            observed_daily = part.set_index("decision_date").reindex(dates)
            metadata = dict(zip(keys, group))
            for column in REGIME_COLUMNS:
                feature = aligned_features[column].to_numpy(dtype=float)
                labels = np.where(~np.isfinite(feature), "unknown", np.where(feature >= cutoff[column], "high", "low"))
                observations = observed_daily[["gross_return", "net_return", "turnover", "interval_hours", "n_return_observations"]].copy()
                observations.insert(0, "decision_date", dates)
                for key, value in metadata.items():
                    observations[key] = value
                observations["regime_feature"], observations["feature_value"] = column, feature
                observations["threshold"], observations["regime"] = cutoff[column], labels
                observation_parts.append(observations.reset_index(drop=True))
                net = observed_daily["net_return"].to_numpy(dtype=float)
                high, low = np.where(labels == "high", net, np.nan), np.where(labels == "low", net, np.nan)
                contrast_id = len(contrast_specs)
                contrast_specs.append({**metadata, "regime_feature": column,
                    "n_high_valid": int(np.isfinite(high).sum()), "n_low_valid": int(np.isfinite(low).sum())})
                high_columns.append(high)
                low_columns.append(low)
                for label in ("high", "low", "unknown"):
                    mask = labels == label
                    selected = observed_daily.loc[mask]
                    period_summaries.append({**metadata, "regime_feature": column, "regime": label,
                        "threshold": cutoff[column], "n_calendar_days": len(dates),
                        "n_days": int(mask.sum()), "n_valid_returns": int(selected["net_return"].notna().sum()),
                        "mean_daily_gross_return": float(selected["gross_return"].mean()),
                        "mean_daily_net_return": float(selected["net_return"].mean()),
                        "mean_daily_turnover": float(selected["turnover"].mean()),
                        "share_calendar_days": float(mask.mean()), "contrast_id": contrast_id})
        if not contrast_specs:
            continue
        high_matrix, low_matrix = np.column_stack(high_columns), np.column_stack(low_columns)
        estimates = _means(high_matrix, axis=0) - _means(low_matrix, axis=0)
        # One combined matrix guarantees identical date blocks for both groups,
        # every feature and every strategy, rather than independent resampling.
        combined = np.column_stack((high_matrix, low_matrix))
        replicate_means = _bootstrap_means(combined, n_bootstrap, block_days, seed + period_number)
        n_contrasts = len(contrast_specs)
        replicate_differences = replicate_means[:, :n_contrasts] - replicate_means[:, n_contrasts:]
        inferences = []
        for column, spec in enumerate(contrast_specs):
            eligible = spec["n_high_valid"] >= 2 and spec["n_low_valid"] >= 2
            inference = _infer(float(estimates[column]) if eligible else np.nan, replicate_differences[:, column])
            inferences.append({"high_minus_low_net_return": float(estimates[column]), **inference,
                "n_high_valid": spec["n_high_valid"], "n_low_valid": spec["n_low_valid"],
                "block_days": block_days, "bootstrap_seed": seed + period_number,
                "holm_family_size": n_contrasts,
                "inference": "nominal circular calendar-day moving-block bootstrap"})
        adjusted = _holm([item["p_value"] for item in inferences])
        for row in period_summaries:
            contrast = row.pop("contrast_id")
            summary_rows.append({**row, **inferences[contrast], "p_holm": adjusted[contrast]})
    observations = pd.concat(observation_parts, ignore_index=True) if observation_parts else pd.DataFrame()
    return observations, pd.DataFrame(summary_rows)
