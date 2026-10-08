"""Synthetic causal/chronological tests, with no holdout data access."""
import numpy as np
import pandas as pd
import pytest

from crypto_stat_arb_extensions.diagnostics import (
    _bootstrap_means, _circular_block_indices, _holm, signal_ic,
)


def trend_panel(start="2021-11-01", end="2022-04-01", equal=False):
    index = pd.date_range(start, end, freq="h", tz="UTC")
    hours = ((index - index[0]) / pd.Timedelta(hours=1)).to_numpy()
    slopes = np.ones(8) * 0.00001 if equal else np.arange(1, 9) * 0.00001
    return pd.DataFrame(np.exp(hours[:, None] * slopes), index=index,
                        columns=["BTCUSDT", "ETHUSDT", "LTCUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT", "SOLUSDT"])


PERIOD = {"development": {"start": "2022-01-01", "end": "2022-04-01"}}


def test_positive_signal_uses_raw_momentum_and_daily_midnight():
    daily, summary = signal_ic(trend_panel(), PERIOD, lookbacks=[1, 24], forward_horizons=[1, 24],
                               n_bootstrap=100, block_days=7)
    assert len(daily) == 90 * 4
    assert daily.decision_date.dt.hour.eq(0).all()
    assert np.allclose(daily.loc[daily.eligible, "ic"], 1)
    assert summary.n_valid.eq(90).all()
    assert np.allclose(summary.mean_ic, 1)
    assert np.allclose(summary.positive_fraction, 1)
    assert summary.holm_family_size.eq(4).all()
    assert (summary.p_holm >= summary.p_value).all()


def test_negative_signal_interpretation_is_reversal_not_separate_test():
    prices = trend_panel()
    hours = ((prices.index - prices.index[0]) / pd.Timedelta(hours=1)).to_numpy()
    prices.iloc[:, :] = np.exp(np.cos(np.pi * hours[:, None] / 24) * np.linspace(.001, .008, 8))
    daily, summary = signal_ic(prices, PERIOD, lookbacks=[24], forward_horizons=[24],
                               n_bootstrap=100, block_days=7)
    assert np.allclose(daily.ic, -1)
    assert summary.iloc[0].mean_ic == pytest.approx(-1)
    assert summary.iloc[0].positive_fraction == 0


def test_all_equal_scores_are_undefined_not_zero_ic():
    daily, summary = signal_ic(trend_panel(equal=True), PERIOD, lookbacks=[24], forward_horizons=[24],
                               n_bootstrap=20, block_days=7)
    assert daily.ic.isna().all()
    assert daily.exclusion_reason.eq("undefined_rank_variance").all()
    assert summary.iloc[0].n_valid == 0
    assert np.isnan(summary.iloc[0].mean_ic)
    assert np.isnan(summary.iloc[0].p_holm)


def test_average_tie_ranks_still_allow_defined_ic():
    prices = trend_panel()
    prices["ETHUSDT"] = prices["BTCUSDT"]
    daily, _ = signal_ic(prices, PERIOD, lookbacks=[24], forward_horizons=[24],
                         n_bootstrap=20, block_days=7)
    assert daily.eligible.all()
    assert np.allclose(daily.ic, 1)


def test_outcome_cannot_cross_period_end_but_may_equal_end():
    daily, summary = signal_ic(trend_panel(), PERIOD, lookbacks=[24], forward_horizons=[168],
                               n_bootstrap=20, block_days=7)
    eligible = daily.loc[daily.eligible]
    assert eligible.decision_date.max() == pd.Timestamp("2022-03-25", tz="UTC")
    assert daily.loc[~daily.eligible, "exclusion_reason"].eq("crosses_split_end").all()
    assert summary.iloc[0].n_calendar_days == 90
    assert summary.iloc[0].n_valid == 84


def test_missing_endpoints_preserve_calendar_grid_and_fixed_universe():
    prices = trend_panel()
    prices.loc[pd.Timestamp("2022-02-03", tz="UTC"), "ETHUSDT"] = np.nan
    daily, summary = signal_ic(prices, PERIOD, lookbacks=[24], forward_horizons=[24],
                               n_bootstrap=20, block_days=7)
    missing_dates = pd.DatetimeIndex(daily.loc[daily.ic.isna(), "decision_date"])
    assert missing_dates.equals(pd.date_range("2022-02-02", "2022-02-04", freq="D", tz="UTC"))
    assert len(daily) == 90
    assert summary.iloc[0].n_valid == 87
    assert daily.exclusion_reason.eq("unavailable_endpoint").sum() == 3


def test_raw_partial_halt_endpoints_are_not_admissible():
    prices = trend_panel(start="2023-02-01", end="2023-04-05")
    prices.attrs["halt_bridges"] = [{"start": "2023-03-24T11:00:00+00:00", "end": "2023-03-24T15:00:00+00:00", "source": "official-test"}]
    period = {"development": {"start": "2023-03-01", "end": "2023-04-01"}}
    daily, _ = signal_ic(prices, period, lookbacks=[12], forward_horizons=[12],
                         n_bootstrap=20, block_days=7)
    actual = daily.loc[daily.exclusion_reason.eq("halt_interior"), "decision_date"]
    assert list(actual) == [pd.Timestamp("2023-03-24", tz="UTC"), pd.Timestamp("2023-03-25", tz="UTC")]
    assert prices.loc["2023-03-24 12:00"].notna().all()  # Rejection is not merely NaN filtering.


def test_future_perturbation_does_not_change_earlier_score_outcomes():
    prices = trend_panel()
    cutoff = pd.Timestamp("2022-03-01", tz="UTC")
    perturbed = prices.copy()
    perturbed.loc[perturbed.index >= cutoff, :] *= np.linspace(.5, 2, 8)
    kwargs = dict(lookbacks=[24], forward_horizons=[24], n_bootstrap=20, block_days=7)
    original, _ = signal_ic(prices, PERIOD, **kwargs)
    changed, _ = signal_ic(perturbed, PERIOD, **kwargs)
    before = original.decision_date + pd.Timedelta(days=1) < cutoff
    pd.testing.assert_series_equal(original.loc[before, "ic"], changed.loc[before, "ic"])


def test_bootstrap_is_seeded_shared_calendar_and_keeps_missing_rows():
    x = np.sin(np.arange(100) / 4.0)
    x[30:40] = np.nan
    values = np.column_stack([x, x, x * 2])
    first = _bootstrap_means(values, 200, 7, 123)
    second = _bootstrap_means(values, 200, 7, 123)
    assert np.array_equal(first, second)
    assert np.allclose(first[:, 0], first[:, 1])
    assert np.allclose(first[:, 2], 2 * first[:, 0])
    assert not np.array_equal(first, _bootstrap_means(values, 200, 7, 124))
    indices = _circular_block_indices(100, 50, 7, np.random.default_rng(123))
    assert indices.shape == (50, 100)
    assert ((indices[:, :7][:, 1:] - indices[:, :7][:, :-1]) % 100 == 1).all()
    assert ((indices >= 30) & (indices < 40)).any()  # Missing calendar dates are sampled.


def test_one_effective_calendar_block_does_not_claim_precise_inference():
    samples = _bootstrap_means(np.ones((20, 1)), 100, 28, 123)
    assert np.isnan(samples).all()


def test_holm_uses_declared_family_and_retains_undefined():
    adjusted = _holm([.01, .03, np.nan, .9])
    assert adjusted[0] == pytest.approx(.04)
    assert adjusted[1] == pytest.approx(.09)
    assert np.isnan(adjusted[2])
    assert adjusted[3] == 1


@pytest.mark.parametrize("setting", [dict(lookbacks=[0]), dict(forward_horizons=[1, 1]), dict(block_days=0), dict(n_bootstrap=False)])
def test_invalid_hypothesis_or_inference_settings_fail(setting):
    with pytest.raises(ValueError):
        signal_ic(trend_panel(), PERIOD, **setting)


def test_nonhourly_calendar_and_overlapping_splits_fail():
    with pytest.raises(ValueError, match="calendar"):
        signal_ic(trend_panel().iloc[::2], PERIOD)
    with pytest.raises(ValueError, match="overlap"):
        signal_ic(trend_panel(), {"a": {"start": "2022-01-01", "end": "2022-03-01"},
                                  "b": {"start": "2022-02-01", "end": "2022-04-01"}})
