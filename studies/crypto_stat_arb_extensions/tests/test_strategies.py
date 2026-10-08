"""Pure synthetic strategy tests; never open downloaded holdout prices."""
import numpy as np
import pandas as pd
import pytest

from crypto_stat_arb_extensions.strategies import candidate_grid, generate_targets


SYMBOLS = ["BTCUSDT", "ETHUSDT", "LTCUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT", "SOLUSDT"]


def panel(start="2021-12-01", end="2022-02-01"):
    index = pd.date_range(start, end, freq="h", tz="UTC")
    return pd.DataFrame(100.0, index=index, columns=SYMBOLS)


def spec(family="cross_momentum", lookback=336, cadence=24, buffer=0.0):
    return {"family": family, "lookback_h": lookback, "rebalance_h": cadence, "buffer_l1": buffer}


def test_predeclared_grid_is_exactly_seventeen_unique_specs():
    grid = candidate_grid()
    assert len(grid) == len({s["strategy_id"] for s in grid}) == 17
    assert pd.Series([s["family"] for s in grid]).value_counts().to_dict() == {
        "cross_momentum": 8, "trend_long_cash": 4, "trend_long_short": 4, "factor_residual": 1}
    assert all(set(s) == {"strategy_id", "family", "lookback_h", "rebalance_h", "buffer_l1"} for s in grid)


@pytest.mark.parametrize("family", ["cross_momentum", "trend_long_cash", "trend_long_short"])
def test_all_equal_prices_and_incomplete_warmup_stay_cash(family):
    prices = panel()
    result = generate_targets(prices, spec(family))
    assert not result.to_numpy().any()
    assert result.index.equals(prices.index)
    assert result.columns.equals(prices.columns)


def test_whole_buffer_skips_single_rank_swap_but_accepts_threshold_equality():
    prices = panel(end="2022-01-05")
    prices.loc["2022-01-01":] = 100 + np.arange(1, 9)
    prices.loc["2022-01-02":] = 100 + np.array([2, 1, 3, 4, 5, 6, 7, 8])
    prices.loc["2022-01-03":] = 100 + np.array([2, 1, 4, 3, 5, 6, 7, 8])
    plain = generate_targets(prices, spec())
    buffered = generate_targets(prices, spec(buffer=0.25))
    t1, t2, t3 = [pd.Timestamp(f"2022-01-0{d}", tz="UTC") for d in (1, 2, 3)]
    assert np.abs(plain.loc[t2] - plain.loc[t1]).sum() == pytest.approx(0.125)
    assert np.abs(plain.loc[t3] - plain.loc[t1]).sum() == pytest.approx(0.25)
    np.testing.assert_allclose(buffered.loc[t2], buffered.loc[t1])
    np.testing.assert_allclose(buffered.loc[t3], plain.loc[t3])
    assert np.allclose(buffered.sum(axis=1), 0)
    assert buffered.abs().sum(axis=1).isin([0.0, 1.0]).all()


def test_weekly_means_monday_midnight_not_every_midnight():
    prices = panel(end="2022-01-18")
    prices.loc["2022-01-03":] = 100 + np.arange(1, 9)
    prices.loc["2022-01-04":] = 100 + np.arange(8, 0, -1)
    result = generate_targets(prices, spec(cadence=168))
    monday = pd.Timestamp("2022-01-03", tz="UTC")
    next_monday = monday + pd.Timedelta(days=7)
    expected = result.loc[monday]
    for time in pd.date_range(monday, next_monday - pd.Timedelta(hours=1), freq="h"):
        np.testing.assert_allclose(result.loc[time], expected)
    assert not np.allclose(result.loc[next_monday], expected)
    changes = result.diff().abs().sum(axis=1) > 1e-12
    changed = result.index[changes]
    assert (changed.dayofweek == 0).all() and (changed.hour == 0).all()


@pytest.mark.parametrize("family", ["trend_long_cash", "trend_long_short"])
def test_own_trend_is_fixed_one_eighth_not_cross_sectional_rank(family):
    prices = panel(end="2022-01-04")
    prices.loc["2022-01-01":] = [120, 110, 100, 90, 80, 70, 60, 50]
    result = generate_targets(prices, spec(family))
    expected = np.array([1, 1, 0, 0, 0, 0, 0, 0] if family == "trend_long_cash"
                        else [1, 1, 0, -1, -1, -1, -1, -1]) / 8
    np.testing.assert_allclose(result.loc[pd.Timestamp("2022-01-01", tz="UTC")], expected)
    assert (result.abs().sum(axis=1) <= 1 + 1e-12).all()


def test_long_cash_does_not_rescale_remaining_positive_names():
    prices = panel(end="2022-01-04")
    prices.loc["2022-01-01":] = [110, 90, 90, 90, 90, 90, 90, 90]
    result = generate_targets(prices, spec("trend_long_cash"))
    assert result.loc[pd.Timestamp("2022-01-01", tz="UTC")].abs().sum() == 0.125


@pytest.mark.parametrize("family", ["cross_momentum", "trend_long_cash", "trend_long_short"])
def test_future_changes_do_not_change_past_targets(family):
    prices = panel()
    hours = np.arange(len(prices))[:, None]
    prices[:] = 100 * np.exp(hours * np.linspace(-0.0002, 0.0003, 8))
    before = generate_targets(prices, spec(family))
    boundary = pd.Timestamp("2022-01-20", tz="UTC")
    modified = prices.copy()
    modified.loc[modified.index > boundary] *= np.linspace(0.5, 3.0, 8)
    after = generate_targets(modified, spec(family))
    pd.testing.assert_frame_equal(before.loc[:boundary], after.loc[:boundary])


def test_declared_halt_is_preserved_and_no_target_changes_inside_it():
    prices = panel(end="2022-01-05")
    start, end = pd.Timestamp("2022-01-02 00:00", tz="UTC"), pd.Timestamp("2022-01-02 04:00", tz="UTC")
    missing = start + pd.Timedelta(hours=2)
    prices.loc[missing] = np.nan
    prices.attrs = {"allowed_missing_endpoints": [missing.isoformat()],
                    "halt_bridges": [{"start": start.isoformat(), "end": end.isoformat(), "source": "synthetic:test"}]}
    prices.loc["2022-01-01":] = 100 + np.arange(1, 9)
    prices.loc[missing] = np.nan
    result = generate_targets(prices, spec(buffer=0.25))
    assert result.attrs == prices.attrs
    for time in pd.date_range(start, end, freq="h"):
        np.testing.assert_allclose(result.loc[time], result.loc[start])
    assert prices.loc[missing].isna().all()


@pytest.mark.parametrize("change", [{"lookback_h": 24}, {"rebalance_h": 72}, {"buffer_l1": 0.5},
                                    {"lookback_h": True}, {"family": "factor_residual"}])
def test_invalid_or_unplanned_specs_fail(change):
    candidate = spec()
    candidate.update(change)
    with pytest.raises(ValueError):
        generate_targets(panel(), candidate)


def test_trend_buffer_and_wrong_universe_rejected():
    with pytest.raises(ValueError):
        generate_targets(panel(), spec("trend_long_short", buffer=0.25))
    with pytest.raises(ValueError):
        generate_targets(panel().iloc[:, :7], spec())
