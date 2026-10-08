import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from crypto_stat_arb.backtest import generate_targets, observed_asset_returns, simulate


def prices(n=49, assets=("A", "B")):
    return pd.DataFrame(
        100.0,
        index=pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"),
        columns=list(assets),
    )


def test_rank_ties_neutrality_and_reversal():
    px = prices(4, ("A", "B", "C", "D"))
    px.iloc[1] = [110, 110, 100, 90]
    px.iloc[2] = [121, 121, 100, 81]
    momentum = generate_targets(px, "momentum", 1, 1)
    reversal = generate_targets(px, "reversal", 1, 1)
    np.testing.assert_allclose(momentum.iloc[1], [0.25, 0.25, -0.125, -0.375])
    np.testing.assert_allclose(reversal, -momentum)
    np.testing.assert_allclose(momentum.sum(axis=1), 0, atol=1e-15)
    np.testing.assert_allclose(momentum.abs().sum(axis=1).iloc[1:], 1)
    assert (momentum.iloc[0] == 0).all()


def test_all_equal_scores_and_incomplete_warmup_are_flat():
    px = prices()
    assert (generate_targets(px, "momentum", 168, 4) == 0).all().all()
    assert (generate_targets(px, "reversal", 1, 1) == 0).all().all()


def test_rebalance_phase_and_hold():
    px = prices(10)
    px["A"] = 100 + np.arange(10)
    px["B"] = 100 - np.arange(10)
    px.loc[px.index[5], "B"] = 120
    targets = generate_targets(px, "momentum", 1, 4)
    assert (targets.iloc[:4] == 0).all().all()
    np.testing.assert_allclose(targets.iloc[4], [0.5, -0.5])
    for hour in (5, 6, 7):
        np.testing.assert_array_equal(targets.iloc[hour], targets.iloc[4])


def test_lookback_is_price_ratio_not_arithmetic_hourly_mean():
    px = prices(4)
    px["A"] = [100, 200, 120, 120]
    px["B"] = [100, 105, 110.25, 110.25]
    # A's trailing total return (20%) exceeds B's (10.25%), despite reversal
    # during A's last hour. Both full two-hour lookback and sign are explicit.
    targets = generate_targets(px, "momentum", 2, 1)
    np.testing.assert_allclose(targets.iloc[2], [0.5, -0.5])


def test_no_lookahead_under_future_price_mutation():
    px = prices(100)
    px["A"] = np.exp(np.arange(100) * 0.01)
    px["B"] = np.exp(np.arange(100) * -0.002)
    original = generate_targets(px, "momentum", 12, 4)
    changed = px.copy()
    changed.iloc[60:, 0] *= 7
    changed.iloc[60:, 1] *= 0.02
    mutation = generate_targets(changed, "momentum", 12, 4)
    assert_frame_equal(original.iloc[:60], mutation.iloc[:60])
    old = simulate(px, original, px.index[20], px.index[59])
    new = simulate(changed, mutation, changed.index[20], changed.index[59])
    assert_frame_equal(old.frame, new.frame)


def test_entry_flip_exit_costs_and_explicit_lag():
    px = prices(4)
    targets = pd.DataFrame([[0.5, -0.5], [-0.5, 0.5], [-0.5, 0.5], [0.5, -0.5]],
                           index=px.index, columns=px.columns)
    result = simulate(px, targets, px.index[0], px.index[-1])
    np.testing.assert_allclose(result.frame["turnover"], [1, 2, 1])
    np.testing.assert_allclose(result.frame["cost"], [0.002, 0.004, 0.002])
    np.testing.assert_allclose(result.frame["equity"], np.cumprod([0.998, 0.996, 0.998]))
    delayed = simulate(px, targets, px.index[0], px.index[-1], execution_lag=2)
    np.testing.assert_allclose(delayed.held_weights.iloc[0], [0, 0])
    np.testing.assert_allclose(delayed.frame["turnover"], [0, 1, 3])
    reset = simulate(px, targets, px.index[1], px.index[-1])
    np.testing.assert_allclose(reset.frame["turnover"], [1, 1])


def test_return_lag_zero_cost_and_known_drawdown_recovery():
    px = prices(4, ("A",))
    px["A"] = [100, 110, 88, 110]
    targets = pd.DataFrame(1.0, index=px.index, columns=px.columns)
    result = simulate(px, targets, px.index[0], px.index[-1], cost_bps=0)
    np.testing.assert_allclose(result.frame["gross_return"], [0.1, -0.2, 0.25])
    np.testing.assert_allclose(result.frame["net_return"], result.frame["gross_return"])
    np.testing.assert_allclose(result.frame["equity"], [1.1, 0.88, 1.1])
    np.testing.assert_allclose(result.frame["drawdown"], [0, -0.2, 0], atol=1e-15)
    targets.iloc[0] = 0
    lagged = simulate(px, targets, px.index[0], px.index[-1], cost_bps=0)
    assert lagged.frame["gross_return"].iloc[0] == 0
    assert lagged.frame["gross_return"].iloc[1] == pytest.approx(-0.2)


def test_initial_wealth_counts_as_drawdown_peak():
    px = prices(2, ("A",))
    px.iloc[1] = 90
    targets = pd.DataFrame(1.0, index=px.index, columns=px.columns)
    result = simulate(px, targets, px.index[0], px.index[-1], cost_bps=0)
    assert result.frame["drawdown"].iloc[0] == pytest.approx(-0.1)


def test_combined_positions_net_before_turnover_without_renormalization():
    px = prices(25)
    first = pd.DataFrame([0.5, -0.5], index=px.columns).T
    targets = pd.DataFrame(np.tile(first.to_numpy(), (25, 1)), index=px.index, columns=px.columns)
    canceled = 0.5 * targets + 0.5 * -targets
    result = simulate(px, canceled, px.index[0], px.index[-1])
    assert result.frame["turnover"].sum() == 0
    assert result.frame["cost"].sum() == 0
    half = simulate(px, 0.5 * targets, px.index[0], px.index[-1])
    assert half.frame["turnover"].sum() == pytest.approx(1.0)


@pytest.mark.parametrize("mutation", ["nan", "missing_hour", "duplicate", "naive", "zero"])
def test_invalid_prices_fail_without_fabrication(mutation):
    px = prices(25)
    if mutation == "nan":
        px.iloc[12, 0] = np.nan
    elif mutation == "missing_hour":
        px = px.drop(px.index[12])
    elif mutation == "duplicate":
        px = pd.concat([px.iloc[:1], px])
    elif mutation == "naive":
        px.index = px.index.tz_localize(None)
    else:
        px.iloc[12, 0] = 0
    with pytest.raises(ValueError):
        generate_targets(px, "momentum", 1, 1)


def test_missing_targets_and_bankruptcy_fail_explicitly():
    px = prices(2, ("A",))
    targets = pd.DataFrame(np.nan, index=px.index, columns=px.columns)
    with pytest.raises(ValueError, match="finite"):
        simulate(px, targets, px.index[0], px.index[-1])
    targets[:] = -2
    px.iloc[1] = 200
    with pytest.raises(ValueError, match="<= -1"):
        simulate(px, targets, px.index[0], px.index[-1], cost_bps=0)


def test_single_return_charges_entry_and_exit_once_and_preserves_inputs():
    px = prices(2)
    targets = pd.DataFrame([[0.5, -0.5], [0.5, -0.5]], index=px.index, columns=px.columns)
    original_px, original_targets = px.copy(), targets.copy()
    result = simulate(px, targets, px.index[0], px.index[-1])
    assert result.frame["turnover"].iloc[0] == 2
    assert result.frame["net_return"].iloc[0] == pytest.approx(-0.004)
    np.testing.assert_array_equal(result.held_weights.iloc[0], [0.5, -0.5])
    assert_frame_equal(px, original_px)
    assert_frame_equal(targets, original_targets)


@pytest.mark.parametrize("kwargs", [{"cost_bps": -1}, {"cost_bps": np.nan},
                                    {"execution_lag": 0}, {"execution_lag": 1.5}])
def test_invalid_simulation_parameters_fail(kwargs):
    px = prices(2)
    targets = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    with pytest.raises(ValueError):
        simulate(px, targets, px.index[0], px.index[-1], **kwargs)


def test_endpoint_and_target_alignment_validation():
    px = prices(3)
    targets = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    with pytest.raises(ValueError, match="exactly"):
        simulate(px, targets[["B", "A"]], px.index[0], px.index[-1])
    with pytest.raises(ValueError, match="cover"):
        simulate(px, targets, px.index[0] - pd.Timedelta(hours=1), px.index[-1])
    with pytest.raises(ValueError, match="later"):
        simulate(px, targets, px.index[1], px.index[1])


def halt_prices():
    index = pd.date_range("2023-03-24", periods=49, freq="h", tz="UTC")
    px = pd.DataFrame(100.0, index=index, columns=["A", "B"])
    px.iloc[10] = [90, 110]
    px.iloc[11] = [100, 100]
    px.iloc[12:14] = [150, 50]  # audited partial/no-trade source marks, not executions
    px.iloc[14] = np.nan
    px.iloc[15:] = [120, 90]
    px.attrs = {
        "allowed_missing_endpoints": [index[14].isoformat()],
        "halt_bridges": [{"start": index[11].isoformat(), "end": index[15].isoformat(),
                          "source": "https://www.binance.com/en/blog/from-our-ceo/6789340645608890113"}],
    }
    return px


def test_observed_halt_bridge_uses_real_prices_once_and_preserves_missing_input():
    px = halt_prices()
    observed = observed_asset_returns(px)
    assert len(observed) == 45
    assert not observed.index.isin(px.index[12:15]).any()
    np.testing.assert_allclose(observed.loc[px.index[15]], [0.2, -0.1])
    assert observed.attrs["interval_hours"] == {px.index[15].isoformat(): 4}
    assert observed["A"].reindex(observed.index).attrs == observed.attrs
    assert px.iloc[14].isna().all()  # no filled or newly created price


def test_halt_freezes_decisions_and_missing_denominator_defers_instead_of_flattening():
    px = halt_prices()
    targets = generate_targets(px, "momentum", 1, 1)
    np.testing.assert_allclose(targets.iloc[10], [-0.5, 0.5])
    np.testing.assert_allclose(targets.iloc[11], [0.5, -0.5])
    for row in (12, 13, 14, 15):
        np.testing.assert_array_equal(targets.iloc[row], targets.iloc[11])
    # The first genuine equal-return decision after normal data resumes may flatten.
    np.testing.assert_array_equal(targets.iloc[16], [0, 0])


def test_halt_lookbacks_use_elapsed_hours_not_observed_row_counts():
    px = halt_prices()
    targets = generate_targets(px, "momentum", 4, 4)
    # At 16:00 the exact denominator is the retained source mark at 12:00,
    # not the fourth observed row back (09:00) in a sparse valuation series.
    np.testing.assert_allclose(targets.iloc[16], [-0.5, 0.5])


def test_halt_bridge_has_no_fictional_trade_cash_reset_or_price_mark():
    px = halt_prices()
    targets = pd.DataFrame(np.tile([0.5, -0.5], (len(px), 1)), index=px.index, columns=px.columns)
    result = simulate(px, targets, px.index[0], px.index[-1])
    assert not result.frame.index.isin(px.index[12:15]).any()
    np.testing.assert_allclose(result.held_weights.loc[px.index[15]], [0.5, -0.5])
    assert result.frame.loc[px.index[15], "gross_return"] == pytest.approx(0.15)
    assert result.frame.loc[px.index[15], "cost"] == 0
    assert result.frame["turnover"].sum() == 2  # initial entry and final exit only
    assert result.frame["interval_hours"].sum() == 48
    assert result.frame.loc[px.index[15], "interval_hours"] == 4
    assert result.frame["net_return"].attrs["interval_hours"] == {px.index[15].isoformat(): 4}


def test_bridge_holdings_and_costs_use_pre_halt_target_with_extra_lag():
    px = halt_prices()
    targets = generate_targets(px, "momentum", 1, 1)
    regular = simulate(px, targets, px.index[0], px.index[-1])
    delayed = simulate(px, targets, px.index[0], px.index[-1], execution_lag=2)
    np.testing.assert_allclose(regular.held_weights.loc[px.index[15]], targets.iloc[11])
    np.testing.assert_allclose(delayed.held_weights.loc[px.index[15]], targets.iloc[10])
    assert regular.frame.loc[px.index[15], "gross_return"] == pytest.approx(0.15)
    assert delayed.frame.loc[px.index[15], "gross_return"] == pytest.approx(-0.15)
    # These costs reflect changes made at the bridge start (11:00), not during suspension.
    assert regular.frame.loc[px.index[15], "turnover"] == 2
    assert delayed.frame.loc[px.index[15], "turnover"] == 1


def test_bridge_future_mutations_cannot_change_pre_halt_exposure():
    px = halt_prices()
    original = generate_targets(px, "momentum", 1, 1)
    changed = px.copy()
    changed.iloc[15:, 0] *= 3
    mutated = generate_targets(changed, "momentum", 1, 1)
    assert_frame_equal(original.iloc[:15], mutated.iloc[:15])
    regular = simulate(px, original, px.index[0], px.index[-1])
    changed_result = simulate(changed, mutated, changed.index[0], changed.index[-1])
    np.testing.assert_array_equal(regular.held_weights.loc[px.index[15]],
                                  changed_result.held_weights.loc[px.index[15]])


@pytest.mark.parametrize("bad", ["undeclared", "no_bridge", "partial_nan", "another_missing", "missing_index"])
def test_unrecognized_or_partial_missing_prices_still_fail(bad):
    px = halt_prices()
    if bad == "undeclared":
        px.attrs.pop("allowed_missing_endpoints")
    elif bad == "no_bridge":
        px.attrs.pop("halt_bridges")
    elif bad == "partial_nan":
        px.iloc[14, 1] = 100
    elif bad == "another_missing":
        px.iloc[20] = np.nan
    else:
        px = px.drop(px.index[14])
    with pytest.raises(ValueError):
        observed_asset_returns(px)


def test_split_boundaries_cannot_force_cash_execution_inside_halt():
    px = halt_prices()
    targets = generate_targets(px, "momentum", 1, 1)
    with pytest.raises(ValueError, match="inside"):
        simulate(px, targets, px.index[12], px.index[-1])
    with pytest.raises(ValueError, match="inside"):
        simulate(px, targets, px.index[0], px.index[13])
