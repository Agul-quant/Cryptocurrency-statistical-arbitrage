"""Pure, post-hoc fixed-basket attribution; no source loading or strategy changes.

The regression estimand is conditional on days with all eight observed factors.
Excluded lifecycle days remain present in the calendar used for HAC distances.
Zero score vectors on those days are missing-observation accounting, NOT filled
coin returns. Alpha is an arithmetic daily intercept times 365, not CAGR.

All intervals are approximate, conditional on already selected strategies and
historical data. Neither HAC nor the coefficient-family correction adjusts the
prior universe/configuration search. Attribution bootstrap resamples realized
daily component vectors, never prices, signals or trades.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd
from scipy.stats import norm

STRATEGY_ORDER = ('A01', 'A02', 'A03', 'A04', 'B01', 'B03', 'B04', 'B05', 'B06')
PERIOD_ORDER = ('development', 'validation', 'oos_partial_2026_jan_sep')
YEAR_DAYS = 365.0
HAC_LAG = 27
SVD_RELATIVE_TOLERANCE = 1e-12
JOINT_FAMILY_SIZE = 243
Z95 = float(norm.ppf(.975))


def _finite(value):
    value = float(value)
    return value if math.isfinite(value) else None


def _calendar(index):
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError('A timezone-aware contiguous UTC daily index is required.')
    utc = index.tz_convert('UTC')
    if len(utc) < 2 or utc.has_duplicates or utc.hasnans or not utc.equals(utc.normalize()):
        raise ValueError('Daily index must contain unique UTC-midnight dates.')
    wanted = pd.date_range(utc[0], utc[-1], freq='D', name=utc.name)
    if not utc.equals(wanted):
        raise ValueError('Keep excluded factor dates on the full contiguous calendar.')
    return utc


def _ranges(index, mask):
    dates = index[np.asarray(mask, dtype=bool)]
    if not len(dates):
        return []
    starts = [0] + (np.flatnonzero(np.diff(dates.asi8) != pd.Timedelta(days=1).value) + 1).tolist()
    stops = starts[1:] + [len(dates)]
    return [{'start': dates[a].date().isoformat(), 'end_inclusive': dates[b - 1].date().isoformat(),
             'n_days': b - a} for a, b in zip(starts, stops)]


def calendar_hac_covariance(design, residuals, observed_mask, *, max_lag=HAC_LAG):
    """OLS sandwich on a full calendar, Bartlett lags measured in actual days.

    ``design`` contains only fitted rows, in their calendar order, in a well
    conditioned coordinate system. Small-sample covariance factor is n/(n-k).
    The same factor is used for HAC27 primary and HAC7 descriptive sensitivity.
    """
    x = np.asarray(design, dtype=float)
    u = np.asarray(residuals, dtype=float)
    mask = np.asarray(observed_mask, dtype=bool)
    n, k = x.shape
    if x.ndim != 2 or u.shape != (n,) or mask.ndim != 1 or mask.sum() != n or n <= k:
        raise ValueError('HAC design, residual and calendar mask dimensions disagree.')
    if max_lag < 0 or not np.isfinite(x).all() or not np.isfinite(u).all():
        raise ValueError('HAC requires finite fitted observations and nonnegative lag.')
    _, singular, vh = np.linalg.svd(x, full_matrices=False)
    if len(singular) != k or singular[-1] <= SVD_RELATIVE_TOLERANCE * singular[0]:
        raise ValueError('HAC cannot identify rank-deficient coefficients.')
    bread = (vh.T / singular**2) @ vh
    score = np.zeros((len(mask), k), dtype=float)
    score[mask] = x * u[:, None]
    meat = score.T @ score
    for lag in range(1, min(int(max_lag), len(mask) - 1) + 1):
        cross = score[lag:].T @ score[:-lag]
        meat += (1 - lag / (max_lag + 1)) * (cross + cross.T)
    covariance = (n / (n - k)) * (bread @ meat @ bread)
    return (covariance + covariance.T) / 2


def _fit(y, factors, mask, names, *, strategy_id, period, model_type):
    """Stable standardized OLS with coefficients transformed to raw units."""
    ncal = len(y)
    n = int(mask.sum())
    k = len(names) + 1
    raw = factors[mask]
    yf = y[mask]
    means = raw.mean(axis=0) if n else np.full(len(names), np.nan)
    scales = raw.std(axis=0, ddof=0) if n else np.full(len(names), np.nan)
    base = {'strategy_id': strategy_id, 'period': period, 'model_type': model_type,
            'n_calendar_days': ncal, 'n_fit_days': n, 'n_excluded_days': ncal - n,
            'n_parameters': k, 'hac_max_lag_days': HAC_LAG, 'hac_small_sample_multiplier': n / (n - k) if n > k else None,
            'alpha_annualization': '365_times_daily_arithmetic_intercept_not_CAGR',
            'sample_scope': 'joint_factor_observed_days_only',
            'selection_adjusted': False, 'causal': False}
    unavailable = [{'strategy_id': strategy_id, 'period': period, 'model_type': model_type,
                    'term': term, 'coefficient_kind': 'annualized_intercept_alpha' if j == 0 else 'conditional_coin_beta',
                    'estimate': None, 'hac27_se': None, 'hac27_z': None, 'hac27_two_sided_p': None,
                    'ci95_low': None, 'ci95_high': None, 'hac7_se': None, 'hac7_ci95_low': None,
                    'hac7_ci95_high': None, 'ci_scope': 'unavailable', 'n_fit_days': n,
                    'n_calendar_days': ncal}
                   for j, term in enumerate(('alpha_annual', *names))]
    coefficients = []
    if n <= k or not np.isfinite(scales).all() or (scales <= 1e-15).any():
        return {**base, 'status': 'unavailable_insufficient_rows_or_constant_factor', 'rank': None,
                'standardized_condition_number': None, 'r_squared': None, 'adjusted_r_squared': None,
                'vif': {name: None for name in names}}, unavailable
    a = np.column_stack([np.ones(n), (raw - means) / scales])
    _, singular, vh = np.linalg.svd(a, full_matrices=False)
    rank = int((singular > SVD_RELATIVE_TOLERANCE * singular[0]).sum())
    condition = _finite(singular[0] / singular[-1]) if singular[-1] > 0 else None
    base.update(rank=rank, singular_values=singular.tolist(), standardized_condition_number=condition,
                standardized_condition_warning=bool(condition is None or condition > 30),
                svd_relative_rank_tolerance=SVD_RELATIVE_TOLERANCE)
    if rank < k:
        return {**base, 'status': 'unavailable_rank_deficient', 'r_squared': None,
                'adjusted_r_squared': None, 'vif': {name: None for name in names}}, unavailable
    theta = np.linalg.lstsq(a, yf, rcond=SVD_RELATIVE_TOLERANCE)[0]
    transform = np.zeros((k, k))
    transform[0, 0] = 1
    transform[0, 1:] = -means / scales
    transform[np.arange(1, k), np.arange(1, k)] = 1 / scales
    params = transform @ theta
    residual = yf - a @ theta
    covariance = {}
    for lag in (27, 7):
        standardized = calendar_hac_covariance(a, residual, mask, max_lag=lag)
        covariance[lag] = transform @ standardized @ transform.T
    bread = (vh.T / singular**2) @ vh
    # Standardized columns have centered sum of squares n, so n*diag(bread)
    # is the ordinary auxiliary-regression VIF, conditional on all other coins.
    vif = {name: float(n * bread[j + 1, j + 1]) for j, name in enumerate(names)}
    sst = float(np.dot(yf - yf.mean(), yf - yf.mean()))
    rss = float(np.dot(residual, residual))
    r2 = 1 - rss / sst if sst > 0 else None
    leverage = np.einsum('ij,jk,ik->i', a, bread, a)
    mse = rss / (n - k)
    cooks = residual**2 / (k * mse) * leverage / (1 - leverage)**2 if mse > 0 else np.full(n, np.nan)
    base.update(status='estimated_conditional_posthoc', vif=vif, vif_above_10=any(v > 10 for v in vif.values()),
                r_squared=r2, adjusted_r_squared=1 - (1 - r2) * (n - 1) / (n - k) if r2 is not None else None,
                maximum_leverage=_finite(np.max(leverage)), maximum_cooks_distance=_finite(np.nanmax(cooks)) if np.isfinite(cooks).any() else None,
                residual_sum_squares=rss)
    for j, term in enumerate(('alpha_annual', *names)):
        multiplier = YEAR_DAYS if j == 0 else 1.
        variance = float(covariance[27][j, j])
        se = math.sqrt(max(variance, 0)) * multiplier if variance >= -1e-14 else None
        estimate = float(params[j] * multiplier)
        z = estimate / se if se is not None and se > 0 else None
        raw_p = float(2 * norm.sf(abs(z))) if z is not None else None
        variance7 = float(covariance[7][j, j])
        se7 = math.sqrt(max(variance7, 0)) * multiplier if variance7 >= -1e-14 else None
        coefficients.append({'strategy_id': strategy_id, 'period': period, 'model_type': model_type,
            'term': term, 'coefficient_kind': 'annualized_intercept_alpha' if j == 0 else 'conditional_coin_beta',
            'estimate': estimate, 'hac27_se': se, 'hac27_z': z, 'hac27_two_sided_p': raw_p,
            'ci95_low': estimate - Z95 * se if se is not None else None,
            'ci95_high': estimate + Z95 * se if se is not None else None,
            'hac7_se': se7, 'hac7_ci95_low': estimate - Z95 * se7 if se7 is not None else None,
            'hac7_ci95_high': estimate + Z95 * se7 if se7 is not None else None,
            'ci_scope': 'marginal_approximate_conditional_not_search_adjusted',
            'n_fit_days': n, 'n_calendar_days': ncal})
    return base, coefficients


def fit_basket_model(strategy_daily, coin_daily, *, strategy_id, period, symbols):
    """Joint eight-coin model plus same-observation BTC-only comparator.

    Inputs retain every UTC date. Missing coin returns are permitted only as
    explicit NaNs; no row is silently removed from the returned sample audit.
    Financial path accounting must be independently reconciled by the caller.
    """
    if not isinstance(strategy_daily, pd.Series) or not isinstance(coin_daily, pd.DataFrame):
        raise ValueError('Use a daily strategy Series and eight-column factor DataFrame.')
    index = _calendar(strategy_daily.index)
    if not coin_daily.index.equals(strategy_daily.index):
        raise ValueError('Strategy and factors must retain exactly the same calendar.')
    names = list(symbols)
    if len(names) != 8 or len(set(names)) != 8 or list(coin_daily.columns) != names or 'BTCUSDT' not in names:
        raise ValueError('Exactly the frozen eight factors, in frozen order, including BTC are required.')
    y = strategy_daily.to_numpy(dtype=float)
    x = coin_daily.to_numpy(dtype=float)
    if not np.isfinite(y).all() or np.isinf(x).any():
        raise ValueError('Strategy daily returns must be finite; only explicit factor NaNs are permitted.')
    mask = np.isfinite(x).all(axis=1)
    joint, coefficients = _fit(y, x, mask, names, strategy_id=strategy_id, period=period, model_type='joint_eight_coin')
    btc, btc_coefficients = _fit(y, x[:, [names.index('BTCUSDT')]], mask, ['BTCUSDT'],
                                 strategy_id=strategy_id, period=period, model_type='btc_only_joint_matched_sample')
    sample = {'excluded_date_ranges': _ranges(index, ~mask),
              'first_fit_day': index[mask][0].date().isoformat() if mask.any() else None,
              'last_fit_day': index[mask][-1].date().isoformat() if mask.any() else None,
              'factor_missing_days': {name: int(np.isnan(x[:, j]).sum()) for j, name in enumerate(names)},
              'factor_missing_date_ranges': {name: _ranges(index, np.isnan(x[:, j])) for j, name in enumerate(names)}}
    joint.update(sample)
    btc.update(sample)
    return {'joint_model': joint, 'coefficients': coefficients, 'matched_btc_model': btc,
            'matched_btc_coefficients': btc_coefficients, 'fit_mask': mask}


def holm_adjust(pvalues):
    """Holm step-down; unavailable hypotheses remain in the family as p=1."""
    values = np.asarray([1. if p is None or not np.isfinite(p) else float(p) for p in pvalues])
    if values.ndim != 1 or ((values < 0) | (values > 1)).any():
        raise ValueError('P-values must lie in [0,1].')
    order = np.argsort(values, kind='stable')
    ranked = np.minimum(1., np.maximum.accumulate(values[order] * np.arange(len(values), 0, -1)))
    result = np.empty(len(values))
    result[order] = ranked
    return result


def adjust_joint_coefficient_family(rows, *, family_size=JOINT_FAMILY_SIZE):
    """Global 27 alpha + 216 beta descriptive inference family, no reselection.

    Unavailable models must be represented by explicit unavailable coefficient
    rows supplied by the caller, so all 243 hypotheses remain in the family.
    """
    if len(rows) != family_size or any(row['model_type'] != 'joint_eight_coin' for row in rows):
        raise ValueError('Retain all joint coefficient slots in the declared family.')
    keys = [(r['strategy_id'], r['period'], r['term']) for r in rows]
    if len(set(keys)) != family_size:
        raise ValueError('Duplicate joint coefficient hypothesis.')
    adjusted = holm_adjust([r.get('hac27_two_sided_p') for r in rows])
    critical = float(norm.ppf(1 - .05 / (2 * family_size)))
    output = []
    for row, p in zip(rows, adjusted):
        row = dict(row)
        estimate, se = row.get('estimate'), row.get('hac27_se')
        available = estimate is not None and se is not None and np.isfinite(estimate) and np.isfinite(se)
        row.update(global_holm243_p=float(p), multiplicity_family_size=family_size,
                   bonferroni243_ci95_low=float(estimate - critical * se) if available else None,
                   bonferroni243_ci95_high=float(estimate + critical * se) if available else None,
                   simultaneous_ci_scope='approximate_familywise_conditional_not_search_adjusted')
        output.append(row)
    return output


def circular_block_indices(n_days, *, replications=4000, seed=20261016, block_days=28):
    if n_days < 2 or replications < 2 or block_days < 1:
        raise ValueError('Positive calendar length, block length and at least two draws are required.')
    rng = np.random.Generator(np.random.PCG64(seed))
    starts = rng.integers(0, n_days, size=(replications, math.ceil(n_days / block_days)))
    return ((starts[..., None] + np.arange(block_days)) % n_days).reshape(replications, -1)[:, :n_days]


def linked_component_totals(gross, fees):
    """Link daily net-NAV-normalized components using fresh within-path NAV."""
    gross = np.asarray(gross, dtype=float)
    fees = np.asarray(fees, dtype=float)
    if gross.shape != fees.shape or gross.ndim not in (2, 3):
        raise ValueError('Gross and positive fee components must have the same [...,day,coin] shape.')
    net = gross - fees
    r = net.sum(axis=-1)
    with np.errstate(over='ignore', invalid='ignore'):
        wealth = np.cumprod(1 + r, axis=-1)
        prior = np.concatenate([np.ones((*wealth.shape[:-1], 1)), wealth[..., :-1]], axis=-1)
        g = (prior[..., None] * gross).sum(axis=-2)
        f = (prior[..., None] * fees).sum(axis=-2)
        n = g - f
        terminal = wealth[..., -1] - 1
    valid = (np.isfinite(gross).all(axis=(-2, -1)) & np.isfinite(fees).all(axis=(-2, -1))
             & (fees >= 0).all(axis=(-2, -1)) & (r > -1).all(axis=-1)
             & np.isfinite(wealth).all(axis=-1) & (wealth > 0).all(axis=-1)
             & np.isfinite(g).all(axis=-1) & np.isfinite(f).all(axis=-1) & np.isfinite(n).all(axis=-1))
    return {'gross': g, 'fees': f, 'net': n, 'terminal_net_return': terminal, 'valid': valid}


def attribution_intervals(daily_components: Mapping, *, period, symbol_map, replications=4000,
                          seed=20261016, block_days=28):
    """Synchronized, daily-vector circular bootstrap with NEW NAV relinking.

    One common calendar index matrix is used for all strategies in this period.
    Boundary entry/liquidation fees stay in their observed daily components;
    no additional charge is introduced at block boundaries. Invalid draws are
    counted, never dropped. Any invalid draw makes its strategy's intervals
    unavailable. Point contributions always retain the complete original path.
    """
    if set(daily_components) != set(STRATEGY_ORDER) or set(symbol_map) != set(STRATEGY_ORDER):
        raise ValueError('All nine frozen strategy identities must be supplied together.')
    ns = {np.asarray(daily_components[sid]['gross']).shape[0] for sid in STRATEGY_ORDER}
    if len(ns) != 1:
        raise ValueError('All nine strategies must retain the same calendar length.')
    n_days = ns.pop()
    indices = circular_block_indices(n_days, replications=replications, seed=seed, block_days=block_days)
    rows, totals = [], []
    for sid in STRATEGY_ORDER:
        gross = np.asarray(daily_components[sid]['gross'], dtype=float)
        fees = np.asarray(daily_components[sid]['fees'], dtype=float)
        if gross.shape != (n_days, 8) or fees.shape != gross.shape or len(symbol_map[sid]) != 8:
            raise ValueError('Each strategy requires exactly eight daily gross/positive-fee component columns.')
        point = linked_component_totals(gross, fees)
        if not bool(point['valid']):
            raise ValueError('Observed components are not finite, nonnegative-fee and compoundable.')
        if not np.isclose(point['net'].sum(), point['terminal_net_return'], rtol=1e-10, atol=1e-12):
            raise ValueError('Observed attribution does not reconcile to compounded terminal return.')
        samples = {name: np.empty((replications, 8), dtype=float) for name in ('gross', 'fees', 'net')}
        terminal = np.empty(replications, dtype=float)
        valid = np.empty(replications, dtype=bool)
        for left in range(0, replications, 32):
            right = min(left + 32, replications)
            selected = indices[left:right]
            result = linked_component_totals(gross[selected], fees[selected])
            for name in samples:
                samples[name][left:right] = result[name]
            terminal[left:right] = result['terminal_net_return']
            valid[left:right] = result['valid']
        valid &= np.isclose(samples['net'].sum(axis=1), terminal, rtol=1e-10, atol=1e-12)
        invalid = int((~valid).sum())
        status = 'unavailable_invalid_bootstrap_draws' if invalid else 'estimated_conditional_posthoc'
        for j, symbol in enumerate(symbol_map[sid]):
            row = {'strategy_id': sid, 'period': period, 'symbol': symbol, 'n_calendar_days': n_days,
                   'bootstrap_replications': replications, 'bootstrap_invalid_draws': invalid,
                   'bootstrap_status': status, 'ci_scope': 'marginal_approximate_conditional_not_search_adjusted',
                   'contribution_units': 'fraction_of_initial_net_NAV_whole_period_not_annualized'}
            for name in samples:
                lo, hi = np.quantile(samples[name][:, j], [.025, .975], method='linear') if not invalid else (None, None)
                row.update({f'{name}_linked_contribution': float(point[name][j]),
                            f'{name}_ci95_low': float(lo) if lo is not None else None,
                            f'{name}_ci95_high': float(hi) if hi is not None else None})
            rows.append(row)
        lo, hi = np.quantile(terminal, [.025, .975], method='linear') if not invalid else (None, None)
        totals.append({'strategy_id': sid, 'period': period, 'terminal_net_return': float(point['terminal_net_return']),
                       'net_contribution_sum': float(point['net'].sum()), 'bootstrap_invalid_draws': invalid,
                       'bootstrap_status': status, 'bootstrap_total_return_ci95_low': _finite(lo) if lo is not None else None,
                       'bootstrap_total_return_ci95_high': _finite(hi) if hi is not None else None,
                       'maximum_valid_draw_reconciliation_error': float(np.max(np.abs(samples['net'][valid].sum(axis=1) - terminal[valid]))) if valid.any() else None})
    return {'rows': rows, 'totals': totals, 'indices': indices,
            'method': {'period': period, 'n_calendar_days': n_days, 'replications': replications,
                       'seed': seed, 'rng': 'numpy.Generator(PCG64)', 'block_days': block_days,
                       'synchronized_nine': True, 'method': 'circular_daily_component_vectors_NEW_NAV_relink',
                       'signals_rerun': False, 'extra_fees_per_block': False,
                       'interval': 'marginal95_percentile_numpy_quantile_linear',
                       'invalid_policy': 'any_invalid_draw_makes_strategy_intervals_unavailable_no_draw_dropping',
                       'selection_adjusted': False}}
