"""Synthetic five-minute tests; no dataset acquisition or research evaluation."""
import numpy as np
import pandas as pd
import pytest

from crypto_intraday_5m.backtest import (
    BacktestResult, apply_costs, candidate_grid, generate_targets,
    observed_asset_returns, simulate,
)

SYMBOLS = ["BTCUSDT", "ETHUSDT", "LTCUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT", "SOLUSDT"]


def panel(start="2022-01-01", end="2022-01-02", trend=False):
    index = pd.date_range(start, end, freq="5min", tz="UTC")
    values = (100 * np.exp(np.arange(len(index))[:, None] * np.linspace(-.001, .001, 8))
              if trend else np.full((len(index), 8), 100.0))
    return pd.DataFrame(values, index=index, columns=SYMBOLS)


def neutral_targets(prices):
    target = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    target.iloc[:, :2] = [.5, -.5]
    return target


def halt_panel():
    prices = panel("2023-03-24", "2023-03-25", trend=True)
    left, right = pd.Timestamp("2023-03-24 11:25", tz="UTC"), pd.Timestamp("2023-03-24 14:05", tz="UTC")
    missing = pd.date_range("2023-03-24 12:45", "2023-03-24 14:00", freq="5min", tz="UTC")
    prices.loc[missing] = np.nan
    prices.attrs = {"bar_minutes": 5, "allowed_missing_endpoints": [t.isoformat() for t in missing],
                    "halt_bridges": [{"start": left.isoformat(), "end": right.isoformat(), "source": "synthetic:venue"}]}
    return prices, left, right


def test_exact_eighteen_predeclared_specs():
    grid = candidate_grid()
    assert len(grid) == len({x["strategy_id"] for x in grid}) == 18
    assert pd.Series([x["family"] for x in grid]).value_counts().to_dict() == {"momentum": 9, "reversal": 9}
    assert all(set(x) == {"strategy_id", "family", "lookback_minutes", "rebalance_minutes"} for x in grid)


@pytest.mark.parametrize("family", ["momentum", "reversal"])
def test_ties_and_incomplete_lookback_remain_cash(family):
    prices = panel()
    targets = generate_targets(prices, family, 30, 5)
    assert not targets.to_numpy().any()
    assert targets.index.equals(prices.index) and targets.columns.equals(prices.columns)


def test_average_ties_neutrality_and_reversal_sign():
    prices = panel(trend=True)
    prices["ETHUSDT"] = prices["BTCUSDT"]
    momentum = generate_targets(prices, "momentum", 5, 5)
    reversal = generate_targets(prices, "reversal", 5, 5)
    assert np.allclose(momentum.sum(axis=1), 0)
    assert np.allclose(momentum.iloc[1:].abs().sum(axis=1), 1)
    np.testing.assert_allclose(momentum.BTCUSDT, momentum.ETHUSDT)
    np.testing.assert_allclose(momentum, -reversal)


@pytest.mark.parametrize("cadence", [5, 15, 60])
def test_rebalance_clock_is_anchored_utc_midnight(cadence):
    prices = panel()
    prices.loc[pd.Timestamp("2022-01-01 00:05", tz="UTC"):] = 100 + np.arange(8)
    prices.loc[pd.Timestamp("2022-01-01 00:10", tz="UTC"):] = 100 + np.arange(7, -1, -1)
    targets = generate_targets(prices, "momentum", 5, cadence)
    changed = targets.index[targets.diff().abs().sum(axis=1) > 1e-12]
    assert ((changed.hour * 60 + changed.minute) % cadence == 0).all()
    if cadence > 5:
        assert not targets.loc[pd.Timestamp("2022-01-01 00:05", tz="UTC")].any()


@pytest.mark.parametrize("family", ["momentum", "reversal"])
def test_future_price_perturbation_does_not_change_past_targets(family):
    prices = panel(trend=True)
    cutoff = pd.Timestamp("2022-01-01 12:00", tz="UTC")
    before = generate_targets(prices, family, 15, 15)
    changed = prices.copy()
    changed.loc[changed.index > cutoff] *= np.linspace(.3, 2, 8)
    after = generate_targets(changed, family, 15, 15)
    pd.testing.assert_frame_equal(before.loc[:cutoff], after.loc[:cutoff])


def test_lag_one_lag_two_and_full_entry_terminal_costs():
    prices = panel(end="2022-01-01 00:10")
    prices.BTCUSDT = [100, 101, 102.01]
    target = neutral_targets(prices)
    one = simulate(prices, target, prices.index[0], prices.index[-1], cost_bps=20, execution_lag=1)
    two = simulate(prices, target, prices.index[0], prices.index[-1], cost_bps=20, execution_lag=2)
    np.testing.assert_allclose(one.frame.gross_return, [.005, .005], atol=1e-14)
    np.testing.assert_allclose(one.frame.turnover, [1, 1])
    np.testing.assert_allclose(one.frame.net_return, [.003, .003], atol=1e-14)
    np.testing.assert_allclose(two.frame.gross_return, [0, .005], atol=1e-14)
    np.testing.assert_allclose(two.frame.turnover, [0, 2])
    assert one.frame.equity.iloc[-1] == pytest.approx(1.003 ** 2)
    assert two.frame.equity.iloc[-1] == pytest.approx(1.001)


def test_single_interval_charges_entry_and_liquidation_exactly_once():
    prices = panel(end="2022-01-01 00:05")
    result = simulate(prices, neutral_targets(prices), prices.index[0], prices.index[-1], 20)
    assert result.frame.turnover.iloc[0] == 2
    assert result.frame.cost.iloc[0] == pytest.approx(.004)
    assert result.frame.drawdown.iloc[0] == pytest.approx(-.004)


def test_target_turnover_does_not_invent_weight_drift_rebalances():
    prices = panel(end="2022-01-01 00:20", trend=True)
    result = simulate(prices, neutral_targets(prices), prices.index[0], prices.index[-1], 20)
    np.testing.assert_allclose(result.frame.turnover, [1, 0, 0, 1])


def test_apply_costs_matches_resimulation_and_never_double_charges():
    prices = panel(trend=True)
    target = generate_targets(prices, "momentum", 5, 15)
    cached = observed_asset_returns(prices)
    gross = simulate(prices, target, prices.index[0], prices.index[-1], 0, asset_returns=cached)
    costly = apply_costs(gross, 20)
    resimulated = simulate(prices, target, prices.index[0], prices.index[-1], 20, asset_returns=cached)
    pd.testing.assert_frame_equal(costly.frame, resimulated.frame)
    pd.testing.assert_frame_equal(apply_costs(costly, 20).frame, costly.frame)
    assert not gross.frame.cost.any()
    assert gross.held_weights is costly.held_weights
    np.testing.assert_allclose(costly.frame.log_equity, np.log1p(costly.frame.net_return).cumsum())


def test_equity_underflow_preserves_log_wealth_and_valid_drawdown():
    index = pd.date_range("2022-01-01 00:05", periods=288 * 2, freq="5min", tz="UTC")
    frame = pd.DataFrame({"gross_return": 0.0, "turnover": 2.0, "interval_minutes": 5}, index=index)
    raw = BacktestResult(frame, pd.DataFrame(0.0, index=index, columns=SYMBOLS))
    result = apply_costs(raw, 4000)  # -80% each bar, all bars still > -100%.
    assert result.frame.equity.iloc[-1] == 0
    assert np.isfinite(result.frame.log_equity).all()
    assert result.frame.log_equity.iloc[-1] == pytest.approx(576 * np.log(.2))
    assert result.frame.drawdown.iloc[-1] == -1


@pytest.mark.parametrize("lag", [1, 2])
def test_real_160_minute_bridge_retains_pre_halt_position(lag):
    prices, left, right = halt_panel()
    targets = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    first = np.array([.5, -.5, 0, 0, 0, 0, 0, 0])
    second = -first
    targets.loc[left - pd.Timedelta(minutes=5):] = first
    targets.loc[left:] = second
    targets.loc[left + pd.Timedelta(minutes=5):] = np.array([0, 0, .5, -.5, 0, 0, 0, 0])
    observed = observed_asset_returns(prices)
    assert observed.attrs["interval_minutes"][right.isoformat()] == 160
    assert len(observed) == 257
    np.testing.assert_allclose(observed.loc[right], prices.loc[right] / prices.loc[left] - 1)
    assert not ((observed.index > left) & (observed.index < right)).any()
    result = simulate(prices, targets, prices.index[0], prices.index[-1], 20, lag, observed)
    expected = second if lag == 1 else first
    np.testing.assert_allclose(result.held_weights.loc[right], expected)
    assert result.frame.loc[right, "gross_return"] == pytest.approx(float((expected * observed.loc[right]).sum()))
    assert not ((result.frame.index > left) & (result.frame.index < right)).any()
    assert result.frame.interval_minutes.sum() == 1440
    assert prices.loc["2023-03-24 12:45"].isna().all()


def test_halt_scores_defer_both_current_and_partial_lookback_endpoints():
    prices, left, right = halt_panel()
    prices.loc[(prices.index > left) & (prices.index < pd.Timestamp("2023-03-24 12:45", tz="UTC"))] *= np.arange(8, 0, -1)
    targets = generate_targets(prices, "momentum", 30, 5)
    for endpoint in pd.date_range(left, right + pd.Timedelta(minutes=25), freq="5min"):
        np.testing.assert_allclose(targets.loc[endpoint], targets.loc[left])
    assert targets.attrs == prices.attrs


def test_hourly_boundary_prices_match_price_aggregation_not_portfolio_claim():
    prices = panel(trend=True)
    hourly = prices.resample("h", closed="right", label="right").last()
    direct = prices.loc[prices.index.minute == 0]
    np.testing.assert_allclose(hourly, direct)
    asset_return = observed_asset_returns(prices).BTCUSDT
    compounded = (1 + asset_return).resample("h", closed="right", label="right").prod() - 1
    np.testing.assert_allclose(compounded, direct.BTCUSDT.pct_change().iloc[1:], atol=1e-14)
    # No assertion equates a rebalanced 5m portfolio to an hourly portfolio.


@pytest.mark.parametrize("problem", ["unknown_nan", "partial_nan", "negative", "nonfinite", "compressed_gap"])
def test_unknown_or_malformed_prices_fail(problem):
    prices = panel()
    if problem == "unknown_nan": prices.iloc[5] = np.nan
    elif problem == "partial_nan":
        prices, _, _ = halt_panel(); prices.loc["2023-03-24 12:45", "ETHUSDT"] = 100
    elif problem == "negative": prices.iloc[5, 0] = 0
    elif problem == "nonfinite": prices.iloc[5, 0] = np.inf
    else: prices = prices.drop(prices.index[5])
    with pytest.raises(ValueError): observed_asset_returns(prices)


@pytest.mark.parametrize("kwargs", [{"family": "other"}, {"lookback_minutes": 10},
                                     {"rebalance_minutes": 30}, {"lookback_minutes": True}])
def test_invalid_signal_parameters_fail(kwargs):
    arguments = {"family": "momentum", "lookback_minutes": 5, "rebalance_minutes": 5}
    arguments.update(kwargs)
    with pytest.raises(ValueError): generate_targets(panel(), **arguments)


def test_unknown_cached_intervals_and_halt_window_boundaries_fail():
    prices, left, right = halt_panel()
    targets = neutral_targets(prices)
    returns = observed_asset_returns(prices)
    broken = returns.copy(); broken.attrs = {}
    with pytest.raises(ValueError): simulate(prices, targets, prices.index[0], prices.index[-1], asset_returns=broken)
    with pytest.raises(ValueError): simulate(prices, targets, left + pd.Timedelta(minutes=5), right)
    with pytest.raises(ValueError): simulate(prices, targets, left, right - pd.Timedelta(minutes=5))


@pytest.mark.parametrize("kind", ["overlap", "cross_day", "unsourced", "missing_endpoint"])
def test_invalid_declared_halt_policy_fails(kind):
    prices, left, right = halt_panel()
    if kind == "overlap":
        prices.attrs["halt_bridges"].append({"start": (left + pd.Timedelta(minutes=5)).isoformat(),
                                            "end": right.isoformat(), "source": "synthetic:venue"})
    elif kind == "cross_day":
        prices.attrs["halt_bridges"] = [{"start": "2023-03-24T23:55:00+00:00",
            "end": "2023-03-25T00:05:00+00:00", "source": "synthetic:venue"}]
    elif kind == "unsourced": prices.attrs["halt_bridges"][0]["source"] = ""
    else: prices.attrs["halt_bridges"][0]["start"] = "2023-03-23T11:25:00+00:00"
    with pytest.raises(ValueError): observed_asset_returns(prices)


def test_cached_impossible_asset_return_wrong_metadata_and_target_grid_fail():
    prices = panel(end="2022-01-01 00:15")
    target = neutral_targets(prices)
    returns = observed_asset_returns(prices)
    returns.iloc[0, 0] = -1.0
    with pytest.raises(ValueError): simulate(prices, target, prices.index[0], prices.index[-1], asset_returns=returns)
    prices.attrs["bar_minutes"] = 60
    with pytest.raises(ValueError): observed_asset_returns(prices)
    prices.attrs = {}
    with pytest.raises(ValueError): simulate(prices, target.iloc[1:], prices.index[0], prices.index[-1])
    with pytest.raises(ValueError): simulate(prices, target, "2022-01-01 00:03", prices.index[-1])


@pytest.mark.parametrize("cost", [np.nan, np.inf, -1, True])
def test_invalid_costs_fail(cost):
    prices = panel(end="2022-01-01 00:05")
    with pytest.raises(ValueError): simulate(prices, neutral_targets(prices), prices.index[0], prices.index[-1], cost)


def test_insolvent_bar_is_not_disguised_by_log_wealth():
    prices = panel(end="2022-01-01 00:05")
    with pytest.raises(ValueError, match="<= -1"):
        simulate(prices, neutral_targets(prices), prices.index[0], prices.index[-1], cost_bps=5000)
