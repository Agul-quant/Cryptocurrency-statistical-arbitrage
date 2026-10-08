import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from crypto_stat_arb.backtest import BacktestResult, generate_targets, observed_asset_returns, simulate
from crypto_stat_arb.metrics import daily_returns, summarize


def hourly_from_daily(values):
    """Put each daily return in its final hourly interval for exact fixtures."""
    index = pd.date_range("2024-01-01 01:00", periods=len(values) * 24, freq="h", tz="UTC")
    hourly = pd.Series(0.0, index=index, name="net_return")
    hourly.iloc[23::24] = values
    return hourly


def result_from_hourly(hourly):
    equity = (1 + hourly).cumprod()
    frame = pd.DataFrame({"gross_return": hourly, "net_return": hourly,
                          "turnover": 0.0, "cost": 0.0, "equity": equity,
                          "drawdown": equity / equity.cummax().clip(lower=1) - 1})
    return BacktestResult(frame, pd.DataFrame(0.0, index=hourly.index, columns=["A"]))


def test_midnight_endpoint_belongs_to_preceding_day_and_compounds():
    hourly = hourly_from_daily([0.01, -0.02, 0.03])
    daily = daily_returns(hourly)
    np.testing.assert_allclose(daily, [0.01, -0.02, 0.03])
    assert daily.index[0] == pd.Timestamp("2024-01-01", tz="UTC")
    assert daily.index[-1] == pd.Timestamp("2024-01-03", tz="UTC")
    constant = pd.Series(0.001, index=hourly.index)
    np.testing.assert_allclose(daily_returns(constant), (1.001 ** 24) - 1)


@pytest.mark.parametrize("kind", ["partial", "missing", "nonfinite", "bankrupt"])
def test_daily_aggregation_rejects_bad_or_partial_days(kind):
    hourly = hourly_from_daily([0.01, 0.02])
    if kind == "partial":
        hourly = hourly.iloc[1:]
    elif kind == "missing":
        hourly = hourly.drop(hourly.index[12])
    elif kind == "nonfinite":
        hourly.iloc[1] = np.nan
    else:
        hourly.iloc[1] = -1
    with pytest.raises(ValueError):
        daily_returns(hourly)


def test_known_arithmetic_compounded_metrics_and_drawdown():
    days = np.array([0.01, -0.02, 0.03])
    stats = summarize(result_from_hourly(hourly_from_daily(days)))
    terminal = np.prod(1 + days)
    assert stats["n_days"] == 3
    assert stats["n_hours"] == 72
    assert stats["total_return"] == pytest.approx(terminal - 1)
    assert stats["annual_return"] == pytest.approx(days.mean() * 365)
    assert stats["annual_volatility"] == pytest.approx(days.std(ddof=1) * np.sqrt(365))
    assert stats["sharpe"] == pytest.approx(days.mean() / days.std(ddof=1) * np.sqrt(365))
    assert stats["cagr"] == pytest.approx(terminal ** (365 / 3) - 1)
    assert stats["max_drawdown"] == pytest.approx(0.02)
    assert stats["alpha_annual"] is None


def test_flat_returns_have_unavailable_sharpe_not_infinity():
    stats = summarize(result_from_hourly(hourly_from_daily([0, 0, 0])))
    assert stats["sharpe"] is None
    assert stats["annual_volatility"] == 0
    assert stats["total_return"] == 0
    assert stats["cagr"] == 0
    assert stats["max_drawdown"] == 0


def test_hac7_alpha_beta_and_confidence_intervals_match_reference():
    x = np.sin(np.arange(60) / 3) * 0.02
    y = 0.001 + 1.5 * x + np.cos(np.arange(60) / 4) * 0.001
    hourly = hourly_from_daily(y)
    benchmark = hourly_from_daily(x)
    stats = summarize(result_from_hourly(hourly), benchmark)
    daily_y = daily_returns(hourly)
    daily_x = daily_returns(benchmark).rename("benchmark")
    fit = sm.OLS(daily_y, sm.add_constant(daily_x, has_constant="add")).fit(
        cov_type="HAC", cov_kwds={"maxlags": 7})
    ci = fit.conf_int()
    assert stats["alpha_annual"] == pytest.approx(fit.params["const"] * 365)
    assert stats["beta"] == pytest.approx(fit.params["benchmark"])
    assert stats["alpha_tstat"] == pytest.approx(fit.tvalues["const"])
    assert stats["alpha_pvalue"] == pytest.approx(fit.pvalues["const"])
    assert stats["alpha_ci_low"] == pytest.approx(ci.loc["const", 0] * 365)
    assert stats["alpha_ci_high"] == pytest.approx(ci.loc["const", 1] * 365)
    assert stats["beta_ci_low"] == pytest.approx(ci.loc["benchmark", 0])
    assert stats["beta_ci_high"] == pytest.approx(ci.loc["benchmark", 1])


def test_full_history_benchmark_is_subset_and_missing_observation_fails():
    y = hourly_from_daily([0.01, -0.01, 0.02])
    x = hourly_from_daily([0.02, -0.01, 0.04])
    prefix = pd.Series([np.nan], index=pd.DatetimeIndex([x.index[0] - pd.Timedelta(hours=1)]))
    stats = summarize(result_from_hourly(y), pd.concat([prefix, x]))
    assert stats["beta"] is not None
    with pytest.raises(ValueError, match="finite"):
        summarize(result_from_hourly(y), x.drop(x.index[10]))


def test_constant_benchmark_has_unavailable_attribution():
    y = hourly_from_daily([0.01, -0.01, 0.02])
    x = hourly_from_daily([0, 0, 0])
    stats = summarize(result_from_hourly(y), x)
    assert stats["alpha_annual"] is None
    assert stats["beta"] is None


def test_turnover_and_cost_summaries_are_arithmetic_totals():
    result = result_from_hourly(hourly_from_daily([0.01, -0.01, 0.02]))
    result.frame.loc[result.frame.index[0], "turnover"] = 1
    result.frame.loc[result.frame.index[12], "turnover"] = 2
    result.frame.loc[result.frame.index[-1], "turnover"] = 1
    result.frame["cost"] = result.frame["turnover"] * 0.002
    stats = summarize(result)
    assert stats["total_turnover"] == 4
    assert stats["mean_hourly_turnover"] == pytest.approx(4 / 72)
    assert stats["total_cost_sum"] == pytest.approx(0.008)


def sparse_interval_returns():
    hourly = hourly_from_daily([0.01, -0.02, 0.03])
    endpoint = hourly.index[14]  # 15:00; preceding observed mark is 11:00
    sparse = hourly.drop(hourly.index[11:14])
    sparse.attrs["interval_hours"] = {endpoint.isoformat(): 4}
    return sparse


def test_audited_sparse_intervals_aggregate_24_elapsed_hours_without_zero_fill():
    sparse = sparse_interval_returns()
    assert len(sparse) == 69
    np.testing.assert_allclose(daily_returns(sparse), [0.01, -0.02, 0.03])
    assert sparse.copy().reindex(sparse.index).attrs == sparse.attrs
    result = result_from_hourly(sparse)
    result.frame.attrs = sparse.attrs.copy()
    result.frame["interval_hours"] = 1
    result.frame.loc[pd.Timestamp("2024-01-01 15:00", tz="UTC"), "interval_hours"] = 4
    result.frame.loc[result.frame.index[0], "turnover"] = 1
    result.frame.loc[result.frame.index[-1], "turnover"] = 1
    stats = summarize(result, sparse)
    assert stats["n_hours"] == 72
    assert stats["n_observations"] == 69
    assert stats["mean_hourly_turnover"] == pytest.approx(2 / 72)
    assert stats["cagr"] == pytest.approx(np.prod([1.01, 0.98, 1.03]) ** (365 / 3) - 1)
    assert stats["beta"] == pytest.approx(1)


@pytest.mark.parametrize("bad", ["no_metadata", "wrong_duration", "incomplete_day", "cross_midnight"])
def test_sparse_interval_metadata_must_cover_complete_days_contiguously(bad):
    sparse = sparse_interval_returns()
    if bad == "no_metadata":
        sparse.attrs.clear()
    elif bad == "wrong_duration":
        sparse.attrs["interval_hours"]["2024-01-01T15:00:00+00:00"] = 3
    elif bad == "incomplete_day":
        sparse = sparse.iloc[1:]
    else:
        # An explicit four-hour interval ending at 02:00 crosses midnight.
        sparse = hourly_from_daily([0.01, 0.02])
        endpoint = pd.Timestamp("2024-01-02 02:00", tz="UTC")
        sparse = sparse.drop(pd.date_range("2024-01-01 23:00", periods=3, freq="h", tz="UTC"))
        sparse.attrs["interval_hours"] = {endpoint.isoformat(): 4}
    with pytest.raises(ValueError):
        daily_returns(sparse)


def test_real_bridge_simulation_and_benchmark_attribution_integrate():
    index = pd.date_range("2023-03-24", periods=73, freq="h", tz="UTC")
    px = pd.DataFrame({"A": 100 * np.exp(np.arange(73) * 0.001),
                       "B": 100 * np.exp(-np.arange(73) * 0.001)}, index=index)
    px.iloc[14] = np.nan
    px.attrs = {"allowed_missing_endpoints": [index[14].isoformat()],
                "halt_bridges": [{"start": index[11].isoformat(), "end": index[15].isoformat(),
                                  "source": "https://example.com/audited-halt"}]}
    targets = generate_targets(px, "momentum", 1, 1)
    result = simulate(px, targets, index[0], index[-1])
    benchmark = observed_asset_returns(px)["A"]
    stats = summarize(result, benchmark)
    assert stats["n_hours"] == 72
    assert stats["n_observations"] == 69
    assert stats["n_days"] == 3
    assert np.isfinite(stats["total_return"])
