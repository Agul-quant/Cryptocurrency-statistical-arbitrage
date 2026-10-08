"""Calendar-day performance and BTC attribution for course backtests."""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from numbers import Integral

from .backtest import BacktestResult, _utc_endpoint, _validate_hourly_index


def _interval_hours(hourly: pd.Series) -> pd.Series:
    """Validate sparse interval continuity against explicit elapsed durations."""
    _validate_hourly_index(hourly.index, require_complete=False)
    declared = hourly.attrs.get("interval_hours", {})
    if not isinstance(declared, dict):
        raise ValueError("interval_hours metadata must be an endpoint-to-duration mapping.")
    normalized = {}
    for endpoint, duration in declared.items():
        if isinstance(duration, bool) or not isinstance(duration, Integral) or duration < 1:
            raise ValueError("Interval durations must be positive whole hours.")
        normalized[_utc_endpoint(endpoint)] = int(duration)
    durations = pd.Series([normalized.get(endpoint, 1) for endpoint in hourly.index],
                          index=hourly.index, dtype=int)
    if len(hourly) > 1:
        gaps = (hourly.index[1:] - hourly.index[:-1]) / pd.Timedelta(hours=1)
        if not np.array_equal(gaps.to_numpy(), durations.iloc[1:].to_numpy()):
            raise ValueError("Missing/unrecognized interval: timestamps must match declared durations.")
    beginnings = hourly.index - pd.to_timedelta(durations.to_numpy(), unit="h")
    interval_days = (hourly.index - pd.Timedelta(nanoseconds=1)).floor("D")
    if not beginnings.floor("D").equals(interval_days):
        raise ValueError("Observed intervals cannot cross UTC interval-day boundaries.")
    return durations


def daily_returns(hourly: pd.Series) -> pd.Series:
    """Compound UTC interval-days; a midnight endpoint ends the preceding day.

    Every emitted day must cover 24 elapsed hours. Explicit interval_hours attrs
    permit audited sparse halt bridges, never inferred or filled observations.
    Partial days, unrecognized gaps, and bankruptcy returns remain errors.
    """
    if not isinstance(hourly, pd.Series):
        raise ValueError("Hourly returns must be a Series.")
    durations = _interval_hours(hourly)
    values = hourly.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= -1.0).any():
        raise ValueError("Hourly returns must be finite and greater than -1.")
    interval_days = (hourly.index - pd.Timedelta(nanoseconds=1)).floor("D")
    counts = durations.groupby(interval_days).sum()
    if not counts.eq(24).all():
        raise ValueError("Every UTC interval-day must cover exactly 24 elapsed hours.")
    daily = (1.0 + hourly.astype(float)).groupby(interval_days).prod() - 1.0
    daily.name = hourly.name
    daily.index.name = "day"
    if not np.isfinite(daily.to_numpy()).all():
        raise ValueError("Daily compounding overflowed.")
    return daily


def summarize(result: BacktestResult, benchmark_hourly: pd.Series | None = None) -> dict:
    """Report daily 365-period arithmetic metrics and observed-endpoint drawdown.

    Sharpe assumes risk-free return zero and uses sample standard deviation.
    Maximum drawdown is a positive loss magnitude; frame drawdowns are signed.
    CAGR uses actual covered elapsed time with a 365-day year. BTC alpha/beta
    uses contemporaneous daily returns, an intercept, and HAC(7) inference.
    During an audited halt, intra-interval drawdowns are intentionally unobserved.
    """
    frame = result.frame
    required = {"net_return", "equity", "drawdown", "turnover", "cost"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Backtest frame is missing columns: {sorted(required - set(frame.columns))}.")
    net = frame["net_return"].copy()
    if "interval_hours" in frame:
        supplied = frame["interval_hours"]
        if not np.isfinite(supplied.to_numpy(dtype=float)).all():
            raise ValueError("Frame interval durations must be finite.")
        net.attrs["interval_hours"] = {
            endpoint.isoformat(): duration
            for endpoint, duration in supplied.items() if duration != 1
        }
    durations = _interval_hours(net)
    elapsed_hours = int(durations.sum())
    daily = daily_returns(net)
    mean, std = float(daily.mean()), float(daily.std(ddof=1))
    duration_years = elapsed_hours / (365.0 * 24)
    terminal = float(frame["equity"].iloc[-1])
    if not np.isfinite(terminal) or terminal <= 0:
        raise ValueError("Terminal equity must be finite and positive.")
    # exp(log(.)) is more stable than exponentiating an extreme tiny terminal.
    with np.errstate(over="ignore"):
        cagr = float(np.expm1(np.log(terminal) / duration_years))
    cagr = cagr if np.isfinite(cagr) else None
    stats = {
        "total_return": terminal - 1.0,
        "cagr": cagr,
        "annual_return": mean * 365.0,
        "annual_volatility": std * np.sqrt(365.0) if np.isfinite(std) else None,
        "sharpe": mean / std * np.sqrt(365.0) if np.isfinite(std) and std > 1e-15 else None,
        "max_drawdown": max(0.0, -float(frame["drawdown"].min())),
        "mean_hourly_turnover": float(frame["turnover"].sum() / elapsed_hours),
        "total_turnover": float(frame["turnover"].sum()),
        "total_cost_sum": float(frame["cost"].sum()),
        "n_hours": elapsed_hours,
        "n_observations": len(frame),
        "n_days": len(daily),
        "alpha_annual": None,
        "beta": None,
        "alpha_tstat": None,
        "alpha_pvalue": None,
        "alpha_ci_low": None,
        "alpha_ci_high": None,
        "beta_ci_low": None,
        "beta_ci_high": None,
    }
    if benchmark_hourly is not None:
        if not isinstance(benchmark_hourly, pd.Series):
            raise ValueError("benchmark_hourly must be a Series.")
        if not isinstance(benchmark_hourly.index, pd.DatetimeIndex) or benchmark_hourly.index.tz is None:
            raise ValueError("Benchmark timestamps must be timezone-aware.")
        if benchmark_hourly.index.has_duplicates:
            raise ValueError("Benchmark timestamps must be unique.")
        benchmark = benchmark_hourly.reindex(frame.index)
        benchmark_daily = daily_returns(benchmark)
        if len(daily) >= 3 and benchmark_daily.std(ddof=1) > 1e-15:
            X = sm.add_constant(benchmark_daily.rename("benchmark"), has_constant="add")
            fit = sm.OLS(daily, X).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
            confidence = fit.conf_int(alpha=0.05)
            stats.update(
                alpha_annual=float(fit.params["const"] * 365.0),
                beta=float(fit.params["benchmark"]),
                alpha_tstat=float(fit.tvalues["const"]),
                alpha_pvalue=float(fit.pvalues["const"]),
                alpha_ci_low=float(confidence.loc["const", 0] * 365.0),
                alpha_ci_high=float(confidence.loc["const", 1] * 365.0),
                beta_ci_low=float(confidence.loc["benchmark", 0]),
                beta_ci_high=float(confidence.loc["benchmark", 1]),
            )
            for key, value in stats.items():
                if isinstance(value, float) and not np.isfinite(value):
                    stats[key] = None
    return stats
