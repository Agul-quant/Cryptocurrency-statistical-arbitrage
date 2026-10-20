"""Cash-benchmark comparisons on fixed, already saved daily strategy returns.

This module does not simulate trades, credit interest to a strategy, acquire
prices, change selections, or replace original acceptance tests. All rates and
returns are fractions, not percentages. Drawdowns are positive loss magnitudes.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd
from scipy.stats import norm
from statsmodels.stats.multitest import multipletests

ORDER = ('A01', 'A02', 'A03', 'A04', 'B01', 'B03', 'B04', 'B05', 'B06')
PERIODS = {
    'development': ('2022-01-01', 730),
    'validation': ('2024-01-01', 731),
    'oos_partial_2026_jan_sep': ('2026-01-01', 273),
}
ANNUAL_DAYS = 365
SEED = 20261016
BLOCK_DAYS = 28
REPLICATIONS = 4000
Z95 = float(norm.ppf(.975))
INPUT_NAMES = {
    'results/daily_returns.csv', 'results/strategy_metrics.csv',
    'data/diagnostics/daily_model_inputs.parquet',
    'results/basket_factors/joint_coefficients.csv',
    'results/basket_factors/matched_btc_coefficients.csv',
    'results/basket_factors/btc_only_comparison.csv', 'configs/frozen_strategies.json',
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_returns(values):
    r = np.asarray(values, dtype=float)
    if r.ndim != 1 or len(r) < 2 or not np.isfinite(r).all() or (r <= -1).any():
        raise ValueError('Returns must be a finite 1D series, n>=2, each > -1')
    return r


def validate_calendar(days, *, start=None, n=None):
    idx = pd.DatetimeIndex(pd.to_datetime(days, utc=True))
    expected_n = len(idx) if n is None else n
    first = idx[0] if start is None else pd.Timestamp(start, tz='UTC')
    expected = pd.date_range(first, periods=expected_n, freq='D')
    if len(idx) != expected_n or not idx.equals(expected) or not idx.equals(idx.floor('D')):
        raise ValueError('Daily observations must match the complete ordered UTC calendar')
    return idx


def cash_daily_rate(annual_nominal=.03):
    if not np.isfinite(annual_nominal) or annual_nominal < 0:
        raise ValueError('Annual nominal cash rate must be finite and nonnegative')
    return float(annual_nominal / ANNUAL_DAYS)


def drawdown_from_daily_returns(returns, days):
    """Daily close drawdown with initial NAV=1 at the first UTC day start.

    A return labelled January 1 ends at January 2 00:00 UTC. Duration runs
    from the preceding high-water endpoint through recovery or sample end.
    Time underwater is the fraction of daily endpoints strictly below peak;
    it is not an intraday/continuously observed duration estimate.
    """
    r = validate_returns(returns)
    idx = validate_calendar(days)
    if len(idx) != len(r):
        raise ValueError('Return and calendar lengths differ')
    times = pd.DatetimeIndex([idx[0], *list(idx + pd.Timedelta(days=1))])
    log_nav = np.r_[0., np.cumsum(np.log1p(r))]
    high = np.maximum.accumulate(log_nav)
    depth = -np.expm1(log_nav - high)
    underwater = log_nav < high - 1e-14
    trough = int(np.argmax(depth))
    peak = int(np.flatnonzero(log_nav[:trough+1] >= high[trough] - 1e-14)[-1])
    recovered = np.flatnonzero(log_nav[trough+1:] >= high[trough] - 1e-14)
    recovery = trough + 1 + int(recovered[0]) if len(recovered) else None
    # An all-flat/upward path has no underwater episode to censor.
    if float(depth[trough]) <= 1e-14:
        return {
            'max_drawdown': 0., 'dd_peak_utc': None, 'dd_trough_utc': None,
            'dd_recovery_utc': None, 'dd_peak_to_trough_days': 0,
            'dd_underwater_days': 0, 'dd_recovery_censored': False,
            'longest_underwater_days': 0, 'longest_underwater_start_utc': None,
            'longest_underwater_end_utc': None, 'longest_underwater_censored': False,
            'time_underwater_fraction': 0.,
        }
    episodes = []
    peak_at, episode_peak = 0, None
    for k in range(1, len(log_nav)):
        if not underwater[k]:
            if episode_peak is not None:
                episodes.append((k-episode_peak, episode_peak, k, False))
                episode_peak = None
            peak_at = k
        elif episode_peak is None:
            episode_peak = peak_at
    if episode_peak is not None:
        episodes.append((len(log_nav)-1-episode_peak, episode_peak, len(log_nav)-1, True))
    longest = max(episodes, key=lambda v: (v[0], -v[1]))
    end = recovery if recovery is not None else len(log_nav)-1
    return {
        'max_drawdown': float(depth[trough]),
        'dd_peak_utc': times[peak].isoformat(), 'dd_trough_utc': times[trough].isoformat(),
        'dd_recovery_utc': None if recovery is None else times[recovery].isoformat(),
        'dd_peak_to_trough_days': trough-peak, 'dd_underwater_days': end-peak,
        'dd_recovery_censored': recovery is None,
        'longest_underwater_days': int(longest[0]),
        'longest_underwater_start_utc': times[longest[1]].isoformat(),
        'longest_underwater_end_utc': times[longest[2]].isoformat(),
        'longest_underwater_censored': bool(longest[3]),
        'time_underwater_fraction': float(underwater[1:].mean()),
    }


def performance(returns, days, annual_nominal=.03):
    r = validate_returns(returns)
    days = validate_calendar(days)
    if len(r) != len(days):
        raise ValueError('Return and calendar lengths differ')
    c = cash_daily_rate(annual_nominal)
    excess = r-c
    relative = excess/(1+c)
    n = len(r)
    raw_log = float(np.log1p(r).sum())
    cash_log = n*math.log1p(c)
    sd = float(np.std(r, ddof=1))
    defined = np.ptp(r) > 0 and sd > 1e-15
    raw_sharpe = math.sqrt(365)*float(r.mean())/sd if defined else np.nan
    excess_sharpe = math.sqrt(365)*float(excess.mean())/sd if defined else np.nan
    output = {
        'n_calendar_days': n, 'first_utc_day': days[0].date().isoformat(),
        'last_utc_day': days[-1].date().isoformat(),
        'cash_nominal_annual': annual_nominal, 'cash_daily_return': c,
        'cash_effective_365_day_return': math.expm1(365*math.log1p(c)),
        'raw_net_return': math.expm1(raw_log), 'cash_compounded_return': math.expm1(cash_log),
        'wealth_relative_excess_return': math.expm1(raw_log-cash_log),
        'difference_of_compounded_returns': math.expm1(raw_log)-math.expm1(cash_log),
        'raw_cagr': math.expm1(raw_log*365/n),
        'relative_annualized_growth': math.expm1((raw_log-cash_log)*365/n),
        'raw_annual_arithmetic_return': 365*float(r.mean()),
        'annual_arithmetic_mean_excess': 365*float(excess.mean()),
        'raw_annual_daily_volatility': sd*math.sqrt(365),
        'arithmetic_excess_annual_volatility': sd*math.sqrt(365),
        'relative_return_annual_volatility': float(np.std(relative, ddof=1))*math.sqrt(365),
        'raw_sharpe': raw_sharpe, 'cash_excess_sharpe': excess_sharpe,
        'cash_interest_credited_to_strategy': False,
        'relative_drawdown_basis': 'daily_endpoints_including_initial_NAV_1_not_intraday',
    }
    for prefix, values in [('raw_daily_', r), ('relative_daily_', relative)]:
        output.update({prefix+k: v for k,v in drawdown_from_daily_returns(values, days).items()})
    return output


def circular_indices(n, *, seed=SEED, replications=REPLICATIONS, block_days=BLOCK_DAYS):
    if n < 2 or replications < 1 or block_days < 1:
        raise ValueError('Invalid bootstrap dimensions')
    rng = np.random.Generator(np.random.PCG64(seed))
    out = np.empty((replications, n), dtype=np.int64)
    offsets = np.arange(block_days)
    for k in range(replications):
        starts = rng.integers(0, n, math.ceil(n/block_days))
        out[k] = ((starts[:, None]+offsets[None, :]) % n).ravel()[:n]
    return out


def bootstrap_intervals(returns, indices, annual_nominal=.03):
    r = validate_returns(returns)
    ind = np.asarray(indices)
    if ind.ndim != 2 or ind.shape[1] != len(r) or ind.dtype.kind not in 'iu' or (ind < 0).any() or (ind >= len(r)).any():
        raise ValueError('Bootstrap indices must be an integer array of full-length samples')
    c = cash_daily_rate(annual_nominal)
    sampled = r[ind]
    n = len(r)
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        relative_log = np.log1p(sampled).sum(axis=1)-n*math.log1p(c)
        draws = {
            'wealth_relative_excess_return': np.expm1(relative_log),
            'relative_annualized_growth': np.expm1(relative_log*365/n),
            'cash_excess_sharpe': math.sqrt(365)*(sampled.mean(axis=1)-c)/sampled.std(axis=1, ddof=1),
        }
    # Constant paths do not have a defined Sharpe, even when floating point
    # summation happens to produce an extremely small positive standard deviation.
    draws['cash_excess_sharpe'][(np.ptp(sampled, axis=1) == 0) | (sampled.std(axis=1, ddof=1) <= 1e-15)] = np.nan
    result = {'bootstrap_replications': len(ind), 'bootstrap_block_days': BLOCK_DAYS,
              'bootstrap_seed': SEED, 'bootstrap_intervals_selection_adjusted': False}
    invalid_all = np.zeros(len(ind), dtype=bool)
    for name, values in draws.items():
        bad = ~np.isfinite(values)
        invalid_all |= bad
        result[name+'_bootstrap_invalid_draws'] = int(bad.sum())
        # Never drop invalid draws or silently condition on survivors.
        lo, hi = np.quantile(values, [.025, .975], method='linear') if not bad.any() else (np.nan, np.nan)
        result[name+'_bootstrap_ci95_low'] = float(lo)
        result[name+'_bootstrap_ci95_high'] = float(hi)
    result['bootstrap_any_invalid_draws'] = int(invalid_all.sum())
    return result


def calendar_hac_covariance(design, residual, mask, lag=27, finite_correction=True):
    design = np.asarray(design, dtype=float)
    residual = np.asarray(residual, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    n, p = design.shape
    if n <= p or mask.sum() != n or residual.shape != (n,) or lag < 0:
        raise ValueError('Invalid covariance dimensions or insufficient observations')
    score = np.zeros((len(mask), p))
    score[mask] = design*residual[:, None]
    meat = score.T@score
    for h in range(1, min(lag+1, len(mask))):
        cross = score[h:].T@score[:-h]
        meat += (1-h/(lag+1))*(cross+cross.T)
    bread = np.linalg.inv(design.T@design)
    covariance = bread@meat@bread
    if finite_correction:
        covariance *= n/(n-p)
    return (covariance+covariance.T)/2


def fit_factor_model(returns, factors, *, mask=None, lag=27, finite_correction=True):
    # Arithmetic excess returns can fall below -1; they are not a compounded
    # wealth-return series and must not inherit its bankruptcy bound.
    y = np.asarray(returns, dtype=float)
    if y.ndim != 1 or len(y) < 2 or not np.isfinite(y).all():
        raise ValueError('Regression response must be a finite 1D series')
    x = np.asarray(factors, dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or len(x) != len(y):
        raise ValueError('Factors and strategy must share the same full calendar')
    complete = np.isfinite(x).all(axis=1)
    if mask is None:
        mask = complete
    else:
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != (len(y),) or (mask & ~complete).any():
            raise ValueError('Cannot retain an unknown factor observation')
    design = np.column_stack([np.ones(mask.sum()), x[mask]])
    if design.shape[0] <= design.shape[1] or np.linalg.matrix_rank(design) < design.shape[1]:
        raise ValueError('Insufficient observations or rank-deficient factors')
    params = np.linalg.lstsq(design, y[mask], rcond=None)[0]
    residual = y[mask]-design@params
    covariance = calendar_hac_covariance(design, residual, mask, lag, finite_correction)
    return {'params': params, 'covariance': covariance, 'residual': residual,
            'mask': mask, 'n_fit_days': int(mask.sum()), 'n_calendar_days': len(y)}


def transformed_cash_parameters(params, covariance, annual_nominal=.03):
    p = np.asarray(params, dtype=float)
    cov = np.asarray(covariance, dtype=float)
    if p.ndim != 1 or cov.shape != (len(p), len(p)):
        raise ValueError('Parameter/covariance dimensions do not match')
    c = cash_daily_rate(annual_nominal)
    transform = np.eye(len(p))
    transform[0, 1:] = c
    transformed = transform@p
    transformed[0] -= c
    return transformed, transform@cov@transform.T


def mean_excess_inference(returns, annual_nominal=.03):
    x = validate_returns(returns)-cash_daily_rate(annual_nominal)
    mean = float(x.mean())
    residual = x-mean
    if np.ptp(x) <= 1e-15:
        variance = 0.
    else:
        variance = float(calendar_hac_covariance(np.ones((len(x), 1)), residual, np.ones(len(x), bool), 27, True)[0, 0])
    se = math.sqrt(max(variance, 0.))
    tstat = mean/se if se > 1e-15 else np.nan
    pvalue = float(2*norm.sf(abs(tstat))) if np.isfinite(tstat) else np.nan
    return {
        'daily_mean_excess': mean, 'daily_mean_excess_hac27_se': se,
        'annual_mean_excess': 365*mean, 'annual_mean_excess_hac27_se': 365*se,
        'hac27_tstat_asymptotic_normal': tstat, 'hac27_two_sided_p': pvalue,
        'annual_mean_excess_ci95_low': 365*(mean-Z95*se),
        'annual_mean_excess_ci95_high': 365*(mean+Z95*se),
        'covariance': 'calendar_HAC27_Bartlett_n_over_n_minus_1',
        'inference_scope': 'conditional_not_configuration_or_universe_search_adjusted',
        'original_acceptance_retested': False,
    }


def coefficient_rows(raw, cash, symbols, model_type, sid, period, lag, finite_correction):
    scale = np.r_[365., np.ones(len(symbols))]
    rows = []
    for j, term in enumerate(('alpha_annual', *symbols)):
        se = math.sqrt(max(float(cash['covariance'][j, j]), 0.))*scale[j]
        raw_se = math.sqrt(max(float(raw['covariance'][j, j]), 0.))*scale[j]
        estimate = float(cash['params'][j]*scale[j])
        raw_estimate = float(raw['params'][j]*scale[j])
        z = estimate/se if se > 1e-15 else np.nan
        rows.append({
            'strategy_id': sid, 'period': period, 'model_type': model_type, 'term': term,
            'raw_estimate': raw_estimate, 'cash_excess_estimate': estimate,
            'raw_se': raw_se, 'cash_excess_se': se,
            'raw_ci95_low': raw_estimate-Z95*raw_se,
            'raw_ci95_high': raw_estimate+Z95*raw_se,
            'cash_excess_ci95_low': estimate-Z95*se,
            'cash_excess_ci95_high': estimate+Z95*se,
            'cash_excess_tstat_asymptotic_normal': z,
            'cash_excess_two_sided_p': float(2*norm.sf(abs(z))) if np.isfinite(z) else np.nan,
            'n_fit_days': cash['n_fit_days'], 'n_calendar_days': cash['n_calendar_days'],
            'hac_lag': lag, 'finite_sample_correction': finite_correction,
            'ci_scope': 'marginal_conditional_not_search_adjusted',
        })
    return rows


def verify_inputs(root, config):
    root = Path(root).resolve()
    manifest = json.loads((root/'metadata/project_manifest.json').read_text())
    pins = config['input_pins']
    if set(pins) != INPUT_NAMES:
        raise ValueError('Exactly seven declared original inputs must be pinned')
    for name, record in pins.items():
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Input pins must be safe project-relative paths')
        path = root/rel
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing input or symlink: '+name)
        actual = sha256(path)
        if actual != record['sha256'] or path.stat().st_size != record['bytes']:
            raise ValueError('Cash analysis input checksum mismatch: '+name)
        if name not in manifest['files'] or manifest['files'][name]['sha256'] != actual:
            raise ValueError('Input not pinned by current project manifest: '+name)
    return {name: record['sha256'] for name, record in pins.items()}


def _assert_close(actual, expected, label, audit, atol=3e-10, rtol=3e-8):
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    np.testing.assert_allclose(a, b, atol=atol, rtol=rtol, equal_nan=True, err_msg=label)
    finite = np.isfinite(a) & np.isfinite(b)
    error = float(np.max(np.abs(a[finite]-b[finite]))) if finite.any() else 0.
    audit[label] = {'numeric_cells': int(a.size), 'maximum_absolute_error': error}


def calculate(root, config):
    """Read pinned daily inputs; return new tables without writing any files."""
    root = Path(root).resolve()
    if config['annual_nominal_rate'] != .03 or config['day_count'] != 'ACT/365F' or config['interest_credited_to_strategy']:
        raise ValueError('This fixed cash comparison requires nominal3percent ACT365F benchmark only')
    if (config['calendar_days_per_fixed_year'] != 365 or not config['daily_compounding'] or
        config['bootstrap'] != {'seed': SEED, 'replications': REPLICATIONS,
                                'block_days': BLOCK_DAYS, 'synchronized_nine': True,
                                'generator_reset_each_period': True}):
        raise ValueError('Cash-compounding or bootstrap protocol changed')
    input_hashes = verify_inputs(root, config)
    daily = pd.read_csv(root/'results/daily_returns.csv')
    saved_metrics = pd.read_csv(root/'results/strategy_metrics.csv')
    model_inputs = pd.read_parquet(root/'data/diagnostics/daily_model_inputs.parquet')
    raw_joint = pd.read_csv(root/'results/basket_factors/joint_coefficients.csv')
    raw_matched = pd.read_csv(root/'results/basket_factors/matched_btc_coefficients.csv')
    raw_btc = pd.read_csv(root/'results/basket_factors/btc_only_comparison.csv')
    registry = json.loads((root/'configs/frozen_strategies.json').read_text())
    symbols = {s['comparison_id']: s['symbols'] for s in registry['strategies']}
    if tuple(registry['order']) != ORDER or set(symbols) != set(ORDER):
        raise ValueError('Frozen strategy registry changed')
    for frame, id_col, day_col in [(daily, 'comparison_id', 'date'), (model_inputs, 'strategy_id', 'utc_day')]:
        if frame.duplicated([id_col, 'period', day_col]).any():
            raise ValueError('Duplicate daily observation')
        frame[day_col] = pd.to_datetime(frame[day_col], utc=True)
    if len(daily) != sum(v[1] for v in PERIODS.values())*len(ORDER) or len(model_inputs) != len(daily):
        raise ValueError('Daily input coverage changed')
    performances, means, joint, matched, full, models, checks, bootstrap = [], [], [], [], [], [], {}, []
    c = cash_daily_rate(.03)
    for period, (first, n) in PERIODS.items():
        indices = circular_indices(n)
        bootstrap.append({'period': period, 'calendar_days': n,
                          'indices_sha256_int64_little_endian': hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest(),
                          'replications': REPLICATIONS, 'block_days': BLOCK_DAYS, 'seed': SEED,
                          'synchronized_nine': True, 'rng_reset_at_each_period': True})
        for sid in ORDER:
            d = daily.loc[daily.comparison_id.eq(sid) & daily.period.eq(period)].sort_values('date')
            m = model_inputs.loc[model_inputs.strategy_id.eq(sid) & model_inputs.period.eq(period)].sort_values('utc_day')
            dates = validate_calendar(d.date, start=first, n=n)
            if not dates.equals(validate_calendar(m.utc_day, start=first, n=n)):
                raise ValueError('Daily return and factor calendars differ')
            y = validate_returns(d.net_return.to_numpy())
            _assert_close(y, m.strategy_net_return, sid+'_'+period+'_daily_input_reconciliation', checks, atol=2e-15, rtol=1e-13)
            metric = saved_metrics.loc[saved_metrics.comparison_id.eq(sid) & saved_metrics.period.eq(period)]
            if len(metric) != 1 or metric.iloc[0].cost_bps != 20 or metric.iloc[0].execution_lag_h != 1:
                raise ValueError('Expected exactly one frozen primary metric row')
            metric = metric.iloc[0]
            perf = dict(strategy_id=sid, period=period, **performance(y, dates))
            perf.update(bootstrap_intervals(y, indices))
            for key in ('total_turnover', 'mean_hourly_turnover', 'mean_daily_turnover',
                        'annualized_turnover', 'annualized_full_l1_turnover', 'max_drawdown'):
                perf['original_path_'+key] = float(metric[key])
            _assert_close([perf['raw_net_return'], perf['raw_cagr'], perf['raw_sharpe'], perf['raw_annual_daily_volatility']],
                          metric[['total_return', 'cagr', 'sharpe', 'annual_volatility']], sid+'_'+period+'_original_metric_reconciliation', checks)
            _assert_close(perf['cash_excess_sharpe'], perf['raw_sharpe']-.03/perf['raw_annual_daily_volatility'], sid+'_'+period+'_Sharpe_identity', checks, atol=2e-13, rtol=1e-12)
            _assert_close(np.expm1(np.log1p((y-c)/(1+c)).sum()), perf['wealth_relative_excess_return'], sid+'_'+period+'_relative_compounding_identity', checks, atol=3e-13, rtol=1e-12)
            performances.append(perf)
            means.append(dict(strategy_id=sid, period=period, **mean_excess_inference(y)))
            x = m[symbols[sid]].to_numpy()
            common = np.isfinite(x).all(axis=1)
            for kind, xx, mask, lag, finite, destination in [
                ('joint_eight_coin', x, common, 27, True, joint),
                ('matched_btc', x[:, [symbols[sid].index('BTCUSDT')]], common, 27, True, matched),
                ('btc_only_full_period', x[:, [symbols[sid].index('BTCUSDT')]], np.ones(n, bool), 7, False, full),
            ]:
                names = symbols[sid] if kind == 'joint_eight_coin' else ['BTCUSDT']
                raw_fit = fit_factor_model(y, xx, mask=mask, lag=lag, finite_correction=finite)
                cash_fit = fit_factor_model(y-c, xx-c, mask=mask, lag=lag, finite_correction=finite)
                params_expected, covariance_expected = transformed_cash_parameters(raw_fit['params'], raw_fit['covariance'])
                label = sid+'_'+period+'_'+kind
                _assert_close(cash_fit['params'], params_expected, label+'_parameter_transformation', checks, atol=3e-12, rtol=3e-9)
                _assert_close(cash_fit['covariance'], covariance_expected, label+'_full_covariance_transformation', checks, atol=2e-13, rtol=2e-8)
                _assert_close(cash_fit['residual'], raw_fit['residual'], label+'_residual_invariance', checks, atol=3e-12, rtol=1e-8)
                rows = coefficient_rows(raw_fit, cash_fit, names, kind, sid, period, lag, finite)
                if kind != 'btc_only_full_period':
                    raw7 = fit_factor_model(y, xx, mask=mask, lag=7, finite_correction=True)
                    cash7 = fit_factor_model(y-c, xx-c, mask=mask, lag=7, finite_correction=True)
                    p7, cov7 = transformed_cash_parameters(raw7['params'], raw7['covariance'])
                    _assert_close(cash7['params'], p7, label+'_HAC7_parameter_transformation', checks, atol=3e-12, rtol=3e-9)
                    _assert_close(cash7['covariance'], cov7, label+'_HAC7_full_covariance_transformation', checks, atol=2e-13, rtol=2e-8)
                    for row7, row in zip(coefficient_rows(raw7, cash7, names, kind, sid, period, 7, True), rows):
                        for key in ('raw_se', 'cash_excess_se', 'raw_ci95_low', 'raw_ci95_high', 'cash_excess_ci95_low', 'cash_excess_ci95_high'):
                            row['hac7_'+key] = row7[key]
                    reference = raw_joint if kind == 'joint_eight_coin' else raw_matched
                    ref = reference.loc[reference.strategy_id.eq(sid) & reference.period.eq(period)].set_index('term').loc[['alpha_annual', *names]]
                    _assert_close([row['raw_estimate'] for row in rows], ref.estimate, label+'_saved_raw_estimates', checks)
                    for key, saved_key in [('raw_se', 'hac27_se'), ('raw_ci95_low', 'ci95_low'), ('raw_ci95_high', 'ci95_high'),
                                           ('hac7_raw_se', 'hac7_se'), ('hac7_raw_ci95_low', 'hac7_ci95_low'), ('hac7_raw_ci95_high', 'hac7_ci95_high')]:
                        _assert_close([row[key] for row in rows], ref[saved_key], label+'_saved_'+key, checks)
                else:
                    ref = raw_btc.loc[raw_btc.strategy_id.eq(sid) & raw_btc.period.eq(period)].iloc[0]
                    _assert_close([rows[0]['raw_estimate'], rows[1]['raw_estimate'], rows[0]['raw_ci95_low'], rows[0]['raw_ci95_high'], rows[1]['raw_ci95_low'], rows[1]['raw_ci95_high']],
                                  [ref.alpha_annual, ref.beta, ref.alpha_ci95_low, ref.alpha_ci95_high, ref.beta_ci95_low, ref.beta_ci95_high], label+'_saved_full_btc', checks)
                for row in rows[1:]:
                    _assert_close([row['cash_excess_estimate'], row['cash_excess_se'], row['cash_excess_ci95_low'], row['cash_excess_ci95_high']],
                                  [row['raw_estimate'], row['raw_se'], row['raw_ci95_low'], row['raw_ci95_high']], label+'_'+row['term']+'_beta_invariance', checks, atol=3e-11, rtol=3e-9)
                destination.extend(rows)
                models.append({'strategy_id': sid, 'period': period, 'model_type': kind,
                               'n_calendar_days': n, 'n_fit_days': int(mask.sum()), 'n_excluded_days': int((~mask).sum()),
                               'symbols': ','.join(names), 'hac_lag': lag, 'finite_sample_correction': finite,
                               'cash_daily_subtracted_from_y_and_each_factor': c,
                               'alpha_cash_identity_annual': float(365*params_expected[0]),
                               'residuals_unchanged': True, 'all_beta_confidence_intervals_unchanged': True})
    performance_frame = pd.DataFrame(performances)
    mean_frame = pd.DataFrame(means)
    mean_frame['cash_excess_global_holm27_p'] = multipletests(mean_frame.hac27_two_sided_p, method='holm')[1]
    mean_frame['cash_excess_mean_multiplicity_family_size'] = 27
    joint_frame = pd.DataFrame(joint)
    joint_frame['cash_excess_global_holm243_p'] = multipletests(joint_frame.cash_excess_two_sided_p, method='holm')[1]
    joint_frame['cash_excess_coefficient_multiplicity_family_size'] = 243
    critical = float(norm.isf(.05/(2*243)))
    joint_frame['cash_excess_bonferroni243_ci95_low'] = joint_frame.cash_excess_estimate-critical*joint_frame.cash_excess_se
    joint_frame['cash_excess_bonferroni243_ci95_high'] = joint_frame.cash_excess_estimate+critical*joint_frame.cash_excess_se
    matched_frame, full_frame = pd.DataFrame(matched), pd.DataFrame(full)
    summary = performance_frame.merge(mean_frame, on=['strategy_id', 'period'], validate='one_to_one')
    for name, frame in [('joint', joint_frame), ('btc_matched', matched_frame), ('btc_full', full_frame)]:
        alpha = frame.loc[frame.term.eq('alpha_annual')].copy()
        columns = ['raw_estimate', 'cash_excess_estimate', 'raw_ci95_low', 'raw_ci95_high', 'cash_excess_ci95_low', 'cash_excess_ci95_high']
        alpha = alpha[['strategy_id', 'period', *columns]].rename(columns={v: name+'_alpha_annual_'+v for v in columns})
        summary = summary.merge(alpha, on=['strategy_id', 'period'], validate='one_to_one')
    methods = {
        'analysis': 'fixed_strategy_hypothetical_cash_benchmark_comparison',
        'numeric_units': 'all_returns_rates_and_drawdowns_are_fractions_not_percentages',
        'annual_nominal_rate': .03, 'daily_cash_return': c, 'day_count': 'ACT/365F',
        'calendar_day_compounding': True, 'interest_credited_to_strategy': False,
        'cash_benchmark_currency': 'USDT_quoted_units',
        'USD_interpretation_requires_USDT_USD_parity': True,
        'currency_caveat': 'hypothetical3percent_cash_benchmark_in_USDT_quoted_units_not_an_actual_product_yield_no_FX_conversion_USD_interpretation_requires_USDT_USD_parity',
        'strategy_trades_costs_selections_risk_limits_and_original_acceptance_tests_unchanged': True,
        'relative_return': '(1+strategy_return)/(1+cash_return)-1',
        'arithmetic_excess_for_Sharpe_and_mean_test': 'strategy_return-cash_return',
        'sharpe': 'sqrt365_times_daily_arithmetic_excess_mean_over_sample_standard_deviation_ddof1',
        'factor_model': '(strategy_return-c)=alpha+sum_beta_times(coin_return-c)+residual',
        'factor_missingness': 'same_original_complete_case_calendar_no_zero_fill_no_shortened_performance_period',
        'joint_and_matched_covariance': 'calendar_Bartlett_HAC27_n_over_n_minus_k_HAC7_sensitivity',
        'btc_full_covariance': 'calendar_Bartlett_HAC7_no_finite_sample_correction',
        'alpha_annualization': '365_times_arithmetic_daily_intercept_not_CAGR',
        'mean_test_covariance': 'calendar_Bartlett_HAC27_n_over_n_minus_1_asymptotic_normal_two_sided',
        'new_mean_family': 'cash_excess_27_strategy_period_means_Holm27_separate_from_original_acceptance',
        'new_joint_factor_family': 'cash_excess_243_joint_coefficients_Holm243_and_Bonferroni243_separate_from_raw_family',
        'btc_comparison_CIs': 'marginal_not_simultaneous_not_new_profitability_tests',
        'bootstrap': bootstrap, 'bootstrap_interval': 'marginal95_percentile_numpy_quantile_linear',
        'bootstrap_invalid_policy': 'per_statistic_any_invalid_draw_makes_that_CI_unavailable_no_draw_dropping',
        'bootstrap_signals_rerun': False, 'bootstrap_extra_block_boundary_trades': False,
        'bootstrap_cash_accrual': 'deterministic_n_calendar_days_not_resampled_rate',
        'inference_caveat': 'conditional_not_basket_or_configuration_search_adjusted_no_new_winner_or_independent_new_test',
        'relative_drawdown_basis': 'daily_endpoint_NAV_including_initial_NAV1_at_first_day_start_no_intraday_claim',
        'cash_model_caveat': 'benchmark_only_no_interest_on_strategy_cash_or_short_collateral_no_new_borrow_funding_or_margin_model',
    }
    tables = {'performance.csv': performance_frame, 'mean_excess_inference.csv': mean_frame,
              'joint_coefficients.csv': joint_frame, 'matched_btc_coefficients.csv': matched_frame,
              'btc_full_period_coefficients.csv': full_frame, 'factor_models.csv': pd.DataFrame(models),
              'strategy_summary.csv': summary}
    assert [len(tables[v]) for v in tables] == [27, 27, 243, 54, 54, 81, 27]
    reconciliation = {'status': 'passed', 'input_sha256': input_hashes, 'checks': checks,
                      'total_numeric_cells_checked': sum(v['numeric_cells'] for v in checks.values()),
                      'max_absolute_numeric_error': max(v['maximum_absolute_error'] for v in checks.values()),
                      'source_writes': False, 'hourly_prices_loaded': False,
                      'new_backtests_or_selections': False,
                      'bootstrap_any_invalid_draws': int(performance_frame.bootstrap_any_invalid_draws.sum()),
                      'table_rows': {k: len(v) for k,v in tables.items()}}
    return tables, {'methods.json': methods, 'reconciliation.json': reconciliation}


def compare_tables(actual, expected, label):
    if list(actual.columns) != list(expected.columns) or actual.shape != expected.shape:
        raise AssertionError(label+': table shape or columns changed')
    for col in actual:
        a, b = actual[col], expected[col]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            np.testing.assert_allclose(a.astype(float), b.astype(float), rtol=3e-8, atol=3e-10, equal_nan=True, err_msg=label+'/'+col)
        else:
            if not a.fillna('<NA>').astype(str).equals(b.fillna('<NA>').astype(str)):
                raise AssertionError(label+': values differ in '+col)


def write_result_files(tables, blobs, output):
    """Caller must first validate an output directory under local_outputs."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(output/name, index=False, float_format='%.17g')
    for name, obj in blobs.items():
        (output/name).write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False)+'\n')
