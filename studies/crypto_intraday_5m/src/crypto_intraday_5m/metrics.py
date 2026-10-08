"""Calendar-day five-minute performance and daily BTC attribution."""
from __future__ import annotations

from numbers import Integral

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .backtest import BAR_MINUTES, BacktestResult, _utc_endpoint, _validate_index


def _interval_minutes(returns: pd.Series) -> pd.Series:
    _validate_index(returns.index, require_complete=False)
    declared = returns.attrs.get("interval_minutes", {})
    if not isinstance(declared, dict):
        raise ValueError("interval_minutes must be an endpoint-to-duration mapping.")
    normalized = {}
    for endpoint, duration in declared.items():
        if (isinstance(duration, bool) or not isinstance(duration, Integral)
                or duration < BAR_MINUTES or duration % BAR_MINUTES):
            raise ValueError("Interval durations must be positive whole multiples of five minutes.")
        normalized[_utc_endpoint(endpoint)] = int(duration)
    durations = pd.Series([normalized.get(t, BAR_MINUTES) for t in returns.index],
                          index=returns.index, dtype=int)
    if len(returns) > 1:
        gaps = (returns.index[1:] - returns.index[:-1]) / pd.Timedelta(minutes=1)
        if not np.array_equal(gaps.to_numpy(), durations.iloc[1:].to_numpy()):
            raise ValueError("Missing/unrecognized interval: endpoints must match declared durations.")
    beginnings = returns.index - pd.to_timedelta(durations.to_numpy(), unit="min")
    interval_days = (returns.index - pd.Timedelta(nanoseconds=1)).floor("D")
    if not beginnings.floor("D").equals(interval_days):
        raise ValueError("Observed intervals cannot cross UTC interval-day boundaries.")
    return durations


def daily_returns(minute_returns: pd.Series) -> pd.Series:
    """Compound complete UTC days, including explicit sparse halt intervals.

    A midnight endpoint ends the preceding day. Every emitted day requires
    1,440 elapsed minutes: ordinarily 288 five-minute observations. No zero
    filling, compressed unknown gaps, or partial-day annualization is allowed.
    """
    if not isinstance(minute_returns, pd.Series):
        raise ValueError("Five-minute returns must be a Series.")
    durations = _interval_minutes(minute_returns)
    values = minute_returns.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= -1).any():
        raise ValueError("Interval returns must be finite and greater than -1.")
    interval_days = (minute_returns.index - pd.Timedelta(nanoseconds=1)).floor("D")
    if not durations.groupby(interval_days).sum().eq(1440).all():
        raise ValueError("Every UTC interval-day must cover exactly 1440 elapsed minutes.")
    daily = (1 + minute_returns.astype(float)).groupby(interval_days).prod() - 1
    daily.name = minute_returns.name
    daily.index.name = "day"
    if not np.isfinite(daily.to_numpy()).all():
        raise ValueError("Daily compounding overflowed.")
    return daily


def summarize(result: BacktestResult, benchmark_minute: pd.Series | None = None) -> dict:
    """Daily 365-period metrics; observed-endpoint drawdown; OLS HAC(7).

    CAGR uses elapsed duration, risk-free return is zero, volatility uses
    daily sample SD, and drawdown is positive loss magnitude. Intra-halt
    drawdown remains unobserved rather than imputed.
    """
    frame = result.frame
    if not {"net_return", "equity", "drawdown", "turnover", "cost", "interval_minutes"}.issubset(frame):
        raise ValueError("Backtest frame lacks required performance fields.")
    supplied = frame["interval_minutes"]
    if not np.isfinite(supplied.to_numpy(dtype=float)).all():
        raise ValueError("Frame interval durations must be finite.")
    net = frame["net_return"].copy()
    net.attrs = {"interval_minutes": {t.isoformat(): duration for t, duration in supplied.items()
                                      if duration != BAR_MINUTES}}
    durations = _interval_minutes(net)
    elapsed = int(durations.sum())
    daily = daily_returns(net)
    mean, std = float(daily.mean()), float(daily.std(ddof=1))
    terminal = float(frame["equity"].iloc[-1])
    if "log_equity" in frame:
        log_values = frame["log_equity"].to_numpy(dtype=float)
        if not np.isfinite(log_values).all() or not np.isfinite(terminal) or terminal < 0:
            raise ValueError("Log wealth must be finite and displayed wealth nonnegative.")
        terminal_log = float(log_values[-1])
        underflow_count = int(frame["equity"].eq(0.0).sum())
    else:
        if not np.isfinite(terminal) or terminal <= 0:
            raise ValueError("Terminal equity must be finite and positive without explicit log wealth.")
        terminal_log, underflow_count = float(np.log(terminal)), 0
    years = elapsed / (365.0 * 1440)
    with np.errstate(over="ignore"):
        cagr = float(np.expm1(terminal_log / years))
    stats = {
        "total_return": terminal - 1, "cagr": cagr if np.isfinite(cagr) else None,
        "annual_return": mean * 365.0,
        "annual_volatility": std * np.sqrt(365) if np.isfinite(std) else None,
        "sharpe": mean / std * np.sqrt(365) if np.isfinite(std) and std > 1e-15 else None,
        "max_drawdown": max(0.0, -float(frame["drawdown"].min())),
        "mean_minute_turnover": float(frame["turnover"].sum() / elapsed),
        "mean_hourly_turnover": float(frame["turnover"].sum() / (elapsed / 60.0)),
        "total_turnover": float(frame["turnover"].sum()), "total_cost_sum": float(frame["cost"].sum()),
        "n_minutes": elapsed, "n_hours": elapsed / 60.0,
        "n_observations": len(frame), "n_days": len(daily),
        "terminal_log_equity": terminal_log, "equity_underflow_count": underflow_count,
        "alpha_annual": None, "beta": None, "alpha_tstat": None, "alpha_pvalue": None,
        "alpha_ci_low": None, "alpha_ci_high": None, "beta_ci_low": None, "beta_ci_high": None,
    }
    if benchmark_minute is not None:
        if not isinstance(benchmark_minute, pd.Series):
            raise ValueError("benchmark_minute must be a Series.")
        _validate_index(benchmark_minute.index, require_complete=False)
        benchmark = benchmark_minute.reindex(frame.index)
        benchmark_daily = daily_returns(benchmark)
        if len(daily) >= 3 and benchmark_daily.std(ddof=1) > 1e-15:
            X = sm.add_constant(benchmark_daily.rename("benchmark"), has_constant="add")
            fit = sm.OLS(daily, X).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
            ci = fit.conf_int(alpha=0.05)
            stats.update({"alpha_annual": float(fit.params["const"] * 365), "beta": float(fit.params["benchmark"]),
                "alpha_tstat": float(fit.tvalues["const"]), "alpha_pvalue": float(fit.pvalues["const"]),
                "alpha_ci_low": float(ci.loc["const", 0] * 365), "alpha_ci_high": float(ci.loc["const", 1] * 365),
                "beta_ci_low": float(ci.loc["benchmark", 0]), "beta_ci_high": float(ci.loc["benchmark", 1])})
    for key, value in stats.items():
        if isinstance(value, float) and not np.isfinite(value):
            stats[key] = None
    return stats
