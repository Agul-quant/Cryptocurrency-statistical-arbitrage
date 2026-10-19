"""Exact-hour performance with explicitly separate complete-UTC-day risk metrics.

No sources, signals or trades are created here. Inherited public APIs remain
unchanged. A risk-only view rebases already-saved NAV without cash resets,
liquidation, fee reassignment or a second simulation. Opening/closing partial
days remain in full-hour performance, and are excluded only from daily moments.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd


DAILY_FIELDS = (
    'annual_return', 'annual_volatility', 'sharpe', 'sortino',
    'daily_downside_deviation', 'es95', 'es95_daily_loss', 'worst_day_return',
    'worst_day_date', 'worst_7day_return', 'worst_7day_start', 'worst_7day_end',
    'daily_win_rate', 'zero_daily_return_fraction', 'daily_gain_loss_ratio',
    'alpha_annual', 'beta', 'alpha_tstat', 'alpha_pvalue', 'alpha_ci_low',
    'alpha_ci_high', 'beta_ci_low', 'beta_ci_high', 'btc_beta',
    'btc_alpha_annual', 'btc_alpha_ci_low', 'btc_alpha_ci_high',
    'btc_beta_ci_low', 'btc_beta_ci_high',
)


def complete_day_mask(frame):
    """Return elapsed-hour coverage and a contiguous complete UTC day mask."""
    index = frame.index
    if (not isinstance(index, pd.DatetimeIndex) or str(index.tz) != 'UTC'
            or index.has_duplicates or not index.is_monotonic_increasing
            or not len(index) or not index.equals(index.floor('h'))):
        raise ValueError('Exact sorted unique UTC hourly endpoints required.')
    hours = (frame.interval_hours.to_numpy(dtype=float)
             if 'interval_hours' in frame else np.ones(len(frame)))
    if (not np.isfinite(hours).all() or (hours < 1).any()
            or not np.array_equal(hours, np.rint(hours))):
        raise ValueError('Known positive whole-hour interval durations required.')
    if len(index) > 1 and not np.array_equal(
            np.diff(index.asi8) / 3_600_000_000_000, hours[1:]):
        raise ValueError('Missing or overlapping hourly accounting intervals.')
    labels = (index - pd.Timedelta(nanoseconds=1)).floor('D')
    beginnings = index - pd.to_timedelta(hours, unit='h')
    if not beginnings.floor('D').equals(labels):
        raise ValueError('Intervals cannot cross UTC interval-day boundaries.')
    coverage = pd.Series(hours, index=index).groupby(labels).sum()
    if (coverage > 24).any() or (len(coverage) > 1 and not (
            np.diff(coverage.index.asi8) == 86_400_000_000_000).all()):
        raise ValueError('Incomplete calendar grid or excess daily coverage.')
    if len(coverage) > 2 and not coverage.iloc[1:-1].eq(24).all():
        raise ValueError('Only opening/closing days may be partial.')
    days = coverage.index[coverage.eq(24)]
    mask = np.asarray(labels.isin(days))
    return hours, labels, coverage, mask


def _risk_result(result, mask, backtest):
    frame = result.frame.loc[mask].copy()
    frame['equity'] = np.cumprod(1 + frame.net_return.to_numpy(dtype=float))
    frame['drawdown'] = frame.equity / frame.equity.cummax().clip(lower=1) - 1
    frame.attrs = dict(result.frame.attrs)
    return backtest.BacktestResult(frame, result.held_weights.loc[mask].copy())


def summarize_full(result, case, benchmark, modules):
    """Return flat scalar metrics; ``n_days`` means complete UTC risk days.

    ``total_return``, ``cagr``, drawdowns, fees, turnover and exposures use all
    requested hours. Daily moments/tails/HAC attribution use only complete UTC
    days from the original full path. Explicit coverage/edge fields prevent
    mistaking those two bases for a shortened evaluation window.
    """
    _, _, metrics, extras, backtest = modules
    frame, held = result.frame, result.held_weights
    required = {'net_return', 'gross_return', 'turnover', 'cost', 'equity', 'drawdown'}
    if not required.issubset(frame) or not held.index.equals(frame.index):
        raise ValueError('Matching complete saved result frame/held weights required.')
    values = frame.net_return.to_numpy(dtype=float)
    gross = frame.gross_return.to_numpy(dtype=float)
    fees = frame.cost.to_numpy(dtype=float)
    turn = frame.turnover.to_numpy(dtype=float)
    if (not np.isfinite(np.r_[values, gross, fees, turn]).all()
            or (values <= -1).any() or (gross <= -1).any()
            or (fees < 0).any() or (turn < 0).any()
            or not np.allclose(values, gross - fees, rtol=0, atol=2e-14)):
        raise ValueError('Saved accounting must be finite, compoundable and reconcile.')
    expected_equity = np.cumprod(1 + values)
    if not np.allclose(frame.equity, expected_equity, rtol=1e-12, atol=1e-14):
        raise ValueError('Saved full NAV does not reconcile to hourly compounding.')
    hours, labels, coverage, mask = complete_day_mask(frame)
    elapsed = float(hours.sum() / 24)
    if mask.sum() < 24:
        raise ValueError('At least one complete UTC day required for this study.')
    risk = _risk_result(result, mask, backtest)
    risk_summary = {**metrics.summarize(risk, benchmark),
                    **extras.extra_metrics(risk, case['family'], benchmark)}
    gross_frame = risk.frame.copy()
    gross_frame['net_return'] = gross_frame.gross_return
    gross_frame['cost'] = 0.
    gross_frame['equity'] = np.cumprod(1 + gross_frame.net_return.to_numpy())
    gross_frame['drawdown'] = gross_frame.equity / gross_frame.equity.cummax().clip(lower=1) - 1
    gross_stats = metrics.summarize(backtest.BacktestResult(gross_frame, risk.held_weights), benchmark)
    stats = dict(risk_summary)
    full_log = math.fsum(np.log1p(values))
    gross_log = math.fsum(np.log1p(gross))
    pi = extras.pi
    dd = pi.drawdown_statistics(values, frame.index, elapsed, hours)
    _, exposure, exposure_meta = extras._exposures(
        held, case['family'], frame, hours)
    logs = np.r_[0., np.cumsum(np.log1p(values))]
    depth = -np.expm1(logs[1:] - np.maximum.accumulate(logs)[1:])
    with np.errstate(over='ignore'):
        cagr = float(np.expm1(full_log * 365 / elapsed))
    cagr = cagr if np.isfinite(cagr) else None
    total_turnover = math.fsum(turn)
    partial = coverage[coverage.ne(24)]
    # Partial groups are descriptive only; their fees and returns remain in NAV.
    partial_records = []
    for day, duration in partial.items():
        edge = np.asarray(labels == day)
        partial_records.append({
            'day': day.date().isoformat(), 'hours': float(duration),
            'net_return': float(np.expm1(math.fsum(np.log1p(values[edge])))),
            'gross_return': float(np.expm1(math.fsum(np.log1p(gross[edge])))),
            'turnover': math.fsum(turn[edge]), 'cost_sum': math.fsum(fees[edge]),
        })
    stats.update(
        total_return=float(np.expm1(full_log)), log_total_return=full_log,
        gross_total_return=float(np.expm1(gross_log)), gross_sharpe=gross_stats['sharpe'],
        cagr=cagr, max_drawdown=dd['max_drawdown'],
        calmar=cagr / dd['max_drawdown'] if cagr is not None and dd['max_drawdown'] > 0 else None,
        ulcer_index=math.sqrt(float(np.dot(depth * depth, hours) / hours.sum())),
        ulcer_time_basis='full requested elapsed hours, observed endpoint drawdowns',
        total_turnover=total_turnover, total_cost_sum=math.fsum(fees),
        mean_hourly_turnover=total_turnover / hours.sum(),
        mean_daily_turnover=total_turnover / elapsed,
        annualized_turnover=total_turnover * 365 / elapsed,
        annualized_full_l1_turnover=total_turnover * 365 / elapsed,
        n_hours=int(hours.sum()), n_observations=len(frame), elapsed_days=elapsed,
        n_days=int(coverage.eq(24).sum()), n_complete_utc_days=int(coverage.eq(24).sum()),
        first_day=labels[0].date().isoformat(), last_day=labels[-1].date().isoformat(),
        full_period_start=(frame.index[0] - pd.Timedelta(hours=float(hours[0]))).isoformat(),
        full_period_end=frame.index[-1].isoformat(),
        risk_period_start=(risk.frame.index[0] - pd.Timedelta(hours=float(risk.frame.interval_hours.iloc[0]))).isoformat(),
        risk_period_end=risk.frame.index[-1].isoformat(),
        risk_first_day=coverage.index[coverage.eq(24)][0].date().isoformat(),
        risk_last_day=coverage.index[coverage.eq(24)][-1].date().isoformat(),
        risk_hours=int(hours[mask].sum()), partial_day_count=len(partial),
        partial_hours=int(hours[~mask].sum()), partial_cost_sum=math.fsum(fees[~mask]),
        partial_turnover=math.fsum(turn[~mask]),
        partial_net_return=float(np.expm1(math.fsum(np.log1p(values[~mask])))),
        partial_gross_return=float(np.expm1(math.fsum(np.log1p(gross[~mask])))),
        partial_day_records_json=__import__('json').dumps(partial_records, sort_keys=True),
        daily_risk_basis='complete contiguous 24-hour UTC days from original saved path; boundary partial days excluded only from daily statistics',
        full_performance_basis='every requested hourly interval including opening/closing partial days, entry and terminal liquidation',
        risk_slice_rebased_without_resimulation=True,
        partial_fees_reallocated=False, partial_returns_annualized=False,
        bootstrap_status='not_calculated_for_all_configurations',
    )
    stats.update({'dd_' + key: value for key, value in dd.items()})
    stats.update(exposure)
    stats.update(exposure_meta)
    return extras._clean(stats)
