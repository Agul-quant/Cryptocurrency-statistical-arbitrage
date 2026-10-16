"""Pure attribution of saved holdings; no targets, trades or simulations created.

Per-coin contributions use actual full-L1 costs and period NAV before each
interval. Daily gross/fee vectors are normalized by that day's opening NAV,
making them additive daily return components for a correctly re-linked bootstrap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TOL = 3e-12


def _same(actual, expected, label, *, atol=TOL):
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    if a.shape != b.shape or not np.allclose(a, b, rtol=3e-10, atol=atol, equal_nan=False):
        raise AssertionError(label + " does not reconcile")


def day_labels(index):
    return (index - pd.Timedelta(nanoseconds=1)).floor("D")


def elapsed_hours(index, durations):
    """Known sparse global bridges are permitted; no inferred missing interval."""
    if (not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC" or
            index.has_duplicates or not index.is_monotonic_increasing or not index.equals(index.floor("h"))):
        raise ValueError("Exact increasing unique UTC hourly endpoints required")
    hours = np.asarray(durations, float)
    if hours.shape != (len(index),) or not np.isfinite(hours).all() or (hours < 1).any() or not np.array_equal(hours, np.rint(hours)):
        raise ValueError("Declared positive whole-hour durations required")
    if len(index) > 1 and not np.array_equal(np.diff(index.asi8) / 3_600_000_000_000, hours[1:]):
        raise ValueError("Missing/unrecognized accounting interval")
    beginnings = index - pd.to_timedelta(hours, unit="h")
    if not beginnings.floor("D").equals(day_labels(index)):
        raise ValueError("An interval crosses a UTC accounting-day boundary")
    coverage = pd.Series(hours, index=day_labels(index)).groupby(level=0).sum()
    if not coverage.eq(24).all() or not coverage.index.equals(pd.date_range(coverage.index[0], coverage.index[-1], freq="D")):
        raise ValueError("Every strategy day must be complete and contiguous; never drop strategy days")
    return hours, coverage


def factor_daily_returns(asset_returns, frame, observed=None, hold_allowed=None, mandatory_exit=None):
    """Strict 24h coin factors; a missing/inactive subinterval makes the day NaN.

    Audited global venue bridges already appear as one declared elapsed interval
    in ``asset_returns``. Individual lifecycle/migration cash gaps are never
    bridged, interpolated or treated as a zero asset return. Forced-exit days are
    also unavailable as full-day buy-and-hold factor observations.
    """
    index = frame.index
    hours, coverage = elapsed_hours(index, frame.interval_hours)
    labels = day_labels(index)
    values = asset_returns.reindex(index).copy()
    if values.columns.has_duplicates:
        raise ValueError("Duplicate coin factor columns")
    finite = np.isfinite(values.to_numpy())
    if (values.to_numpy()[finite] <= -1).any():
        raise ValueError("Coin factors require finite compoundable real returns")
    known = pd.DataFrame(finite, index=index, columns=values.columns)
    if observed is not None:
        known &= observed.reindex(index).loc[:, values.columns]
    if hold_allowed is not None:
        known &= hold_allowed.reindex(index).loc[:, values.columns]
    if mandatory_exit is not None:
        known &= ~mandatory_exit.reindex(index).loc[:, values.columns]
    # prod(min_count=...) varies by bridge day, so enforce all intraday marks.
    all_known = known.groupby(labels).all()
    compounded = (1 + values).groupby(labels).prod(min_count=1) - 1
    compounded = compounded.where(all_known)
    compounded.index.name = "utc_day"
    if not compounded.index.equals(coverage.index):
        raise AssertionError("Coin factor daily calendar changed")
    return compounded


def reconcile_path(*, prices, asset_returns, targets, held, mandatory_exit, frame, base_frame,
                   saved_linked, cost_bps=20):
    """Reconstruct exact accounting independently, then compare saved ledgers."""
    if float(cost_bps) != 20:
        raise ValueError("This diagnostic is scoped to 20bps only")
    if not held.index.equals(frame.index) or not held.columns.equals(prices.columns):
        raise ValueError("Held columns/calendar do not match the frozen basket")
    if not base_frame.index.equals(frame.index) or not saved_linked.index.equals(frame.index) or not saved_linked.columns.equals(held.columns):
        raise ValueError("Saved base/coin paths do not align")
    hours, coverage = elapsed_hours(frame.index, frame.interval_hours)
    weights = held.to_numpy(float)
    if not np.isfinite(weights).all():
        raise ValueError("Nonfinite held weight")
    rv = asset_returns.reindex(frame.index).loc[:, held.columns].to_numpy(float)
    if ((~np.isfinite(rv)) & (np.abs(weights) > 1e-14)).any():
        raise ValueError("Nonzero holding has an unobserved valuation return")
    gross = np.where(np.isfinite(rv), rv * weights, 0.)
    post = weights.copy()
    forced = mandatory_exit.loc[frame.index, held.columns].any(axis=1).to_numpy()
    post[forced] = targets.loc[frame.index, held.columns].to_numpy(float)[forced]
    previous = np.vstack([np.zeros((1, len(held.columns))), post[:-1]])
    ordinary = np.abs(weights - previous)
    event_units = np.abs(post - weights)
    terminal = np.zeros_like(weights)
    terminal[-1] = np.abs(post[-1])
    units = ordinary + event_units + terminal
    fees = units * .002
    net = gross - fees
    net_hour = net.sum(axis=1)
    if not np.isfinite(net_hour).all() or (net_hour <= -1).any():
        raise ValueError("Noncompoundable saved path")
    nav = np.cumprod(1 + net_hour)
    nav_before = np.r_[1., nav[:-1]]
    gross_linked = gross * nav_before[:, None]
    fee_linked = fees * nav_before[:, None]
    linked = gross_linked - fee_linked
    for label, actual, expected in (
        ("gross return", gross.sum(axis=1), frame.gross_return),
        ("zero-cost base gross", gross.sum(axis=1), base_frame.gross_return),
        ("base net is gross", gross.sum(axis=1), base_frame.net_return),
        ("full-L1 units", units.sum(axis=1), frame.turnover),
        ("ordinary units", ordinary.sum(axis=1), frame.ordinary_turnover),
        ("forced-event units", event_units.sum(axis=1), frame.forced_event_turnover),
        ("fees", fees.sum(axis=1), frame.cost),
        ("net return", net_hour, frame.net_return),
        ("period NAV", nav, frame.equity),
        ("saved linked coin contributions", linked, saved_linked),
        ("compounded linked return", linked.sum(), nav[-1] - 1),
    ):
        _same(actual, expected, label)
    labels = day_labels(frame.index)
    day_start_nav = pd.Series(nav_before, index=frame.index).groupby(labels).first()
    gross_daily_linked = pd.DataFrame(gross_linked, index=frame.index, columns=held.columns).groupby(labels).sum()
    fee_daily_linked = pd.DataFrame(fee_linked, index=frame.index, columns=held.columns).groupby(labels).sum()
    gross_daily = gross_daily_linked.div(day_start_nav, axis=0)
    fee_daily = fee_daily_linked.div(day_start_nav, axis=0)
    daily = pd.Series(net_hour, index=frame.index).groupby(labels).apply(lambda r: np.expm1(np.log1p(r).sum()))
    daily.index.name = "utc_day"
    _same((gross_daily - fee_daily).sum(axis=1), daily, "daily normalized contributions")
    daily_nav_before = np.r_[1., np.cumprod(1 + daily.to_numpy())[:-1]]
    _same(gross_daily.to_numpy() * daily_nav_before[:, None], gross_daily_linked, "daily gross re-link")
    _same(fee_daily.to_numpy() * daily_nav_before[:, None], fee_daily_linked, "daily fee re-link")
    _same(((gross_daily - fee_daily).to_numpy() * daily_nav_before[:, None]).sum(), nav[-1] - 1, "daily re-linked period return")
    coin = pd.DataFrame({
        "symbol": held.columns, "gross_linked_contribution": gross_linked.sum(axis=0),
        "linked_fees": fee_linked.sum(axis=0), "net_linked_contribution": linked.sum(axis=0),
        "full_l1_turnover": units.sum(axis=0), "ordinary_turnover": ordinary.sum(axis=0),
        "forced_turnover": event_units.sum(axis=0), "terminal_turnover": terminal.sum(axis=0),
    })
    audit = {"all_accounting_checks_passed": True, "elapsed_hours": int(hours.sum()), "n_days": len(daily),
             "net_return": float(nav[-1] - 1), "terminal_turnover": float(terminal.sum()),
             "forced_turnover": float(event_units.sum()), "ordinary_turnover": float(ordinary.sum()),
             "full_l1_turnover": float(units.sum()), "linked_fee_contribution": float(fee_linked.sum()),
             "max_saved_coin_link_error": float(np.max(np.abs(linked - saved_linked.to_numpy()))),
             "net_contribution_error": float(linked.sum() - (nav[-1] - 1)),
             "period_starts_from_cash": True, "terminal_liquidation_count": 1,
             "partial_event_metadata": frame.attrs.get("partial_interval_events", [])}
    return {"strategy_daily": daily, "gross_daily": gross_daily.to_numpy(), "fees_daily": fee_daily.to_numpy(),
            "coin_attribution": coin, "audit": audit}


def build_inputs(loaded=None):
    """Return compact inference-ready inputs from only the saved 27 paths."""
    if loaded is None:
        from .source import load_inputs
        loaded = load_inputs()
    from .source import STRATEGY_ORDER, PERIODS
    # Only the unchanged pure return helper is invoked, never any simulator.
    from research.top30_dev_validation.simulator import asset_returns
    panel = loaded["panel"]
    all_returns = asset_returns(panel["prices"])
    by_period = {p: {"strategy_daily": {}, "coin_daily": {}, "daily_components": {}, "symbol_map": {}} for p in PERIODS}
    rows, audits, metadata = [], [], []
    legacy_coins = loaded["legacy_coin_contributions"]
    for saved in loaded["saved"]:
        rec = saved["record"]
        sid, period, symbols = rec["comparison_id"], rec["period"], rec["symbols"]
        frame = saved["primary_path"]
        prices = panel["prices"].loc[:, symbols].copy()
        prices.attrs = dict(panel["prices"].attrs)
        result = reconcile_path(prices=prices, asset_returns=all_returns.loc[:, symbols],
                    targets=saved["targets_path"], held=saved["held_path"],
                    mandatory_exit=panel["mandatory_exit"], frame=frame,
                    base_frame=saved["base_path"], saved_linked=saved["coin_hourly_path"])
        start, end = (pd.Timestamp(t, tz="UTC") for t in PERIODS[period])
        expected = pd.date_range(start, end - pd.Timedelta(days=1), freq="D", name="utc_day")
        if not result["strategy_daily"].index.equals(expected):
            raise AssertionError("The saved strategy period must retain every requested UTC day")
        factor = factor_daily_returns(all_returns.loc[:, symbols], frame,
                    observed=panel["observed"], hold_allowed=panel["hold_allowed"], mandatory_exit=panel["mandatory_exit"])
        group = by_period[period]
        group["strategy_daily"][sid] = result["strategy_daily"]
        group["coin_daily"][sid] = factor
        group["daily_components"][sid] = {"gross": result["gross_daily"], "fees": result["fees_daily"]}
        group["symbol_map"][sid] = symbols
        coin = result["coin_attribution"]
        expected_coins = legacy_coins.loc[legacy_coins.comparison_id.eq(sid) & legacy_coins.period.eq(period)].set_index("symbol").loc[symbols]
        for key in ("gross_linked_contribution", "linked_fees", "net_linked_contribution", "full_l1_turnover", "ordinary_turnover", "forced_turnover", "terminal_turnover"):
            _same(coin[key], expected_coins[key], "legacy coin ledger " + key)
        coin["comparison_id"], coin["period"] = sid, period
        rows.append(coin)
        audit = {"comparison_id": sid, "period": period, **result["audit"]}
        audits.append(audit)
        metadata.append({"comparison_id": sid, "period": period, "symbols": symbols, "case": rec["case"],
                         "n_days": len(expected), "n_complete_factor_days": int(factor.notna().all(axis=1).sum()),
                         "n_incomplete_factor_days": int(factor.isna().any(axis=1).sum()),
                         "strategy_calendar_preserved": True, "cost_bps": 20, "execution_lag_h": 1})
    for period, group in by_period.items():
        group["strategy_daily"] = pd.DataFrame(group["strategy_daily"])[list(STRATEGY_ORDER)]
        if group["strategy_daily"].isna().any().any():
            raise AssertionError("Strategy return rows may not be dropped")
    ledger = pd.concat(rows, ignore_index=True)
    if len(ledger) != 216 or len(audits) != 27:
        raise AssertionError("Must account for all 27 paths and all 216 coin rows")
    return {"by_period": by_period, "coin_attribution": ledger, "path_audits": audits,
            "metadata": metadata, "legacy_metrics": loaded["legacy_metrics"]}
