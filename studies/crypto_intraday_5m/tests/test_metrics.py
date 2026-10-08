"""Synthetic elapsed-minute, daily-compounding and attribution tests."""
import numpy as np
import pandas as pd
import pytest

from crypto_intraday_5m.backtest import BacktestResult, apply_costs
from crypto_intraday_5m.metrics import daily_returns, summarize


def result_from_daily(days, start="2022-01-01"):
    index = pd.date_range(pd.Timestamp(start, tz="UTC") + pd.Timedelta(minutes=5),
                          periods=len(days) * 288, freq="5min")
    values = np.repeat(np.expm1(np.log1p(np.asarray(days)) / 288), 288)
    frame = pd.DataFrame({"gross_return": values, "turnover": 0.0, "interval_minutes": 5}, index=index)
    return apply_costs(BacktestResult(frame, pd.DataFrame(0.0, index=index, columns=["BTCUSDT"])), 0)


def test_daily_compounding_288_bars_and_midnight_previous_day():
    result = result_from_daily([.02, -.03, .01])
    observed = daily_returns(result.frame.net_return)
    np.testing.assert_allclose(observed, [.02, -.03, .01], atol=1e-13)
    assert observed.index.equals(pd.date_range("2022-01-01", periods=3, freq="D", tz="UTC", name="day"))
    stats = summarize(result)
    assert stats["n_minutes"] == 4320 and stats["n_hours"] == 72.0
    assert stats["n_observations"] == 864 and stats["n_days"] == 3


def test_daily_metrics_use_365_not_bar_count_and_positive_drawdown():
    daily = np.array([.01, -.02, .03, -.015])
    result = result_from_daily(daily)
    stats = summarize(result)
    assert stats["annual_return"] == pytest.approx(daily.mean() * 365)
    assert stats["annual_volatility"] == pytest.approx(daily.std(ddof=1) * np.sqrt(365))
    assert stats["sharpe"] == pytest.approx(daily.mean() / daily.std(ddof=1) * np.sqrt(365))
    assert stats["total_return"] == pytest.approx(np.prod(1 + daily) - 1)
    assert stats["cagr"] == pytest.approx(np.expm1(np.log1p(daily).sum() * 365 / len(daily)))
    assert stats["max_drawdown"] > 0
    assert stats["max_drawdown"] == pytest.approx(-result.frame.drawdown.min())


def test_allcash_sharpe_is_undefined_not_zero():
    stats = summarize(result_from_daily([0, 0, 0]))
    assert stats["total_return"] == stats["annual_return"] == stats["annual_volatility"] == 0
    assert stats["sharpe"] is None and stats["max_drawdown"] == 0
    assert stats["terminal_log_equity"] == 0 and stats["equity_underflow_count"] == 0


def test_one_day_volatility_and_sharpe_undefined():
    stats = summarize(result_from_daily([.01]))
    assert stats["annual_volatility"] is None and stats["sharpe"] is None


def test_160_minute_bridge_compounds_once_and_tiles_day():
    result = result_from_daily([.03])
    minute = result.frame.net_return.copy()
    left, right = pd.Timestamp("2022-01-01 11:25", tz="UTC"), pd.Timestamp("2022-01-01 14:05", tz="UTC")
    window = (minute.index > left) & (minute.index <= right)
    actual = np.prod(1 + minute.loc[window]) - 1
    minute.loc[right] = actual
    minute = minute.loc[~((minute.index > left) & (minute.index < right))].copy()
    minute.attrs = {"interval_minutes": {right.isoformat(): 160}}
    assert len(minute) == 257
    assert daily_returns(minute).iloc[0] == pytest.approx(.03)
    gross = pd.DataFrame({"gross_return": minute, "turnover": 0.0,
                          "interval_minutes": [160 if t == right else 5 for t in minute.index]})
    gross.attrs = minute.attrs.copy()
    sparse_result = apply_costs(BacktestResult(gross, pd.DataFrame(0.0, index=minute.index, columns=["BTCUSDT"])), 0)
    stats = summarize(sparse_result, minute)
    assert stats["n_minutes"] == 1440 and stats["n_observations"] == 257
    assert stats["n_hours"] == 24.0 and stats["total_return"] == pytest.approx(.03)


def test_ols_alpha_beta_match_known_daily_relationship_and_hac_ci():
    benchmark_daily = np.array([.01, -.015, .02, -.01, .005, .012, -.007, .003, .016, -.009])
    result = result_from_daily(.001 + .4 * benchmark_daily)
    benchmark = result_from_daily(benchmark_daily).frame.net_return
    stats = summarize(result, benchmark)
    assert stats["beta"] == pytest.approx(.4, abs=1e-10)
    assert stats["alpha_annual"] == pytest.approx(.365, abs=1e-10)
    assert stats["alpha_ci_low"] <= stats["alpha_annual"] <= stats["alpha_ci_high"]
    assert stats["beta_ci_low"] <= stats["beta"] <= stats["beta_ci_high"]


def test_nonzero_noise_hac_seven_matches_independent_statsmodels():
    import statsmodels.api as sm
    rng = np.random.default_rng(107)
    market = rng.normal(0, .02, 60)
    strategy = .0003 + .2 * market + rng.normal(0, .005, 60)
    result = result_from_daily(strategy)
    benchmark = result_from_daily(market).frame.net_return
    stats = summarize(result, benchmark)
    fit = sm.OLS(strategy, sm.add_constant(market)).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
    ci = fit.conf_int(alpha=.05)
    assert stats["alpha_annual"] == pytest.approx(fit.params[0] * 365, abs=1e-10)
    assert stats["beta"] == pytest.approx(fit.params[1], abs=1e-10)
    np.testing.assert_allclose([stats["alpha_ci_low"], stats["alpha_ci_high"]], ci[0] * 365, atol=1e-10)
    np.testing.assert_allclose([stats["beta_ci_low"], stats["beta_ci_high"]], ci[1], atol=1e-10)


def test_underflow_is_not_fake_bankruptcy_and_cagr_uses_log_duration():
    index = pd.date_range("2022-01-01 00:05", periods=576, freq="5min", tz="UTC")
    gross = pd.DataFrame({"gross_return": 0.0, "turnover": 2.0, "interval_minutes": 5}, index=index)
    result = apply_costs(BacktestResult(gross, pd.DataFrame(0.0, index=index, columns=["BTCUSDT"])), 4000)
    stats = summarize(result)
    assert stats["total_return"] == stats["cagr"] == -1
    assert stats["terminal_log_equity"] == pytest.approx(576 * np.log(.2))
    assert stats["equity_underflow_count"] > 0
    assert stats["max_drawdown"] == 1 and stats["n_days"] == 2


@pytest.mark.parametrize("problem", ["partial_day", "unknown_gap", "bad_duration", "cross_day", "bankrupt", "nonfinite"])
def test_incomplete_or_invalid_interval_days_fail(problem):
    minute = result_from_daily([.01, .02]).frame.net_return.copy()
    if problem == "partial_day": minute = minute.iloc[1:]
    elif problem == "unknown_gap": minute = minute.drop(minute.index[30])
    elif problem == "bad_duration": minute.attrs = {"interval_minutes": {minute.index[30].isoformat(): 7}}
    elif problem == "cross_day": minute.attrs = {"interval_minutes": {minute.index[0].isoformat(): 10}}
    elif problem == "bankrupt": minute.iloc[20] = -1
    else: minute.iloc[20] = np.nan
    with pytest.raises(ValueError): daily_returns(minute)


def test_benchmark_missing_or_duplicate_returns_fail():
    result = result_from_daily([.01, .02, -.01])
    missing = result.frame.net_return.drop(result.frame.index[10])
    with pytest.raises(ValueError): summarize(result, missing)
    duplicate = pd.concat([result.frame.net_return, result.frame.net_return.iloc[:1]]).sort_index()
    with pytest.raises(ValueError): summarize(result, duplicate)
