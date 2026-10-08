"""Synthetic factor formation/state/hedge tests; never use 2026 archives."""
import numpy as np
import pandas as pd
import pytest

from crypto_stat_arb.backtest import simulate
from crypto_stat_arb_extensions import strategies


SYMBOLS = ["BTCUSDT", "ETHUSDT", "LTCUSDT", "ADAUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT", "SOLUSDT"]
ALTS = SYMBOLS[1:]


def formation_prices(start="2021-10-01", end="2022-04-01", seed=917):
    days = pd.date_range(start, end, freq="D", tz="UTC")
    rng = np.random.default_rng(seed)
    market = np.log(100) + np.r_[0.0, rng.normal(0, 0.03, len(days) - 1)].cumsum()
    logs = {"BTCUSDT": market}
    for i, symbol in enumerate(ALTS):
        spread = np.zeros(len(days))
        for j in range(1, len(days)):
            spread[j] = 0.8 * spread[j - 1] + rng.normal(0, 0.006)
        logs[symbol] = (0.6 + 0.15 * i) * market + spread
    daily = np.exp(pd.DataFrame(logs, index=days))
    hourly = pd.date_range(start, end, freq="h", tz="UTC")
    # This is an explicitly piecewise-constant synthetic fixture, not filling
    # absent historical observations in the research code.
    return daily.reindex(hourly, method="ffill")


def state_prices(changes, end="2022-02-03", betas=None, btc_changes=None):
    betas = betas or {s: 1.0 for s in ALTS}
    days = pd.date_range("2021-10-01", end, freq="D", tz="UTC")
    z = pd.DataFrame(0.0, index=days, columns=ALTS)
    for time, values in changes.items():
        for symbol, value in values.items():
            z.loc[pd.Timestamp(time, tz="UTC"):, symbol] = value
    btc = pd.Series(100.0, index=days)
    for time, value in (btc_changes or {}).items():
        btc.loc[pd.Timestamp(time, tz="UTC"):] = value
    daily = pd.DataFrame({"BTCUSDT": btc, **{
        symbol: btc ** betas[symbol] * np.exp(z[symbol]) for symbol in ALTS}})
    return daily.reindex(pd.date_range(days[0], days[-1], freq="h"), method="ffill")


def mock_eligible_models(monkeypatch, betas=None):
    betas = betas or {s: 1.0 for s in ALTS}

    def fitted(daily, refit, symbols, bridges):
        return [{**strategies._model_template(refit, symbol), "beta": betas[symbol],
                 "alpha_daily_log_return": 0.0, "mu": 0.0, "sigma": 1.0,
                 "adf_pvalue": 0.0001, "adf_pvalue_holm": 0.0007,
                 "phi": 0.8, "half_life_days": np.log(0.5) / np.log(0.8),
                 "eligible": True, "reason": "eligible"} for symbol in symbols]
    monkeypatch.setattr(strategies, "_fit_month_models", fitted)


def time(value):
    return pd.Timestamp(value, tz="UTC")


def symbol_events(result, symbol="ETHUSDT", start="2022-01-01"):
    return result.events.loc[result.events.symbol.eq(symbol) & (result.events.decision_time >= time(start))]


def test_factor_partition_uses_91_prices_30_returns_then_60_separate_endpoints():
    prices = formation_prices()
    daily = prices.loc[prices.index.hour == 0]
    refit = time("2022-01-01")
    models = strategies._fit_month_models(daily, refit, ALTS, [])
    model = models[0]
    assert model["formation_price_start"] == refit - pd.Timedelta(days=91)
    assert model["fit_start"] == refit - pd.Timedelta(days=90)
    assert model["fit_end"] == refit - pd.Timedelta(days=61)
    assert model["calibration_start"] == refit - pd.Timedelta(days=60)
    assert model["calibration_end"] == refit - pd.Timedelta(days=1)
    window = np.log(daily.loc[model["formation_price_start"]:model["calibration_end"], ["ETHUSDT", "BTCUSDT"]])
    assert len(window) == 91
    returns = window.diff().dropna().iloc[:30]
    expected_alpha, expected_beta = np.linalg.lstsq(
        np.column_stack([np.ones(30), returns.BTCUSDT]), returns.ETHUSDT, rcond=None)[0]
    expected_spread = window.ETHUSDT.iloc[-60:] - expected_beta * window.BTCUSDT.iloc[-60:]
    assert model["beta"] == pytest.approx(expected_beta)
    assert model["alpha_daily_log_return"] == pytest.approx(expected_alpha)
    assert model["mu"] == pytest.approx(expected_spread.mean())
    assert model["sigma"] == pytest.approx(expected_spread.std(ddof=1))
    changed = daily.copy()
    changed.loc[model["calibration_start"]:model["calibration_end"], "ETHUSDT"] *= 1.5
    later_model = strategies._fit_month_models(changed, refit, ALTS, [])[0]
    assert later_model["beta"] == model["beta"]
    assert later_model["mu"] != pytest.approx(model["mu"])


def test_adf_arguments_pinned_and_holm_includes_all_seven(monkeypatch):
    calls = []

    def adf(spread, **kwargs):
        calls.append(kwargs)
        return (-5.0, 0.01, 0, len(spread), {}, 0.0)
    monkeypatch.setattr(strategies, "adfuller", adf)
    daily = formation_prices().iloc[::24]
    models = strategies._fit_month_models(daily, time("2022-01-01"), ALTS, [])
    assert len(calls) == 7
    assert all(c == {"maxlag": 3, "regression": "c", "autolag": "AIC"} for c in calls)
    assert all(m["adf_pvalue"] == 0.01 and m["adf_pvalue_holm"] == pytest.approx(0.07) for m in models)
    assert all(not m["eligible"] and "adf_holm_not_rejected" in m["reason"] for m in models)


def test_raw_valid_adf_retained_even_when_beta_gate_fails(monkeypatch):
    daily = formation_prices().iloc[::24]
    daily["ETHUSDT"] *= daily.BTCUSDT ** 6
    monkeypatch.setattr(strategies, "adfuller", lambda *args, **kwargs: (-5, 0.0001, 0, 60, {}, 0))
    model = strategies._fit_month_models(daily, time("2022-01-01"), ALTS, [])[0]
    assert model["beta"] > 5
    assert model["adf_pvalue"] == 0.0001 and model["adf_pvalue_holm"] == pytest.approx(0.0007)
    assert "beta_out_of_bounds" in model["reason"] and not model["eligible"]


def test_zero_spread_scale_is_failed_model_p_one_in_holm(monkeypatch):
    daily = formation_prices().iloc[::24]
    daily["ETHUSDT"] = daily.BTCUSDT ** 2
    monkeypatch.setattr(strategies, "adfuller", lambda *args, **kwargs: (-5, 0.001, 0, 60, {}, 0))
    models = strategies._fit_month_models(daily, time("2022-01-01"), ALTS, [])
    assert models[0]["sigma"] <= 1e-8
    assert models[0]["adf_pvalue"] == models[0]["adf_pvalue_holm"] == 1
    assert "spread_scale_too_small" in models[0]["reason"] and not models[0]["eligible"]
    assert all(m["adf_pvalue_holm"] == pytest.approx(0.007) for m in models[1:])


@pytest.mark.parametrize("phi,reason", [(0.25, "half_life_out_of_bounds"),
                                       (0.99, "half_life_out_of_bounds"),
                                       (1.01, "non_mean_reverting_ar1"),
                                       (-0.5, "non_mean_reverting_ar1")])
def test_half_life_and_phi_eligibility_gates(monkeypatch, phi, reason):
    daily = formation_prices().iloc[::24]
    refit = time("2022-01-01")
    dates = pd.date_range(refit - pd.Timedelta(days=91), refit - pd.Timedelta(days=1), freq="D", tz="UTC")
    # First31prices imply exactlybeta1 for30formationreturns. Calibration is
    # deliberately disjoint and gives a known AR1 price-level spread.
    daily.loc[dates[:31], "ETHUSDT"] = daily.loc[dates[:31], "BTCUSDT"]
    spread = 0.01 * phi ** np.arange(60)
    daily.loc[dates[-60:], "ETHUSDT"] = daily.loc[dates[-60:], "BTCUSDT"] * np.exp(spread)
    monkeypatch.setattr(strategies, "adfuller", lambda *args, **kwargs: (-5, 0.0001, 0, 60, {}, 0))
    model = strategies._fit_month_models(daily, refit, ALTS, [])[0]
    assert model["beta"] == pytest.approx(1)
    assert model["phi"] == pytest.approx(phi, abs=1e-8)
    assert reason in model["reason"] and not model["eligible"]


def test_insufficient_warmup_constant_factor_and_allcash_are_valid():
    index = pd.date_range("2021-12-01", "2022-02-01", freq="h", tz="UTC")
    prices = pd.DataFrame(100.0, index=index, columns=SYMBOLS)
    result = strategies.generate_factor_targets(prices)
    assert not result.targets.to_numpy().any()
    assert not result.models.eligible.any()
    assert result.models.adf_pvalue_holm.eq(1).all()
    assert result.models.reason.str.contains("insufficient_or_unobserved_formation").all()
    longer = pd.DataFrame(100.0, index=pd.date_range("2021-10-01", "2022-02-01", freq="h", tz="UTC"), columns=SYMBOLS)
    result = strategies.generate_factor_targets(longer)
    assert result.models.loc[result.models.refit_time == time("2022-01-01"), "reason"].str.contains("constant_market_factor").all()
    assert not result.targets.to_numpy().any()


def test_future_price_changes_do_not_change_prior_models_events_or_targets():
    prices = formation_prices()
    boundary = time("2022-02-15")
    before = strategies.generate_factor_targets(prices)
    changed = prices.copy()
    changed.loc[changed.index > boundary] *= np.linspace(0.5, 2.5, 8)
    after = strategies.generate_factor_targets(changed)
    pd.testing.assert_frame_equal(before.targets.loc[:boundary], after.targets.loc[:boundary])
    pd.testing.assert_frame_equal(before.models.loc[before.models.refit_time <= boundary].reset_index(drop=True),
                                  after.models.loc[after.models.refit_time <= boundary].reset_index(drop=True))
    pd.testing.assert_frame_equal(before.events.loc[before.events.decision_time <= boundary].reset_index(drop=True),
                                  after.events.loc[after.events.decision_time <= boundary].reset_index(drop=True))


def test_mean_crossing_overshoot_closes_and_does_not_same_day_flip(monkeypatch):
    mock_eligible_models(monkeypatch)
    prices = state_prices({"2022-01-02": {"ETHUSDT": -2.5}, "2022-01-03": {"ETHUSDT": 2.5}}, end="2022-01-05")
    result = strategies.generate_factor_targets(prices)
    events = symbol_events(result)
    assert events.loc[events.decision_time == time("2022-01-02"), "event"].tolist() == ["entry"]
    assert events.loc[events.decision_time == time("2022-01-03"), "event"].tolist() == ["mean_reversion_exit"]
    assert result.targets.loc[time("2022-01-03")].abs().sum() == 0
    assert result.targets.loc[time("2022-01-04"), "ETHUSDT"] == pytest.approx(-1 / 14)


@pytest.mark.parametrize("entry,overshoot", [(2.5, -2.5), (-2.5, 2.5)])
def test_both_sides_exit_when_jump_crosses_mean(monkeypatch, entry, overshoot):
    mock_eligible_models(monkeypatch)
    prices = state_prices({"2022-01-02": {"ETHUSDT": entry}, "2022-01-03": {"ETHUSDT": overshoot}}, end="2022-01-03")
    result = strategies.generate_factor_targets(prices)
    assert symbol_events(result).iloc[-1]["event"] == "mean_reversion_exit"
    assert result.targets.loc[time("2022-01-03")].abs().sum() == 0


def test_adverse_stop_and_extreme_flat_entry_exclusion(monkeypatch):
    mock_eligible_models(monkeypatch)
    prices = state_prices({"2022-01-02": {"ETHUSDT": -2.5}, "2022-01-03": {"ETHUSDT": -4.5}}, end="2022-01-05")
    result = strategies.generate_factor_targets(prices)
    events = symbol_events(result)
    assert events.loc[events.decision_time == time("2022-01-03"), "event"].tolist() == ["adverse_stop"]
    assert events.loc[events.decision_time == time("2022-01-04"), "event"].tolist() == ["entry_skipped_extreme"]
    assert result.targets.loc[time("2022-01-03"):].abs().sum(axis=1).eq(0).all()


def test_holding_age_is_elapsed_days_and_capped_at_twenty(monkeypatch):
    mock_eligible_models(monkeypatch)
    prices = state_prices({"2022-01-02": {"ETHUSDT": -2.5}, "2022-01-03": {"ETHUSDT": -1.0}}, end="2022-01-25")
    result = strategies.generate_factor_targets(prices)
    event = symbol_events(result).loc[lambda x: x.event.eq("max_holding_exit")].iloc[0]
    assert event.decision_time == time("2022-01-22") and event.holding_days == 20
    assert result.targets.loc[time("2022-01-22")].abs().sum() == 0


def test_monthly_refit_forces_cash_and_freezes_weights_between_refits(monkeypatch):
    mock_eligible_models(monkeypatch)
    prices = state_prices({"2022-01-25": {"ETHUSDT": -2.5}})
    result = strategies.generate_factor_targets(prices)
    assert result.targets.loc[time("2022-01-31"), "ETHUSDT"] > 0
    assert result.targets.loc[time("2022-02-01")].abs().sum() == 0
    assert result.targets.loc[time("2022-02-02"), "ETHUSDT"] > 0
    events = symbol_events(result)
    assert events.loc[events.decision_time == time("2022-02-01"), "event"].tolist() == ["monthly_exit", "monthly_refit_cash"]
    january = result.models.loc[result.models.refit_time == time("2022-01-01")]
    assert len(january) == 7 and january.beta.nunique() == 1


def test_net_aggregated_actual_btc_hedge_and_full_hedge_costs(monkeypatch):
    betas = {s: 1.0 for s in ALTS}
    betas["ETHUSDT"] = 2.0
    mock_eligible_models(monkeypatch, betas)
    prices = state_prices({"2022-01-02": {"ETHUSDT": -2.5}, "2022-01-03": {"ETHUSDT": -1.5}},
                          end="2022-01-03", betas=betas, btc_changes={"2022-01-03": 110})
    result = strategies.generate_factor_targets(prices)
    entry = result.targets.loc[time("2022-01-02")]
    assert entry.ETHUSDT == pytest.approx(1 / 21)
    assert entry.BTCUSDT == pytest.approx(-2 / 21)
    evaluated = simulate(prices, result.targets, "2022-01-02", "2022-01-03", cost_bps=20)
    actual_asset_return = prices.loc[time("2022-01-03")] / prices.loc[time("2022-01-02")] - 1
    expected_gross = float((entry * actual_asset_return).sum())
    assert evaluated.frame.gross_return.sum() == pytest.approx(expected_gross)
    assert expected_gross == pytest.approx(entry.ETHUSDT * actual_asset_return.ETHUSDT
                                          + entry.BTCUSDT * actual_asset_return.BTCUSDT)
    assert evaluated.frame.turnover.sum() == pytest.approx(2 / 7)
    assert evaluated.frame.cost.sum() == pytest.approx(20e-4 * 2 / 7)
    np.testing.assert_allclose(evaluated.frame.net_return, evaluated.frame.gross_return - evaluated.frame.cost)


def test_opposing_pair_hedges_are_netted_not_artificially_gross_scaled(monkeypatch):
    mock_eligible_models(monkeypatch)
    prices = state_prices({"2022-01-02": {"ETHUSDT": -2.5, "LTCUSDT": 2.5}}, end="2022-01-03")
    result = strategies.generate_factor_targets(prices)
    weights = result.targets.loc[time("2022-01-02")]
    assert weights.BTCUSDT == pytest.approx(0)
    assert weights.ETHUSDT == pytest.approx(1 / 14) and weights.LTCUSDT == pytest.approx(-1 / 14)
    assert weights.abs().sum() == pytest.approx(1 / 7)
    assert (result.targets.abs().sum(axis=1) <= 1 + 1e-12).all()


def test_declared_halt_retains_factor_exposure_and_never_fills_prices(monkeypatch):
    mock_eligible_models(monkeypatch)
    prices = state_prices({"2022-01-02": {"ETHUSDT": -2.5}, "2022-01-03": {"ETHUSDT": -1.0}}, end="2022-01-05")
    left, right, missing = time("2022-01-02 12:00"), time("2022-01-02 16:00"), time("2022-01-02 14:00")
    prices.loc[missing] = np.nan
    prices.attrs = {"allowed_missing_endpoints": [missing.isoformat()],
                    "halt_bridges": [{"start": left.isoformat(), "end": right.isoformat(), "source": "synthetic:test"}]}
    result = strategies.generate_factor_targets(prices)
    assert result.targets.attrs == prices.attrs
    for endpoint in pd.date_range(left, right, freq="h"):
        np.testing.assert_allclose(result.targets.loc[endpoint], result.targets.loc[left])
    assert prices.loc[missing].isna().all()
    evaluated = simulate(prices, result.targets, "2022-01-02", "2022-01-03", cost_bps=20)
    assert evaluated.frame.loc[right, "interval_hours"] == 4
    assert evaluated.frame.loc[right, "turnover"] == 0
    assert not ((evaluated.frame.index > left) & (evaluated.frame.index < right)).any()


def test_missing_btc_or_wrong_universe_fails():
    with pytest.raises(ValueError):
        strategies.generate_factor_targets(formation_prices().rename(columns={"BTCUSDT": "OTHER"}))
    with pytest.raises(ValueError):
        strategies.generate_factor_targets(formation_prices().iloc[:, :7])
