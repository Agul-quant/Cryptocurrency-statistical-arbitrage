import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from crypto_stat_arb.backtest import generate_targets, observed_asset_returns, simulate
from extended_backtest import SCHEDULE_EPOCH, generate_scaled_targets


def synthetic_prices(n=1000, start="2022-01-01 00:00", seed=42):
    index = pd.date_range(start, periods=n, freq="h", tz="UTC", name="bar_end")
    rng = np.random.default_rng(seed)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.004, (n, 4)), axis=0)),
                        index=index, columns=["A", "B", "C", "D"])


@pytest.mark.parametrize("family", ["momentum", "reversal"])
@pytest.mark.parametrize("cadence", [1, 4, 24])
@pytest.mark.parametrize("lookback", [1, 24, 168])
def test_existing_schedule_phase_zero_parity(family, cadence, lookback):
    prices = synthetic_prices(start="2021-12-01 01:00")
    expected = generate_targets(prices, family, lookback, cadence)
    actual = generate_scaled_targets(prices, family, lookback, cadence)
    assert_frame_equal(actual, expected)


@pytest.mark.parametrize("cadence", [1, 4, 12, 24, 72, 168])
def test_momentum_and_reversal_are_opposites_and_neutral(cadence):
    prices = synthetic_prices()
    momentum = generate_scaled_targets(prices, "momentum", 12, cadence)
    reversal = generate_scaled_targets(prices, "reversal", 12, cadence)
    np.testing.assert_allclose(momentum, -reversal)
    np.testing.assert_allclose(momentum.sum(axis=1), 0, atol=1e-15)
    exposure = momentum.abs().sum(axis=1)
    assert ((exposure == 0) | np.isclose(exposure, 1)).all()


@pytest.mark.parametrize("cadence", [72, 168])
def test_multiday_rebalances_use_elapsed_hours_not_hour_of_day(cadence):
    prices = synthetic_prices()
    targets = generate_scaled_targets(prices, "momentum", 1, cadence)
    first = SCHEDULE_EPOCH
    second = first + pd.Timedelta(hours=cadence)
    assert targets.loc[first].abs().sum() == pytest.approx(1)
    assert targets.loc[second].abs().sum() == pytest.approx(1)
    between = targets.loc[(targets.index >= first) & (targets.index < second)]
    np.testing.assert_allclose(between, np.tile(targets.loc[first], (len(between), 1)))
    elapsed = ((prices.index - SCHEDULE_EPOCH) / pd.Timedelta(hours=1)).to_numpy(dtype=int)
    unscheduled = elapsed % cadence != 0
    np.testing.assert_allclose(targets.diff().fillna(0).loc[unscheduled], 0)
    if cadence == 168:
        decisions = prices.index[elapsed % cadence == 0]
        assert (decisions.weekday == 0).all()
    else:
        decisions = prices.index[elapsed % cadence == 0]
        assert len(set(decisions.weekday)) > 1  # three-day cadence moves through weekdays


@pytest.mark.parametrize("cadence,phase", [(24, 6), (24, 18), (72, 24), (168, 24), (168, 144)])
def test_phase_offsets_are_real_utc_schedules(cadence, phase):
    prices = synthetic_prices(n=2000)
    targets = generate_scaled_targets(prices, "momentum", 1, cadence, phase_hours=phase)
    elapsed = ((prices.index - SCHEDULE_EPOCH) / pd.Timedelta(hours=1)).to_numpy(dtype=int)
    scheduled = (elapsed - phase) % cadence == 0
    np.testing.assert_allclose(targets.diff().fillna(0).loc[~scheduled], 0)
    expected = SCHEDULE_EPOCH + pd.Timedelta(hours=phase)
    assert targets.loc[expected].abs().sum() == pytest.approx(1)
    if cadence == 168 and phase == 24:
        assert (prices.index[scheduled].weekday == 1).all()  # Tuesday, not Monday
    if cadence == 24:
        assert (prices.index[scheduled].hour == phase).all()


def test_nanosecond_and_microsecond_storage_have_identical_schedule():
    prices = synthetic_prices()
    microseconds = prices.copy()
    microseconds.index = microseconds.index.as_unit("us")
    expected = generate_scaled_targets(prices, "momentum", 24, 168)
    actual = generate_scaled_targets(microseconds, "momentum", 24, 168)
    np.testing.assert_array_equal(expected.to_numpy(), actual.to_numpy())


def test_ninety_day_lookback_warmup_and_common_march_seventh_first_return():
    prices = synthetic_prices(n=2500, start="2021-12-01 01:00")
    hourly = generate_scaled_targets(prices, "momentum", 2160, 1)
    assert (hourly.iloc[:2160] == 0).all().all()
    assert hourly.index[2160] == pd.Timestamp("2022-03-01 01:00", tz="UTC")
    assert hourly.iloc[2160].abs().sum() == pytest.approx(1)
    start = pd.Timestamp("2022-03-07", tz="UTC")
    for cadence in (1, 4, 12, 24, 72, 168):
        targets = generate_scaled_targets(prices, "momentum", 2160, cadence)
        assert targets.loc[start].abs().sum() == pytest.approx(1)
        result = simulate(prices, targets, start, start + pd.Timedelta(days=1), cost_bps=0)
        assert result.held_weights.iloc[0].abs().sum() == pytest.approx(1)
    weekly = generate_scaled_targets(prices, "momentum", 2160, 168)
    delayed = simulate(prices, weekly, start, start + pd.Timedelta(days=1),
                       cost_bps=0, execution_lag=2)
    assert delayed.held_weights.iloc[0].abs().sum() == 0  # prior weekly target lacked history
    assert delayed.held_weights.iloc[1].abs().sum() == pytest.approx(1)


@pytest.mark.parametrize("cadence", [1, 4, 12, 24, 72, 168])
def test_all_ties_are_flat_not_infinite(cadence):
    prices = synthetic_prices()
    prices[:] = 100
    targets = generate_scaled_targets(prices, "momentum", 1, cadence)
    assert (targets == 0).all().all()
    assert np.isfinite(targets.to_numpy()).all()


@pytest.mark.parametrize("cadence", [1, 12, 72, 168])
def test_future_price_changes_do_not_modify_past_targets_or_pnl(cadence):
    prices = synthetic_prices(n=2000)
    targets = generate_scaled_targets(prices, "momentum", 336, cadence)
    changed = prices.copy()
    changed.iloc[1500:, 0] *= 4
    changed.iloc[1500:, 1] *= 0.1
    mutated = generate_scaled_targets(changed, "momentum", 336, cadence)
    assert_frame_equal(targets.iloc[:1500], mutated.iloc[:1500])
    previous = simulate(prices, targets, prices.index[500], prices.index[1499], cost_bps=0)
    subsequent = simulate(changed, mutated, changed.index[500], changed.index[1499], cost_bps=0)
    assert_frame_equal(previous.frame, subsequent.frame)


def halt_prices():
    prices = synthetic_prices(n=97, start="2023-03-23 00:00")
    missing = pd.Timestamp("2023-03-24 14:00", tz="UTC")
    prices.loc[missing] = np.nan
    prices.attrs = {"allowed_missing_endpoints": [missing.isoformat()],
                    "halt_bridges": [{"start": "2023-03-24T11:00:00+00:00",
                                      "end": "2023-03-24T15:00:00+00:00",
                                      "source": "https://www.binance.com/en/blog/from-our-ceo/6789340645608890113"}]}
    return prices


@pytest.mark.parametrize("cadence", [1, 4, 12, 24, 72, 168])
def test_declared_halt_freezes_decisions_and_preserves_real_bridge(cadence):
    prices = halt_prices()
    original = prices.copy()
    targets = generate_scaled_targets(prices, "momentum", 1, cadence)
    before = pd.Timestamp("2023-03-24 11:00", tz="UTC")
    for hour in (12, 13, 14, 15):
        np.testing.assert_array_equal(targets.loc[pd.Timestamp(f"2023-03-24 {hour}:00", tz="UTC")],
                                      targets.loc[before])
    result = simulate(prices, targets, prices.index[0], prices.index[-1], cost_bps=0)
    endpoint = pd.Timestamp("2023-03-24 15:00", tz="UTC")
    observed = observed_asset_returns(prices)
    expected = ((prices.loc[endpoint] / prices.loc[before] - 1) * targets.loc[before]).sum()
    assert result.frame.loc[endpoint, "gross_return"] == pytest.approx(expected)
    assert result.frame.loc[endpoint, "interval_hours"] == 4
    for hour in (12, 13, 14):
        assert pd.Timestamp(f"2023-03-24 {hour}:00", tz="UTC") not in observed.index
    assert_frame_equal(prices, original)
    assert prices.loc[pd.Timestamp("2023-03-24 14:00", tz="UTC")].isna().all()


def test_undeclared_missing_prices_do_not_get_filled():
    prices = synthetic_prices()
    prices.iloc[100] = np.nan
    with pytest.raises(ValueError, match="explicit"):
        generate_scaled_targets(prices, "momentum", 1, 72)


@pytest.mark.parametrize("kwargs", [{"lookback_h": 0}, {"rebalance_h": 48},
                                    {"phase_hours": -1}, {"phase_hours": 24},
                                    {"phase_hours": 1.5}, {"phase_hours": True},
                                    {"family": "trend"}])
def test_invalid_parameters_fail(kwargs):
    parameters = {"family": "momentum", "lookback_h": 24, "rebalance_h": 24}
    parameters.update(kwargs)
    with pytest.raises(ValueError):
        generate_scaled_targets(synthetic_prices(), **parameters)
