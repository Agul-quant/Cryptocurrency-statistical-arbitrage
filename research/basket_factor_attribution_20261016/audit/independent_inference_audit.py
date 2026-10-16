"""Read-only independent statistical oracle; no scientific module imports.

Verify saved bytes before decoding. Raw-unit statsmodels OLS + raw-unit calendar
sandwich reproduce the standardized production implementation. Bootstrap uses
an independent log-wealth relinking implementation and independently generated
calendar blocks. Only files in this audit/ directory are written.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'audit'
REPAIR_SHA = '7fbcc73c997377cde875a0c2c802fdc5da2da80a3467e3b8f06157d5d7eb50c7'
ORDER = ('A01','A02','A03','A04','B01','B03','B04','B05','B06')
PERIODS = ('development','validation','oos_partial_2026_jan_sep')
NDAYS = {'development':730, 'validation':731, 'oos_partial_2026_jan_sep':273}
COUNTS = {}
MAX_ERRORS = {}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def close(actual, expected, label, *, atol=3e-10, rtol=3e-8):
    a, e = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    np.testing.assert_allclose(a, e, atol=atol, rtol=rtol, err_msg=label, equal_nan=True)
    COUNTS[label] = COUNTS.get(label, 0) + a.size
    finite = np.isfinite(a) & np.isfinite(e)
    error = float(np.max(np.abs(a[finite] - e[finite]))) if finite.any() else 0.
    MAX_ERRORS[label] = max(MAX_ERRORS.get(label, 0.), error)


def verify_custody():
    repair_path = AUDIT / 'volatile_log_custody.json'
    assert sha(repair_path) == REPAIR_SHA, 'Root technical custody amendment changed'
    repair = json.loads(repair_path.read_text())
    receipt_path = ROOT / 'outputs/computation_receipt.json'
    assert sha(receipt_path) == repair['computation_receipt_sha256']
    receipt = json.loads(receipt_path.read_text())
    freeze_path = ROOT / 'outputs/access_freeze.json'
    assert sha(freeze_path) == receipt['access_freeze_sha256']
    freeze = json.loads(freeze_path.read_text())
    assert freeze['authorized'] is True
    for rel, expected in freeze['code_sha256'].items():
        assert sha(ROOT / rel) == expected, 'Frozen analysis code changed: ' + rel
    assert sha(ROOT / 'protocol.json') == freeze['protocol_sha256'] == receipt['protocol_sha256']
    assert sha(ROOT / 'required_source_pins.json') == freeze['source_pins_sha256']
    stable = repair['stable_scientific_artifact_sha256']
    assert set(stable) == set(receipt['artifact_sha256']) - {'outputs/computation.log'}
    for rel, expected in stable.items():
        assert expected == receipt['artifact_sha256'][rel]
        assert sha(ROOT / rel) == expected, 'Changed scientific input: ' + rel
    assert len(stable) == 19
    for log in repair['volatile_log_repair']:
        assert log['intermediate_sha256'] == receipt['artifact_sha256'][log['path']]
        assert sha(ROOT / log['path']) == log['final_sha256']
    return receipt, stable


def calendar_covariance(raw, residual, mask, lag):
    n, p = raw.shape
    # A second implementation in original raw return units, not production's
    # standardized SVD coordinates. Rows retain their actual calendar offsets.
    score = np.zeros((len(mask), p))
    score[np.flatnonzero(mask)] = residual[:, None] * raw
    s = np.einsum('ti,tj->ij', score, score)
    for h in range(1, lag + 1):
        if h >= len(mask):
            break
        c = np.einsum('ti,tj->ij', score[h:], score[:-h])
        s += (1 - h / (lag + 1)) * (c + c.T)
    inv = np.linalg.inv(raw.T @ raw)
    return (n / (n - p)) * inv @ s @ inv


def audit_fit(y, factors, mask, saved_rows, model, label):
    raw = np.column_stack([np.ones(mask.sum()), factors[mask]])
    fit = sm.OLS(y[mask], raw).fit()
    names = ('alpha_annual', *model['_symbols'])
    rows = saved_rows.set_index('term').loc[list(names)]
    scale = np.r_[365., np.ones(len(names) - 1)]
    close(rows.estimate, fit.params * scale, label + '_coefficients')
    for lag in (27, 7):
        covariance = calendar_covariance(raw, fit.resid, mask, lag)
        se = np.sqrt(np.diag(covariance)) * scale
        close(rows[f'hac{lag}_se'], se, label + f'_HAC{lag}_SE')
        low, high = fit.params * scale - norm.ppf(.975) * se, fit.params * scale + norm.ppf(.975) * se
        close(rows['ci95_low' if lag == 27 else 'hac7_ci95_low'], low, label + f'_HAC{lag}_CI_low')
        close(rows['ci95_high' if lag == 27 else 'hac7_ci95_high'], high, label + f'_HAC{lag}_CI_high')
        if mask.all():
            reference = sm.OLS(y, raw).fit(cov_type='HAC', cov_kwds={'maxlags':lag, 'use_correction':True})
            close(rows[f'hac{lag}_se'], reference.bse * scale, label + f'_statsmodels_full_HAC{lag}')
        if lag == 27:
            z = fit.params * scale / se
            close(rows.hac27_z, z, label + '_z')
            close(rows.hac27_two_sided_p, 2 * norm.sf(np.abs(z)), label + '_raw_p', atol=2e-12)
    close(model['r_squared'], fit.rsquared, label + '_R2')
    close(model['adjusted_r_squared'], fit.rsquared_adj, label + '_adjusted_R2')
    centered = (factors[mask] - factors[mask].mean(axis=0)) / factors[mask].std(axis=0, ddof=0)
    standardized = np.column_stack([np.ones(mask.sum()), centered])
    singular = np.linalg.svd(standardized, compute_uv=False)
    close(model['standardized_condition_number'], np.linalg.cond(standardized), label + '_standardized_condition')
    assert model['rank'] == np.linalg.matrix_rank(standardized, tol=singular[0] * 1e-12)
    for j, symbol in enumerate(model['_symbols']):
        close(model['vif'][symbol], variance_inflation_factor(raw, j + 1), label + '_VIF')
    return fit


def independent_indices(n):
    rng = np.random.Generator(np.random.PCG64(20261016))
    generated = []
    for _ in range(4000):
        starts = rng.integers(0, n, math.ceil(n / 28))
        generated.append(np.concatenate([(s + np.arange(28)) % n for s in starts])[:n])
    return np.asarray(generated)


def independent_link(gross, fees):
    daily = np.sum(gross - fees, axis=-1)
    # Production uses cumprod; this independent oracle reconstructs prior NAV
    # via log accumulation, retaining every component and all calendar days.
    log = np.log1p(daily)
    prior = np.exp(np.concatenate([np.zeros((*daily.shape[:-1], 1)), np.cumsum(log, axis=-1)[..., :-1]], axis=-1))
    g = np.einsum('...ti,...t->...i', gross, prior)
    f = np.einsum('...ti,...t->...i', fees, prior)
    terminal = np.expm1(np.sum(log, axis=-1))
    return g, f, g - f, terminal


def main():
    receipt, pins = verify_custody()  # ALL scientific bytes checked BEFORE decode
    def frame(name):
        rel = 'outputs/' + name
        assert sha(ROOT / rel) == pins[rel]
        return pd.read_parquet(ROOT / rel) if name.endswith('.parquet') else pd.read_csv(ROOT / rel)
    def blob(name):
        rel = 'outputs/' + name
        assert sha(ROOT / rel) == pins[rel]
        return json.loads((ROOT / rel).read_text())
    daily = frame('daily_model_inputs.parquet')
    components = frame('daily_attribution_components.parquet')
    coef = frame('joint_coefficients.csv')
    matched = frame('matched_btc_coefficients.csv')
    legacy = frame('legacy_btc_comparison.csv')
    calendar = frame('regression_sample_calendar.csv')
    ledger = frame('coin_attribution.csv')
    totals = frame('attribution_totals.csv')
    flat = frame('joint_models.csv')
    models = blob('joint_models.json')
    btc_models = blob('matched_btc_models.json')
    methods = blob('bootstrap_methods.json')
    path_audits = blob('path_accounting_audit.json')
    assert len(models) == len(btc_models) == len(legacy) == len(totals) == len(path_audits) == 27
    assert len(coef) == 243 and len(matched) == 54 and len(ledger) == 216
    assert set(coef.strategy_id) == set(ORDER) and set(coef.period) == set(PERIODS)
    assert all(a['all_accounting_checks_passed'] for a in path_audits)
    details, a03 = [], []
    for period in PERIODS:
        for sid in ORDER:
            selected = daily.loc[daily.period.eq(period) & daily.strategy_id.eq(sid)].sort_values('utc_day')
            selected['utc_day'] = pd.to_datetime(selected.utc_day, utc=True)
            assert len(selected) == NDAYS[period]
            assert selected.utc_day.reset_index(drop=True).equals(pd.Series(pd.date_range(selected.utc_day.iloc[0], periods=NDAYS[period], freq='D'), name='utc_day'))
            model = next(m for m in models if m['period'] == period and m['strategy_id'] == sid)
            model = dict(model)
            names = flat.loc[flat.period.eq(period) & flat.strategy_id.eq(sid), 'symbols'].iloc[0].split(',')
            model['_symbols'] = names
            y = selected.strategy_net_return.to_numpy()
            x = selected[names].to_numpy()
            mask = np.isfinite(x).all(axis=1)
            assert np.isfinite(y).all() and (y > -1).all()
            assert model['n_calendar_days'] == len(y) and model['n_fit_days'] == mask.sum()
            scope = calendar.loc[calendar.period.eq(period) & calendar.strategy_id.eq(sid)].sort_values('utc_day')
            np.testing.assert_array_equal(scope.included_joint_regression.to_numpy(), mask)
            joint_rows = coef.loc[coef.period.eq(period) & coef.strategy_id.eq(sid)]
            joint_fit = audit_fit(y, x, mask, joint_rows, model, 'joint')
            influence = joint_fit.get_influence()
            leverage = influence.hat_matrix_diag
            cooks = influence.cooks_distance[0]
            leverage_pos, cooks_pos = int(np.argmax(leverage)), int(np.nanargmax(cooks))
            retained_days = selected.utc_day.iloc[np.flatnonzero(mask)].reset_index(drop=True)
            close(model['maximum_leverage'], leverage[leverage_pos], 'joint_maximum_leverage')
            close(model['maximum_cooks_distance'], cooks[cooks_pos], 'joint_maximum_Cooks_distance')
            factor_position = np.unravel_index(np.nanargmax(np.abs(x)), x.shape)
            bm = dict(next(m for m in btc_models if m['period'] == period and m['strategy_id'] == sid))
            bm['_symbols'] = ['BTCUSDT']
            audit_fit(y, x[:, [names.index('BTCUSDT')]], mask,
                      matched.loc[matched.period.eq(period) & matched.strategy_id.eq(sid)], bm, 'matched_BTC')
            # Saved legacy values use the full daily calendar and NO finite-
            # sample multiplier, exactly the old statsmodels HAC7 convention.
            btc = x[:, names.index('BTCUSDT')]
            assert np.isfinite(btc).all()
            oldfit = sm.OLS(y, sm.add_constant(btc)).fit(cov_type='HAC', cov_kwds={'maxlags':7})
            old = legacy.loc[legacy.period.eq(period) & legacy.strategy_id.eq(sid)].iloc[0]
            close([old.alpha_annual, old.beta], oldfit.params * [365., 1.], 'legacy_BTC_points')
            close([old.alpha_ci95_low, old.beta_ci95_low], oldfit.conf_int()[:, 0] * [365., 1.], 'legacy_BTC_CI_low')
            close([old.alpha_ci95_high, old.beta_ci95_high], oldfit.conf_int()[:, 1] * [365., 1.], 'legacy_BTC_CI_high')
            close(old.alpha_pvalue, oldfit.pvalues[0], 'legacy_BTC_alpha_p')
            details.append({'strategy_id':sid, 'period':period, 'n_calendar_days':len(y), 'n_fit_days':int(mask.sum()),
                            'n_excluded_days':int((~mask).sum()), 'excluded_date_ranges':model['excluded_date_ranges'],
                            'rank':int(model['rank']), 'condition_number':model['standardized_condition_number'],
                            'max_VIF':max(model['vif'].values()),
                            'maximum_leverage':float(leverage[leverage_pos]),
                            'maximum_leverage_UTC_day':retained_days.iloc[leverage_pos].date().isoformat(),
                            'maximum_leverage_factor_returns':dict(zip(names, x[mask][leverage_pos].tolist())),
                            'maximum_Cooks_distance':float(cooks[cooks_pos]),
                            'maximum_Cooks_UTC_day':retained_days.iloc[cooks_pos].date().isoformat(),
                            'maximum_Cooks_factor_returns':dict(zip(names, x[mask][cooks_pos].tolist())),
                            'maximum_Cooks_strategy_return':float(y[mask][cooks_pos]),
                            'maximum_absolute_factor_return':float(x[factor_position]),
                            'maximum_absolute_factor_symbol':names[factor_position[1]],
                            'maximum_absolute_factor_UTC_day':selected.utc_day.iloc[factor_position[0]].date().isoformat(),
                            'influence_caveat':'No observations dropped/refit; low collinearity does not remove high-leverage or heavy-tail inference fragility.'})
            if sid == 'A03':
                alpha = joint_rows.loc[joint_rows.term.eq('alpha_annual')].iloc[0]
                a03.append({'period':period, 'legacy_BTC_alpha_annual':float(old.alpha_annual),
                            'joint_alpha_annual':float(alpha.estimate), 'joint_alpha_ci95_low':float(alpha.ci95_low),
                            'joint_alpha_ci95_high':float(alpha.ci95_high), 'joint_alpha_global_Holm243_p':float(alpha.global_holm243_p),
                            'net_return_unchanged':float(np.expm1(np.log1p(y).sum())),
                            'interpretation':'conditional post-hoc accounting/risk diagnostic; no new winner or changed original acceptance'})
    p = coef.hac27_two_sided_p.to_numpy()
    close(coef.global_holm243_p, multipletests(p, alpha=.05, method='holm')[1], 'global243_Holm', atol=1e-12)
    critical = norm.isf(.05 / (2 * 243))
    close(coef.bonferroni243_ci95_low, coef.estimate - critical * coef.hac27_se, 'global243_Bonferroni_low')
    close(coef.bonferroni243_ci95_high, coef.estimate + critical * coef.hac27_se, 'global243_Bonferroni_high')
    boot_summary = []
    for period in PERIODS:
        rel = 'outputs/bootstrap_indices_' + period + '.npy'
        assert sha(ROOT / rel) == pins[rel]
        saved_indices = np.load(ROOT / rel, allow_pickle=False)
        indices = independent_indices(NDAYS[period])
        np.testing.assert_array_equal(saved_indices, indices)
        assert next(m for m in methods if m['period'] == period)['replications'] == 4000
        period_invalid = 0
        for sid in ORDER:
            part = components.loc[components.period.eq(period) & components.strategy_id.eq(sid)]
            names = flat.loc[flat.period.eq(period) & flat.strategy_id.eq(sid), 'symbols'].iloc[0].split(',')
            gross = part.pivot(index='utc_day', columns='symbol', values='gross_component').loc[:, names].to_numpy()
            fees = part.pivot(index='utc_day', columns='symbol', values='fee_component').loc[:, names].to_numpy()
            assert gross.shape == fees.shape == (NDAYS[period], 8)
            assert np.isfinite(gross).all() and np.isfinite(fees).all() and (fees >= 0).all()
            selected = daily.loc[daily.period.eq(period) & daily.strategy_id.eq(sid)].sort_values('utc_day')
            close((gross - fees).sum(axis=1), selected.strategy_net_return, 'daily_component_reconciliation', atol=3e-13)
            saved = ledger.loc[ledger.period.eq(period) & ledger.strategy_id.eq(sid)].set_index('symbol').loc[names]
            pg, pf, pn, pt = independent_link(gross, fees)
            close(saved.gross_linked_contribution, pg, 'observed_coin_gross')
            close(saved.fees_linked_contribution, pf, 'observed_coin_fee')
            close(saved.net_linked_contribution, pn, 'observed_coin_net')
            close(pn.sum(), pt, 'observed_component_total')
            samples = [np.empty((4000, 8)) for _ in range(3)]
            terminal = np.empty(4000)
            for start in range(0, 4000, 64):
                finish = min(start + 64, 4000)
                idx = indices[start:finish]
                linked = independent_link(gross[idx], fees[idx])
                for j in range(3):
                    samples[j][start:finish] = linked[j]
                terminal[start:finish] = linked[3]
            valid = np.isfinite(terminal) & np.isfinite(samples[2]).all(axis=1)
            invalid = int((~valid).sum())
            period_invalid += invalid
            assert (saved.bootstrap_invalid_draws == invalid).all()
            assert invalid == 0
            close(samples[2].sum(axis=1), terminal, 'every_bootstrap_draw_compounding_reconciliation', atol=1e-11)
            for j, name in enumerate(('gross','fees','net')):
                low, high = np.percentile(samples[j], [2.5,97.5], axis=0, method='linear')
                close(saved[name + '_ci95_low'], low, 'bootstrap_' + name + '_CI_low')
                close(saved[name + '_ci95_high'], high, 'bootstrap_' + name + '_CI_high')
            totalrow = totals.loc[totals.period.eq(period) & totals.strategy_id.eq(sid)].iloc[0]
            close(totalrow.terminal_net_return, pt, 'attribution_total_point')
            close([totalrow.bootstrap_total_return_ci95_low, totalrow.bootstrap_total_return_ci95_high],
                  np.percentile(terminal, [2.5,97.5], method='linear'), 'bootstrap_total_return_CI')
        boot_summary.append({'period':period, 'n_days':NDAYS[period], 'n_strategies':9,
                             'synchronized_draws':4000, 'invalid_strategy_draws':period_invalid,
                             'new_NAV_and_all_1296_gross_fee_net_CI_endpoints_across_periods':'independently_reproduced'})
    verify_custody()  # Repeat custody check; audit never modifies scientific bytes
    output = {'status':'PASS', 'created_at_utc':datetime.now(timezone.utc).isoformat(),
              'audit_code_sha256':sha(__file__), 'computation_receipt_sha256':sha(ROOT / 'outputs/computation_receipt.json'),
              'technical_log_custody_amendment_sha256':REPAIR_SHA, 'verified_stable_scientific_files':len(pins),
              'no_scientific_code_imports':True, 'no_scientific_outputs_changed':True,
              'joint_models_independently_reproduced':27, 'matched_BTC_models_independently_reproduced':27,
              'legacy_BTC_models_independently_reproduced':27, 'joint_coefficients_and_CIs':243,
              'coin_rows_and_CIs':216, 'multiple_testing_family':243, 'all_invalid_bootstrap_counts_zero':True,
              'numeric_checks':COUNTS, 'maximum_absolute_errors':MAX_ERRORS,
              'model_sample_and_collinearity':details, 'bootstrap':boot_summary, 'A03_descriptive_findings':a03,
              'limitations':['Model inference is conditional post-hoc, not a fresh holdout or search-adjusted alpha.',
                             'Missing-factor models describe observed joint-factor days, not unavailable full-period factor returns.',
                             'Gross leg P&L is linked to net NAV; coefficient beta is not a portfolio weight or hedge prescription.',
                             'This audit validates inference/compounding on supplied daily inputs, not raw archive or signal reconstruction.']}
    path = AUDIT / 'independent_inference_audit.json'
    path.write_text(json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'status':output['status'], 'receipt':str(path), 'receipt_sha256':sha(path),
                      'joint_models':27, 'matched_BTC_models':27, 'legacy_BTC_models':27,
                      'joint_coefficients':243, 'coin_rows':216, 'A03_descriptive_findings':a03}, indent=2))


if __name__ == '__main__':
    main()
