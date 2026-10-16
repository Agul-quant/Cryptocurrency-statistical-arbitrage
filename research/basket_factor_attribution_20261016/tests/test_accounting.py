"""Synthetic, source-free accounting tests; never unpickle/decode market data."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.basket_factor_attribution_20261016.accounting import (
    day_labels, elapsed_hours, factor_daily_returns, reconcile_path,
)


def synthetic_path(*, flat=False):
    full = pd.date_range("2022-01-01", periods=49, freq="h", tz="UTC", name="bar_end")
    columns = ["BTCUSDT", "ETHUSDT"]
    rv = np.column_stack([np.linspace(-.002, .003, 48), np.linspace(.004, -.001, 48)])
    price_values = np.vstack([np.ones(2), np.cumprod(1 + rv, axis=0)]) * 100
    prices = pd.DataFrame(price_values, index=full, columns=columns)
    index = full[1:]
    weights = np.tile([.4, -.2], (48, 1))
    if flat:
        weights[:] = 0
    else:
        weights[10:, 0] = 0
        weights[25:, 1] = -.1
    targets = pd.DataFrame(0., index=full, columns=columns)
    targets.loc[:, "ETHUSDT"] = -.2 if not flat else 0.
    targets.loc[full[26]:, "ETHUSDT"] = -.1 if not flat else 0.
    exits = pd.DataFrame(False, index=full, columns=columns)
    exits.loc[index[9], "BTCUSDT"] = True
    post = weights.copy()
    post[9] = targets.loc[index[9]].to_numpy()
    previous = np.vstack([np.zeros(2), post[:-1]])
    ordinary = np.abs(weights - previous)
    forced = np.abs(post - weights)
    terminal = np.zeros_like(weights)
    terminal[-1] = np.abs(post[-1])
    units = ordinary + forced + terminal
    gross = rv * weights
    fee = units * .002
    net = (gross - fee).sum(axis=1)
    nav = np.cumprod(1 + net)
    nav_before = np.r_[1., nav[:-1]]
    frame = pd.DataFrame({"gross_return": gross.sum(axis=1), "net_return": net,
            "ordinary_turnover": ordinary.sum(axis=1), "forced_event_turnover": forced.sum(axis=1),
            "turnover": units.sum(axis=1), "cost": fee.sum(axis=1), "equity": nav,
            "interval_hours": 1}, index=index)
    frame.attrs["partial_interval_events"] = [{"symbol": "BTCUSDT", "event_time": "2022-01-01T09:40:00Z", "bucket_end": index[9].isoformat(), "post_event_weight": 0.}]
    base = frame.copy()
    base["net_return"] = base.gross_return
    base["cost"] = 0.
    base["equity"] = np.cumprod(1 + base.net_return)
    return {"prices": prices, "asset_returns": pd.DataFrame(rv, index=index, columns=columns),
            "targets": targets, "held": pd.DataFrame(weights, index=index, columns=columns),
            "mandatory_exit": exits, "frame": frame, "base_frame": base,
            "saved_linked": pd.DataFrame((gross-fee)*nav_before[:, None], index=index, columns=columns)}


def test_compounded_coin_contributions_reconcile_with_once_terminal_and_forced_fees():
    x = synthetic_path()
    result = reconcile_path(**x)
    coin = result["coin_attribution"]
    np.testing.assert_allclose(coin.net_linked_contribution.sum(), x["frame"].equity.iloc[-1] - 1)
    np.testing.assert_allclose(coin.terminal_turnover.sum(), .1)
    np.testing.assert_allclose(coin.forced_turnover.sum(), .4)
    assert result["audit"]["terminal_liquidation_count"] == 1
    assert result["audit"]["n_days"] == 2
    assert len(result["audit"]["partial_event_metadata"]) == 1


def test_daily_components_are_daily_returns_not_period_linked_values():
    x = synthetic_path()
    result = reconcile_path(**x)
    daily = result["strategy_daily"].to_numpy()
    np.testing.assert_allclose((result["gross_daily"] - result["fees_daily"]).sum(axis=1), daily)
    np.testing.assert_allclose(((result["gross_daily"] - result["fees_daily"]) * np.r_[1., 1+daily[0]][:, None]).sum(), x["frame"].equity.iloc[-1]-1)
    assert not np.isclose(daily.sum(), x["frame"].equity.iloc[-1]-1, atol=1e-10)


def test_genuine_all_cash_remains_evaluated():
    result = reconcile_path(**synthetic_path(flat=True))
    assert result["audit"]["net_return"] == 0
    assert np.count_nonzero(result["gross_daily"]) == 0
    assert np.count_nonzero(result["fees_daily"]) == 0


def test_saved_link_tamper_fails():
    x = synthetic_path()
    x["saved_linked"].iloc[-1, 0] += 1e-4
    with pytest.raises(AssertionError, match="saved linked coin"):
        reconcile_path(**x)


def test_terminal_fee_tamper_fails():
    x = synthetic_path()
    x["frame"].loc[x["frame"].index[-1], "turnover"] -= .1
    with pytest.raises(AssertionError, match="full-L1"):
        reconcile_path(**x)


def test_unobserved_return_with_nonzero_weight_is_error():
    x = synthetic_path()
    x["asset_returns"].iloc[3, 0] = np.nan
    with pytest.raises(ValueError, match="Nonzero holding"):
        reconcile_path(**x)


def test_factor_missing_interior_does_not_use_finite_day_endpoints():
    x = synthetic_path()
    ret = x["asset_returns"].copy()
    ret.iloc[3, 0] = np.nan
    daily = factor_daily_returns(ret, x["frame"])
    assert np.isnan(daily.iloc[0, 0])
    assert np.isfinite(daily.iloc[0, 1])
    assert np.isfinite(daily.iloc[1, 0])


def test_inactive_cash_slot_or_mandatory_exit_not_zero_factor_return():
    x = synthetic_path()
    hold = pd.DataFrame(True, index=x["prices"].index, columns=x["prices"].columns)
    hold.iloc[28, 1] = False
    daily = factor_daily_returns(x["asset_returns"], x["frame"], hold_allowed=hold, mandatory_exit=x["mandatory_exit"])
    assert np.isnan(daily.iloc[0, 0])  # Partial event is not a whole-day coin factor.
    assert np.isnan(daily.iloc[1, 1])
    assert np.isfinite(daily.iloc[1, 0])


def test_venue_bridge_keeps_complete_elapsed_day_and_real_reopening_move():
    from research.top30_dev_validation.simulator import asset_returns
    x = synthetic_path()
    prices = x["prices"].copy()
    left, right = prices.index[11], prices.index[15]
    prices.loc[(prices.index > left) & (prices.index < right)] = np.nan
    prices.attrs["halt_bridges"] = [{"start": left.isoformat(), "end": right.isoformat(), "source": "synthetic-audited-halt"}]
    ret = asset_returns(prices)
    frame = pd.DataFrame({"interval_hours": [4 if t == right else 1 for t in ret.index]}, index=ret.index)
    daily = factor_daily_returns(ret, frame)
    direct = prices.loc[prices.index[24]].to_numpy()/prices.iloc[0].to_numpy()-1
    np.testing.assert_allclose(daily.iloc[0].to_numpy(), direct)
    assert len(ret) == 45
    assert frame.interval_hours.sum() == 48


def test_unrecognized_missing_interval_does_not_shorten_strategy_days():
    x = synthetic_path()
    broken = x["frame"].drop(x["frame"].index[4])
    with pytest.raises(ValueError, match="Missing/unrecognized"):
        elapsed_hours(broken.index, broken.interval_hours)


def test_midnight_endpoint_is_previous_day():
    clock = pd.DatetimeIndex(["2026-10-01T00:00:00Z"])
    assert day_labels(clock)[0] == pd.Timestamp("2026-09-30T00:00:00Z")


def test_partial_day_is_not_silently_dropped():
    x = synthetic_path()
    shortened = x["frame"].iloc[1:]
    with pytest.raises(ValueError, match="complete and contiguous"):
        elapsed_hours(shortened.index, shortened.interval_hours)


def test_source_catalog_is_exact_27_paths_and_does_not_decode_parquet(monkeypatch):
    from research.basket_factor_attribution_20261016.source import metadata_catalog
    monkeypatch.setattr(pd, "read_parquet", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Forbidden market decode")))
    result = metadata_catalog()
    assert len(result["records"]) == 27
    assert len({(r["comparison_id"], r["period"]) for r in result["records"]}) == 27
    assert all(r["execution_lag_h"] == 1 for r in result["records"])
    assert result["expected_coin_rows"] == 216
    assert all(r["comparison_id"] != "B02" for r in result["records"])
