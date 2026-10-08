"""Regime diagnostics are causal descriptions, not new selected filters."""
import numpy as np
import pandas as pd
import pytest

from crypto_stat_arb_extensions.diagnostics import (
    REGIME_COLUMNS, fit_regime_thresholds, regime_diagnostics, regime_features,
)


def panels():
    index = pd.date_range("2021-11-01", "2022-05-01", freq="h", tz="UTC")
    hours = ((index - index[0]) / pd.Timedelta(hours=1)).to_numpy()
    columns = ["BTCUSDT", "ETHUSDT", "LTCUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT", "SOLUSDT"]
    prices = pd.DataFrame(np.exp(.00002 * hours[:, None] * np.arange(1, 9)), index=index, columns=columns)
    volume = pd.DataFrame(1., index=index, columns=columns)
    return prices, volume


def feature_table(start="2022-01-01", end="2022-04-01"):
    dates = pd.date_range(start, end, freq="D", inclusive="left", tz="UTC", name="decision_date")
    x = np.where(np.arange(len(dates)) % 2, 2., .5)
    return pd.DataFrame({column: x for column in REGIME_COLUMNS}, index=dates)


SPLITS = {"development": {"start": "2022-01-01", "end": "2022-04-01"}}
THRESHOLDS = {"thresholds": {column: 1. for column in REGIME_COLUMNS}}


def return_table(features, strategies=("a",)):
    records = []
    for sid in strategies:
        for day, row in features.iterrows():
            high = row.iloc[0] >= 1
            daily_net = .002 if high else -.001
            net = (1 + daily_net) ** (1 / 24) - 1
            for hour in range(1, 25):
                records.append({"bar_end": day + pd.Timedelta(hours=hour), "strategy_id": sid,
                    "split": "development", "cost_bps": 20., "execution_lag": 1,
                    "gross_return": net + .00001, "net_return": net, "turnover": .05,
                    "interval_hours": 1.})
    return pd.DataFrame(records)


def test_relative_volume_uses_complete_last24h_and_strict_preceding7days():
    prices, volume = panels()
    day = pd.Timestamp("2022-02-01", tz="UTC")
    volume.loc[(volume.index > day - pd.Timedelta(days=1)) & (volume.index <= day)] = 10.
    features = regime_features(prices, volume)
    assert features.loc[day, "relative_quote_volume"] == pytest.approx(10)
    assert features.loc[day - pd.Timedelta(days=1), "relative_quote_volume"] == pytest.approx(1)
    assert features.loc[day + pd.Timedelta(days=1), "relative_quote_volume"] == pytest.approx(7 / 16)


def test_missing_volume_produces_unknown_not_partial_sum_or_stale_fill():
    prices, volume = panels()
    day = pd.Timestamp("2022-02-01", tz="UTC")
    volume.loc[day - pd.Timedelta(hours=8), "ETHUSDT"] = np.nan
    features = regime_features(prices, volume)
    affected = features.loc[day:day + pd.Timedelta(days=7), "relative_quote_volume"]
    assert affected.isna().all()
    assert features.loc[day + pd.Timedelta(days=8), "relative_quote_volume"] == pytest.approx(1)


def test_volatility_and_dispersion_have_explicit_sample_definitions():
    prices, volume = panels()
    features = regime_features(prices, volume)
    day = pd.Timestamp("2022-02-01", tz="UTC")
    returns = prices.loc[day] / prices.loc[day - pd.Timedelta(days=1)] - 1
    assert features.loc[day, "return_dispersion_24h"] == pytest.approx(returns.std(ddof=1))
    assert features.loc[day, "btc_volatility_30d"] == pytest.approx(0, abs=1e-12)
    assert features.loc["2021-11-30", "btc_volatility_30d"] != features.loc["2021-11-30", "btc_volatility_30d"]
    assert np.isfinite(features.loc["2021-12-01", "btc_volatility_30d"])


def test_future_prices_or_volume_do_not_change_current_features():
    prices, volume = panels()
    day = pd.Timestamp("2022-02-01", tz="UTC")
    before = regime_features(prices, volume)
    changed_prices, changed_volume = prices.copy(), volume.copy()
    changed_prices.loc[changed_prices.index > day] *= np.arange(1, 9)
    changed_volume.loc[changed_volume.index > day] *= 200
    after = regime_features(changed_prices, changed_volume)
    pd.testing.assert_frame_equal(before.loc[:day], after.loc[:day])


def test_thresholds_fit_only_training_dates_and_record_metadata():
    features = feature_table(end="2022-05-01")
    original = fit_regime_thresholds(features, "2022-01-01", "2022-04-01")
    features.loc[features.index >= pd.Timestamp("2022-04-01", tz="UTC")] = 1e10
    changed = fit_regime_thresholds(features, "2022-01-01", "2022-04-01")
    assert original == changed
    assert original["thresholds"] == {column: 1.25 for column in REGIME_COLUMNS}
    assert original["n_training_observations"] == {column: 90 for column in REGIME_COLUMNS}
    assert original["training_end_exclusive"] == "2022-04-01T00:00:00+00:00"


def test_daily_pnl_uses_previous_decision_label_and_compounds_not_sums():
    features = feature_table()
    frame = return_table(features)
    observations, summary = regime_diagnostics(frame, features, THRESHOLDS, SPLITS,
                                                n_bootstrap=100, block_days=7)
    first = observations.loc[observations.regime_feature.eq(REGIME_COLUMNS[0])].iloc[0]
    assert first.decision_date == pd.Timestamp("2022-01-01", tz="UTC")
    assert first.regime == "low"
    assert first.net_return == pytest.approx(-.001)
    assert first.turnover == pytest.approx(1.2)
    assert first.interval_hours == 24
    assert first.n_return_observations == 24
    assert len(observations) == 90 * 3
    high = summary.loc[summary.regime.eq("high")]
    low = summary.loc[summary.regime.eq("low")]
    assert np.allclose(high.mean_daily_net_return, .002)
    assert np.allclose(low.mean_daily_net_return, -.001)
    assert np.allclose(summary.high_minus_low_net_return, .003)
    assert summary.holm_family_size.eq(3).all()
    assert "sharpe" not in summary.columns


def test_unknown_features_retained_without_affecting_pnl_or_missing_calendar():
    features = feature_table()
    frame = return_table(features)
    day = features.index[20]
    features.loc[day, REGIME_COLUMNS[0]] = np.nan
    observations, summary = regime_diagnostics(frame, features, THRESHOLDS, SPLITS,
                                                n_bootstrap=100, block_days=7)
    unknown = observations.loc[observations.regime.eq("unknown")]
    assert len(unknown) == 1
    assert unknown.iloc[0].decision_date == day
    assert unknown.iloc[0].net_return == pytest.approx(-.001)
    assert len(observations) == 270
    row = summary.loc[summary.regime_feature.eq(REGIME_COLUMNS[0]) & summary.regime.eq("unknown")].iloc[0]
    assert row.n_days == row.n_valid_returns == 1


def test_daily_halt_bridge_counts_elapsed_hours_and_preserves_real_return():
    features = feature_table()
    frame = return_table(features)
    day = pd.Timestamp("2022-02-01", tz="UTC")
    interior = (frame.bar_end > day + pd.Timedelta(hours=11)) & (frame.bar_end < day + pd.Timedelta(hours=15))
    bridge_rows = (frame.bar_end > day + pd.Timedelta(hours=11)) & (frame.bar_end <= day + pd.Timedelta(hours=15))
    expected_gross = float(np.prod(1 + frame.loc[bridge_rows, "gross_return"]) - 1)
    expected_net = float(np.prod(1 + frame.loc[bridge_rows, "net_return"]) - 1)
    bridge = frame.bar_end.eq(day + pd.Timedelta(hours=15))
    frame.loc[bridge, ["gross_return", "net_return", "turnover", "interval_hours"]] = [expected_gross, expected_net, .2, 4.]
    frame = frame.loc[~interior]
    observations, _ = regime_diagnostics(frame, features, THRESHOLDS, SPLITS,
                                          n_bootstrap=20, block_days=7)
    actual = observations.loc[observations.decision_date.eq(day)].iloc[0]
    assert actual.interval_hours == 24
    assert actual.n_return_observations == 21
    assert actual.turnover == pytest.approx(1.2)
    assert actual.net_return == pytest.approx(.002)


def test_holm_is_applied_once_per_strategy_feature_not_per_three_labels():
    features = feature_table()
    frame = return_table(features, strategies=("a", "b"))
    _, summary = regime_diagnostics(frame, features, THRESHOLDS, SPLITS,
                                     n_bootstrap=100, block_days=7)
    assert len(summary) == 2 * 3 * 3
    assert summary.holm_family_size.eq(6).all()
    grouped = summary.groupby(["strategy_id", "regime_feature"])
    assert grouped.p_holm.nunique().eq(1).all()
    assert np.allclose(summary.p_holm, 6 / 101)


def test_regime_bootstrap_seed_reproducibility_and_shared_dates():
    features = feature_table()
    frame = return_table(features, strategies=("a", "b"))
    frame.net_return += np.sin(np.arange(len(frame)) / 5) * .0001
    kwargs = dict(n_bootstrap=100, block_days=7, seed=19)
    first_obs, first_summary = regime_diagnostics(frame, features, THRESHOLDS, SPLITS, **kwargs)
    second_obs, second_summary = regime_diagnostics(frame, features, THRESHOLDS, SPLITS, **kwargs)
    pd.testing.assert_frame_equal(first_obs, second_obs)
    pd.testing.assert_frame_equal(first_summary, second_summary)
    a = first_summary.loc[first_summary.strategy_id.eq("a") & first_summary.regime.eq("high")]
    assert a.ci_low.nunique() == 1  # Identical feature labels share the sampled date blocks.


def test_missing_whole_return_day_is_retained_on_calendar_grid():
    features = feature_table()
    frame = return_table(features)
    day = features.index[15]
    frame = frame.loc[~((frame.bar_end > day) & (frame.bar_end <= day + pd.Timedelta(days=1)))]
    observations, summary = regime_diagnostics(frame, features, THRESHOLDS, SPLITS,
                                                n_bootstrap=20, block_days=7)
    actual = observations.loc[observations.decision_date.eq(day)]
    assert len(actual) == 3
    assert actual.net_return.isna().all()
    assert len(observations) == 270
    high = summary.loc[summary.regime.eq("high")]
    assert high.n_days.eq(45).all()
    assert high.n_valid_returns.eq(44).all()


@pytest.mark.parametrize("alteration", ["missing_hour", "duplicate", "outside", "overlap", "bankrupt"])
def test_invalid_daily_return_intervals_or_boundaries_fail(alteration):
    features = feature_table()
    frame = return_table(features)
    if alteration == "missing_hour":
        frame = frame.iloc[1:]
    elif alteration == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]])
    elif alteration == "outside":
        frame.loc[0, "bar_end"] = pd.Timestamp("2021-12-31 23:00", tz="UTC")
    elif alteration == "overlap":
        frame.loc[0, "interval_hours"] = 2
        frame.loc[1, "interval_hours"] = .5
        frame.loc[2, "interval_hours"] = .5
    else:
        frame.loc[0, "net_return"] = -1
    with pytest.raises(ValueError):
        regime_diagnostics(frame, features, THRESHOLDS, SPLITS, n_bootstrap=10, block_days=7)


def test_no_finite_training_or_misaligned_feature_panel_fails():
    features = feature_table()
    features.loc[:, REGIME_COLUMNS[0]] = np.nan
    with pytest.raises(ValueError, match="No finite"):
        fit_regime_thresholds(features, "2022-01-01", "2022-04-01")
    prices, volume = panels()
    with pytest.raises(ValueError, match="matching"):
        regime_features(prices, volume.iloc[:, ::-1])
