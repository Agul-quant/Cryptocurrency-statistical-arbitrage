"""Fixed-path performance, exposure and BTC attribution diagnostics."""
from __future__ import annotations

from collections.abc import Mapping
import math

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import performance_indicators as pi

YEAR_DAYS = 365.0
DEFAULT_PERIOD_SEED = 20261009
NS_PER_HOUR = 3_600_000_000_000
WEIGHT_TOLERANCE = 1e-12


def _utc(value):
    result = pd.Timestamp(value)
    if pd.isna(result):
        raise ValueError('Event timestamp cannot be missing.')
    return result.tz_localize('UTC') if result.tz is None else result.tz_convert('UTC')


def _clean(value):
    """Native JSON values, retaining undefined statistics as None, never NaN."""
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _finite(value):
    return float(value) if np.isfinite(value) else None


def _expm1(value):
    with np.errstate(over='ignore'):
        return _finite(np.expm1(value))


def _durations(frame, index):
    if 'interval_hours' in frame:
        values = frame.interval_hours.to_numpy(dtype=float)
    elif frame.attrs.get('interval_hours'):
        declared = frame.attrs['interval_hours']
        if not isinstance(declared, Mapping):
            raise ValueError('interval_hours metadata must be an endpoint-duration mapping.')
        declared = {_utc(t): float(hours) for t, hours in declared.items()}
        values = np.array([declared.get(t, 1.0) for t in index])
    elif len(index) > 1:
        gaps = np.diff(index.asi8) / NS_PER_HOUR
        if not np.all(gaps == gaps[0]):
            raise ValueError('Irregular endpoints require explicit interval_hours.')
        values = np.full(len(index), gaps[0])
    else:
        # This API is hourly by default; a one-day singleton needs an explicit
        # 24-hour duration instead of an invented first observation duration.
        values = np.ones(len(index))
    if values.ndim != 1 or len(values) != len(index) or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('Interval durations must be finite, positive and same length as returns.')
    return values


def _exposure_rows(weights, family, columns):
    weights = np.atleast_2d(np.asarray(weights, dtype=float))
    gross = np.abs(weights).sum(axis=1)
    long = np.maximum(weights, 0).sum(axis=1)
    short = -np.minimum(weights, 0).sum(axis=1)
    fields = {'gross': gross, 'net': weights.sum(axis=1), 'long': long, 'short': short,
              'unused_gross_budget': np.maximum(1 - gross, 0),
              'flat_fraction': (gross == 0).astype(float)}
    if family.startswith('trend_long_cash'):
        if (weights < -WEIGHT_TOLERANCE).any():
            raise ValueError('Long/cash family cannot have negative held weights.')
        fields['cash_allocation'] = np.maximum(1 - long, 0)
        fields['inactive_slot_budget'] = (np.abs(weights) <= WEIGHT_TOLERANCE).sum(axis=1) / len(columns)
    elif family.startswith('trend_long_short'):
        fields['inactive_slot_budget'] = (np.abs(weights) <= WEIGHT_TOLERANCE).sum(axis=1) / len(columns)
    elif family.startswith('factor_residual'):
        if 'BTCUSDT' not in columns or len(columns) < 2:
            raise ValueError('Factor exposure requires BTCUSDT and at least one fixed non-BTC slot.')
        positions = [i for i, name in enumerate(columns) if name != 'BTCUSDT']
        active = (np.abs(weights[:, positions]) > WEIGHT_TOLERANCE).sum(axis=1)
        fields['unallocated_spread_budget'] = 1 - active / len(positions)
    return fields


def _exposures(held, family, frame, hours):
    """Integrate documented symbol-only partial events, never prorate returns.

    Other assets (including a BTC hedge) retain the interval's held allocation
    until its completed endpoint. This preserves the explicitly modeled orphan
    hedge interval instead of pretending portfolio-wide neutrality at 00:40.
    """
    matrix = held.to_numpy(dtype=float)
    fields = _exposure_rows(matrix, family, held.columns)
    result = pd.DataFrame(fields, index=held.index)
    minima = {key: float(np.min(value)) for key, value in fields.items() if key != 'flat_fraction'}
    maxima = {key: float(np.max(value)) for key, value in fields.items() if key != 'flat_fraction'}
    structured = 'partial_interval_events' in frame.attrs
    events = frame.attrs.get('partial_interval_events', [])
    if not isinstance(events, (list, tuple)):
        raise ValueError('partial_interval_events must be a list of sourced accounting-event records.')
    warning = frame.attrs.get('partial_event_exposure_warning', '')
    by_bucket = {}
    applicable = unadjusted = active_events = 0
    first_start = held.index[0] - pd.Timedelta(int(np.rint(hours[0] * NS_PER_HOUR)), unit='ns')
    for event in events:
        if not isinstance(event, Mapping) or not {'symbol', 'event_time', 'bucket_end'}.issubset(event):
            raise ValueError('Partial event needs symbol, event_time and bucket_end.')
        time, end = _utc(event['event_time']), _utc(event['bucket_end'])
        if time < first_start or time >= held.index[-1]:
            continue  # Full-history attrs may be inherited by a later period.
        if end not in held.index or event['symbol'] not in held.columns:
            raise ValueError('Applicable partial-event symbol/bucket is missing.')
        position = held.index.get_loc(end)
        start = end - pd.Timedelta(int(np.rint(hours[position] * NS_PER_HOUR)), unit='ns')
        if not start < time < end:
            raise ValueError('Partial event must occur strictly inside its declared accounting interval.')
        applicable += 1
        if 'post_event_weight' not in event:
            unadjusted += 1
            continue  # Flag-only: do not invent a post-event weight or execution.
        post = float(event['post_event_weight'])
        if not np.isfinite(post):
            raise ValueError('Partial-event post weight must be finite.')
        by_bucket.setdefault(position, []).append((time, event, post))
    for position, bucket_events in by_bucket.items():
        end = held.index[position]
        start = end - pd.Timedelta(int(np.rint(hours[position] * NS_PER_HOUR)), unit='ns')
        state = matrix[position].copy()
        cursor = start
        accumulated = {key: 0.0 for key in fields}
        def integrate(stop):
            instant = _exposure_rows(state, family, held.columns)
            fraction = float((stop - cursor) / pd.Timedelta(hours=hours[position]))
            for key, value in instant.items():
                accumulated[key] += fraction * float(value[0])
                if key != 'flat_fraction':
                    minima[key] = min(minima[key], float(value[0]))
                    maxima[key] = max(maxima[key], float(value[0]))
        for time, event, post in sorted(bucket_events, key=lambda item: item[0]):
            if time < cursor:
                raise ValueError('Partial event ordering is invalid.')
            column = held.columns.get_loc(event['symbol'])
            declared_pre = event.get('pre_event_weight', event.get('previous_weight'))
            if declared_pre is not None and (not np.isfinite(float(declared_pre)) or not np.isclose(float(declared_pre), state[column], rtol=0, atol=WEIGHT_TOLERANCE)):
                raise ValueError('Declared pre-event weight does not match the supplied held path.')
            active_events += abs(state[column]) > WEIGHT_TOLERANCE
            integrate(time)
            cursor = time
            state[column] = post
        integrate(end)
        for key, value in accumulated.items():
            result.iloc[position, result.columns.get_loc(key)] = value
    unknown_warning = bool(warning) and not structured
    adjusted_count = applicable - unadjusted
    adjusted = adjusted_count > 0
    unknown = unadjusted > 0 or unknown_warning
    basis = ('partial-event elapsed adjusted'
             if adjusted else 'accounting interval held weights')
    if unknown:
        basis += '; actual intrahour path unobserved'
    metadata = {
        'partial_event_count': applicable if structured else None if unknown_warning else 0,
        'partial_event_adjusted_count': adjusted_count,
        'partial_event_active_count': int(active_events),
        'partial_event_exposure_adjusted': adjusted,
        'partial_event_exposure_unadjusted': unknown,
        'partial_event_exposure_warning': str(warning) if applicable or unknown_warning else '',
        'exposure_time_basis': basis,
        'partial_event_return_accounting': 'returns/costs retain original accounting buckets; not prorated or resimulated',
        'partial_event_other_assets_convention': 'other held assets/hedges remain until completed bucket endpoint; possible temporary loss of neutrality',
        'intrahour_mark_to_market_unobserved': True,
        'temporary_orphan_hedge_possible': bool(applicable and family.startswith('factor_residual')),
        'n_asset_slots': len(held.columns),
        'n_factor_spread_slots': len(held.columns) - 1 if family.startswith('factor_residual') else None,
    }
    summary = pi.exposure_statistics(result, held.index, hours.sum() / 24, hours)
    for key in minima:
        values = result[key].to_numpy()
        summary['mean_' + key] = float(values[0]) if np.max(values) == np.min(values) else float(np.dot(values, hours) / hours.sum())
        summary['min_' + key] = minima[key]
        summary['max_' + key] = maxima[key]
    summary['fraction_flat'] = float(np.dot(result.flat_fraction.to_numpy(), hours) / hours.sum())
    summary['averaging'] = basis
    summary['cash_inferred_from_unused_gross'] = False
    return result, summary, metadata


def _benchmark_daily(benchmark_hourly, index, hours, elapsed_days):
    if benchmark_hourly is None:
        return None
    if not isinstance(benchmark_hourly, pd.Series) or not isinstance(benchmark_hourly.index, pd.DatetimeIndex) or benchmark_hourly.index.tz is None:
        raise ValueError('benchmark_hourly must be an aware timestamp-indexed Series of simple returns, not prices.')
    if benchmark_hourly.index.has_duplicates or benchmark_hourly.index.hasnans:
        raise ValueError('Benchmark endpoints must be unique and finite.')
    benchmark = benchmark_hourly.copy()
    benchmark.index = benchmark.index.tz_convert('UTC')
    values = benchmark.reindex(index).to_numpy(dtype=float)
    daily = pi.calendar_daily_path(values, values, np.zeros(len(values)), index, elapsed_days, hours)
    return daily.net_return.rename('BTCUSDT')


def _context(result, family, benchmark_hourly):
    if not isinstance(family, str) or not family:
        raise ValueError('family must be a nonempty string.')
    if not hasattr(result, 'frame') or not hasattr(result, 'held_weights'):
        raise ValueError('result must provide frame and held_weights.')
    frame, held = result.frame, result.held_weights
    if not isinstance(frame, pd.DataFrame) or not isinstance(held, pd.DataFrame):
        raise ValueError('Result frames must be DataFrames.')
    if not {'net_return', 'gross_return', 'turnover'}.issubset(frame.columns):
        raise ValueError('Result requires net_return, gross_return and turnover.')
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError('Return endpoints must be timezone-aware.')
    if not frame.index.equals(held.index) or held.shape[1] == 0 or held.columns.has_duplicates:
        raise ValueError('Held asset columns/endpoints must be nonempty, unique, and match the return frame.')
    index = frame.index.tz_convert('UTC').as_unit('ns')
    held = held.astype(float).copy()
    held.index = index
    if not np.isfinite(held.to_numpy()).all():
        raise ValueError('Held weights must be finite.')
    hours = _durations(frame, index)
    elapsed = float(hours.sum() / 24)
    daily = pi.calendar_daily_path(frame.net_return, frame.gross_return, frame.turnover, index, elapsed, hours)
    if 'cost' in frame:
        cost = frame.cost.to_numpy(dtype=float)
        if not np.isfinite(cost).all() or (cost < 0).any() or not np.allclose(frame.net_return, frame.gross_return - cost, rtol=0, atol=2e-14):
            raise ValueError('Saved net returns must reconcile to gross minus finite nonnegative interval costs.')
    exposures, exposure_summary, exposure_metadata = _exposures(held, family, frame, hours)
    benchmark = _benchmark_daily(benchmark_hourly, index, hours, elapsed)
    return dict(frame=frame, index=index, hours=hours, elapsed=elapsed, daily=daily,
                exposures=exposures, exposure_summary=exposure_summary,
                exposure_metadata=exposure_metadata, benchmark=benchmark)


def _attribution(daily, benchmark):
    empty = {key: None for key in ['btc_beta', 'btc_alpha_annual', 'btc_alpha_ci_low', 'btc_alpha_ci_high', 'btc_beta_ci_low', 'btc_beta_ci_high']}
    if benchmark is None or len(daily) < 3 or benchmark.max() == benchmark.min():
        return empty
    fit = sm.OLS(daily.net_return.to_numpy(), sm.add_constant(benchmark.to_numpy(), has_constant='add')).fit(cov_type='HAC', cov_kwds={'maxlags': 7})
    confidence = fit.conf_int(alpha=.05)
    return _clean({'btc_beta': fit.params[1], 'btc_alpha_annual': fit.params[0] * YEAR_DAYS,
                   'btc_alpha_ci_low': confidence[0, 0] * YEAR_DAYS,
                   'btc_alpha_ci_high': confidence[0, 1] * YEAR_DAYS,
                   'btc_beta_ci_low': confidence[1, 0], 'btc_beta_ci_high': confidence[1, 1]})


def _extra(context):
    frame, daily, hours = context['frame'], context['daily'], context['hours']
    values = daily.net_return.to_numpy()
    scale = float(np.max(np.abs(values))) or 1.0
    normalized = values / scale
    mean = float(normalized.mean())
    std = (0.0 if values.max() == values.min() else float(normalized.std(ddof=1))) if len(values) >= 2 else None
    downside_values = np.minimum(values, 0)
    downside_scale = float(np.max(np.abs(downside_values)))
    downside_norm = float(np.sqrt(np.mean((downside_values / downside_scale) ** 2))) if downside_scale else 0.0
    with np.errstate(over='ignore'):
        annual_return = _finite(mean * YEAR_DAYS * np.float64(scale))
        annual_vol = _finite(std * math.sqrt(YEAR_DAYS) * np.float64(scale)) if std is not None else None
        sharpe = _finite(mean / std * math.sqrt(YEAR_DAYS)) if std is not None and std > 0 else None
        sortino = _finite(mean * (np.float64(scale) / downside_scale) / downside_norm * math.sqrt(YEAR_DAYS)) if downside_norm else None
    log_total = math.fsum(daily.net_log_return.to_numpy())
    cagr = _expm1(log_total * YEAR_DAYS / context['elapsed'])
    dd = pi.drawdown_statistics(frame.net_return, context['index'], context['elapsed'], hours)
    logs = np.r_[0.0, np.cumsum(np.log1p(frame.net_return.to_numpy(dtype=float)))]
    endpoint_depth = -np.expm1(logs[1:] - np.maximum.accumulate(logs)[1:])
    ulcer = math.sqrt(float(np.dot(endpoint_depth ** 2, hours) / hours.sum()))
    worst = int(np.argmin(daily.net_log_return.to_numpy()))
    weekly_return = weekly_start = weekly_end = None
    if len(daily) >= 7:
        weekly = np.convolve(daily.net_log_return.to_numpy(), np.ones(7), mode='valid')
        position = int(np.argmin(weekly))
        weekly_return = _expm1(float(weekly[position]))
        weekly_start = daily.index[position].date().isoformat()
        weekly_end = daily.index[position + 6].date().isoformat()
    gains, losses = float(np.maximum(normalized, 0).sum()), float(-np.minimum(normalized, 0).sum())
    turnover = float(frame.turnover.sum())
    fields = {
        'n_observations': len(frame), 'n_days': len(daily), 'elapsed_days': context['elapsed'],
        'n_hours': float(hours.sum()), 'first_day': daily.index[0].date().isoformat(), 'last_day': daily.index[-1].date().isoformat(),
        'total_return': _expm1(log_total), 'log_total_return': log_total, 'cagr': cagr,
        'gross_total_return': _expm1(math.fsum(daily.gross_log_return.to_numpy())),
        'annual_return': annual_return, 'annual_volatility': annual_vol, 'sharpe': sharpe, 'sortino': sortino,
        'daily_downside_deviation': downside_norm * downside_scale,
        'es95': pi.expected_shortfall(values),
        'worst_day_return': float(values[worst]), 'worst_day_date': daily.index[worst].date().isoformat(),
        'worst_7day_return': weekly_return, 'worst_7day_start': weekly_start, 'worst_7day_end': weekly_end,
        'max_drawdown': dd['max_drawdown'],
        'calmar': cagr / dd['max_drawdown'] if cagr is not None and dd['max_drawdown'] > 0 else None,
        'ulcer_index': ulcer, 'ulcer_time_basis': 'elapsed interval duration weighted observed-endpoint drawdown RMS',
        'total_turnover': turnover, 'mean_daily_turnover': turnover / context['elapsed'],
        'annualized_turnover': turnover * YEAR_DAYS / context['elapsed'],
        'annualized_full_l1_turnover': turnover * YEAR_DAYS / context['elapsed'],
        'entry_liquidation_included_if_present_in_input': True,
        'daily_win_rate': float(np.mean(values > 0)), 'zero_daily_return_fraction': float(np.mean(values == 0)),
        'daily_gain_loss_ratio': gains / losses if losses > 0 else None,
        'trade_profit_factor_status': 'undefined_without_portfolio_trade_grouping',
        'turnover_convention': 'supplied full-L1 target changes including entry/liquidation; not drift-adjusted actual notional/NAV',
        'capacity_status': 'not_identifiable_from_fixed_path_price_only_model',
        'bootstrap_status': 'not_calculated_for_all_configurations',
    }
    fields['es95_daily_loss'] = -fields['es95']
    fields.update({'dd_' + key: value for key, value in dd.items()})
    fields.update(context['exposure_summary'])
    fields.update(context['exposure_metadata'])
    fields.update(_attribution(daily, context['benchmark']))
    return _clean(fields)


def extra_metrics(result, family, benchmark_hourly=None) -> dict:
    """Flat all-configuration diagnostics, no bootstrap/rolling/strategy rerun.

    Fixed-slot counts are inferred from held columns (30 assets / 29 spreads in
    the requested study). Partial-event metadata may adjust exposures only;
    returns, fees and turnover always retain their saved accounting path.
    """
    return _extra(_context(result, family, benchmark_hourly))


def detailed_selected(result, family, benchmark_hourly=None,
                      periodseed: int = DEFAULT_PERIOD_SEED, *,
                      bootstrap_plan=None, include_rolling: bool = True) -> dict:
    """Selected fixed-path details, nominal paired-ready block intervals.

    ``periodseed`` is the fourth positional argument. For paired costs/models,
    reuse a compact ``pi.circular_block_plan(n_days, 4000, 28, periodseed)`` via
    ``bootstrap_plan`` or use the same seed for exactly matching calendar dates.
    Returned scalar dictionaries are JSON-safe; only ``rolling`` needs separate
    CSV/Parquet export. No comprehensive research-history DSR is asserted.
    """
    context = _context(result, family, benchmark_hourly)
    frame, daily = context['frame'], context['daily']
    generic = pi.summarize_performance(
        frame.net_return, frame.gross_return, frame.turnover, context['index'],
        context['elapsed'], context['hours'], bootstrap_plan=bootstrap_plan,
        exposures=context['exposures'], benchmark_daily=context['benchmark'],
        include_rolling=include_rolling, bootstrap_samples=4000,
        bootstrap_seed=periodseed, bootstrap_block_days=28)
    summary = _extra(context)
    bootstrap, fee = generic['bootstrap'], generic['break_even']
    summary['bootstrap_status'] = 'computed_selected_fixed_path_nominal_not_search_adjusted'
    for name in ['sharpe', 'total_return', 'cagr', 'log_total_return']:
        summary[name + '_ci_low'], summary[name + '_ci_high'] = bootstrap[name + '_ci']
    summary.update(bootstrap_valid_sharpe_samples=bootstrap['valid_sharpe_samples'],
                   bootstrap_total_samples=bootstrap['samples'], bootstrap_block_days=bootstrap['block_days'],
                   bootstrap_seed=bootstrap['seed'], nominal_ci_not_search_adjusted=True,
                   bootstrap_sharpe_conditioned_on_defined_samples=bootstrap['sharpe_conditioned_on_defined_samples'])
    summary.update({'break_even_' + key: value for key, value in fee.items()})
    rolling = generic['rolling']
    if rolling is not None:
        labels = (context['index'] - pd.Timedelta(nanoseconds=1)).floor('D')
        daily_exposure = context['exposures'].mul(context['hours'], axis=0).groupby(labels).sum() / 24
        for name in daily_exposure:
            rolling['mean_' + name] = daily_exposure[name].reindex(daily.index).rolling(90, min_periods=90).mean()
        rolling['total_turnover'] = daily.turnover.rolling(90, min_periods=90).sum()
        rolling['mean_daily_turnover'] = daily.turnover.rolling(90, min_periods=90).mean()
        rolling['annualized_turnover'] = rolling.mean_daily_turnover * YEAR_DAYS
    native = _clean({'summary': summary, 'bootstrap': bootstrap, 'break_even': fee,
                     'drawdown': generic['drawdown'], 'exposures': context['exposure_summary'],
                     'exposure_metadata': context['exposure_metadata'], 'definitions': {
                         **generic['definitions'],
                         'ulcer_index': 'sqrt(elapsed-hours-weighted mean observed endpoint drawdown depth squared), fraction units',
                         'exposure': context['exposure_metadata']['exposure_time_basis'],
                         'exposure_extrema': 'instantaneous supplied pre/post-event states, not extrema of time-averaged weights',
                         'cash': 'only explicit long/cash allocation; inactive slots and unallocated spread budgets are NOT cash',
                         'fixed_slot_budget': 'actual asset-column count; factor budget excludes BTCUSDT once',
                         'search_adjustment': 'none: selected realized-path bootstrap is conditional and descriptive, not DSR or fresh OOS',
                     }})
    native['rolling'] = rolling
    return native
