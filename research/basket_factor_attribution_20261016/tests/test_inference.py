"""Synthetic-only statistical/accounting oracles; never load market data."""
import math

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from research.basket_factor_attribution_20261016 import inference as mod


SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'C3USDT', 'C4USDT', 'C5USDT', 'C6USDT', 'C7USDT', 'C8USDT']


def fixture(n=365):
    rng = np.random.default_rng(381)
    factors = rng.normal(0, .03, (n, 8))
    factors[:, 1] += .5 * factors[:, 0]
    noise = rng.normal(0, .002, n)
    noise[1:] += .4 * noise[:-1]
    beta = np.arange(1, 9) / 20
    y = .0003 + factors @ beta + noise
    index = pd.date_range('2022-01-01', periods=n, tz='UTC', freq='D')
    return pd.Series(y, index=index), pd.DataFrame(factors, columns=SYMBOLS, index=index)


def test_joint_point_and_hac_match_independent_statsmodels_full_calendar():
    y, x = fixture()
    result = mod.fit_basket_model(y, x, strategy_id='A03', period='development', symbols=SYMBOLS)
    rows = result['coefficients']
    oracle = sm.OLS(y.to_numpy(), sm.add_constant(x.to_numpy())).fit(
        cov_type='HAC', cov_kwds={'maxlags': 27, 'use_correction': True})
    scale = np.r_[365., np.ones(8)]
    np.testing.assert_allclose([r['estimate'] for r in rows], oracle.params * scale, atol=1e-11, rtol=1e-11)
    np.testing.assert_allclose([r['hac27_se'] for r in rows], oracle.bse * scale, atol=1e-11, rtol=1e-11)
    np.testing.assert_allclose([r['ci95_low'] for r in rows], oracle.conf_int()[:, 0] * scale, atol=1e-11, rtol=1e-11)
    assert result['joint_model']['rank'] == 9
    assert result['joint_model']['n_fit_days'] == len(y)
    assert result['joint_model']['r_squared'] == pytest.approx(oracle.rsquared)
    assert result['joint_model']['adjusted_r_squared'] == pytest.approx(oracle.rsquared_adj)
    for j, name in enumerate(SYMBOLS):
        others = np.delete(x.to_numpy(), j, axis=1)
        aux = sm.OLS(x[name].to_numpy(), sm.add_constant(others)).fit()
        assert result['joint_model']['vif'][name] == pytest.approx(1 / (1 - aux.rsquared))


def test_calendar_hac_missing_gap_uses_actual_day_pairs_not_compressed_rows():
    y, x = fixture(250)
    x.iloc[30:70, 3] = np.nan
    x.iloc[160:180, 2] = np.nan
    result = mod.fit_basket_model(y, x, strategy_id='A01', period='development', symbols=SYMBOLS)
    mask = x.notna().all(axis=1).to_numpy()
    raw = sm.add_constant(x.loc[mask].to_numpy())
    yf = y.loc[mask].to_numpy()
    coeff = np.linalg.lstsq(raw, yf, rcond=None)[0]
    residual = yf - raw @ coeff
    # Independent direct pairwise calendar oracle in raw coefficient units.
    dates = np.flatnonzero(mask)
    meat = np.zeros((9, 9))
    for i in range(len(dates)):
        gi = raw[i] * residual[i]
        meat += np.outer(gi, gi)
        for j in range(i):
            lag = dates[i] - dates[j]
            if lag <= 27:
                gj = raw[j] * residual[j]
                meat += (1 - lag / 28) * (np.outer(gi, gj) + np.outer(gj, gi))
    bread = np.linalg.inv(raw.T @ raw)
    expected = len(dates) / (len(dates) - 9) * bread @ meat @ bread
    scale = np.r_[365., np.ones(8)]
    np.testing.assert_allclose([r['hac27_se'] for r in result['coefficients']], np.sqrt(np.diag(expected)) * scale,
                               atol=1e-10, rtol=1e-10)
    compressed = sm.OLS(yf, raw).fit(cov_type='HAC', cov_kwds={'maxlags': 27, 'use_correction': True})
    assert not np.allclose(np.sqrt(np.diag(expected)), compressed.bse, rtol=1e-3, atol=0)
    model = result['joint_model']
    assert model['n_fit_days'] == 190
    assert model['excluded_date_ranges'] == [
        {'start': '2022-01-31', 'end_inclusive': '2022-03-11', 'n_days': 40},
        {'start': '2022-06-10', 'end_inclusive': '2022-06-29', 'n_days': 20}]
    btc = result['matched_btc_model']
    assert btc['n_fit_days'] == model['n_fit_days']
    assert btc['excluded_date_ranges'] == model['excluded_date_ranges']
    assert len(result['matched_btc_coefficients']) == 2


def test_factor_gaps_are_not_filled_and_calendar_compression_rejected():
    y, x = fixture(100)
    x.iloc[5, 0] = np.nan
    result = mod.fit_basket_model(y, x, strategy_id='A01', period='development', symbols=SYMBOLS)
    assert result['joint_model']['n_excluded_days'] == 1
    assert pd.isna(x.iloc[5, 0])
    with pytest.raises(ValueError, match='contiguous calendar'):
        mod.fit_basket_model(y.drop(y.index[5]), x.drop(x.index[5]), strategy_id='A01', period='development', symbols=SYMBOLS)
    with pytest.raises(ValueError, match='frozen order'):
        mod.fit_basket_model(y, x[SYMBOLS[::-1]], strategy_id='A01', period='development', symbols=SYMBOLS)


@pytest.mark.parametrize('constant', [True, False])
def test_unidentified_model_keeps_all_nine_unavailable_coefficient_slots(constant):
    y, x = fixture(150)
    x.iloc[:, -1] = 0 if constant else x.iloc[:, -2]
    result = mod.fit_basket_model(y, x, strategy_id='A01', period='development', symbols=SYMBOLS)
    assert result['joint_model']['status'].startswith('unavailable_')
    assert len(result['coefficients']) == 9
    assert all(r['estimate'] is None for r in result['coefficients'])
    assert result['matched_btc_model']['status'] == 'estimated_conditional_posthoc'


def test_holm_family_retains_undefined_slots_and_bonferroni_is_wider():
    rows = []
    for p in mod.PERIOD_ORDER:
        for sid in mod.STRATEGY_ORDER:
            for name in ['alpha_annual', *SYMBOLS]:
                rows.append({'strategy_id': sid, 'period': p, 'model_type': 'joint_eight_coin', 'term': name,
                             'estimate': .1, 'hac27_se': .02, 'hac27_two_sided_p': .02})
    rows[0].update(estimate=None, hac27_se=None, hac27_two_sided_p=None)
    adjusted = mod.adjust_joint_coefficient_family(rows)
    assert len(adjusted) == 243
    assert adjusted[0]['global_holm243_p'] == 1
    assert adjusted[0]['bonferroni243_ci95_low'] is None
    assert adjusted[1]['bonferroni243_ci95_low'] < .1 - mod.Z95 * .02
    np.testing.assert_allclose(mod.holm_adjust([.01, .03, .04, None]), [.04, .09, .09, 1])
    with pytest.raises(ValueError, match='all joint coefficient slots'):
        mod.adjust_joint_coefficient_family(rows[:-1])


def component_fixture(n=80):
    rng = np.random.default_rng(881)
    gross = rng.normal(.0002, .001, size=(n, 8))
    gross[:, 0] += .001
    fees = np.zeros((n, 8))
    fees[0] = .0002  # original entry fee must not be recharged per block
    fees[-1] = .0002
    return {sid: {'gross': gross.copy(), 'fees': fees.copy()} for sid in mod.STRATEGY_ORDER}, {sid: SYMBOLS for sid in mod.STRATEGY_ORDER}


def test_new_nav_relink_reconciles_each_bootstrap_path_and_is_not_old_nav_sum():
    components, symbols = component_fixture()
    result = mod.attribution_intervals(components, period='development', symbol_map=symbols, replications=40)
    assert result['indices'].shape == (40, 80)
    assert len(result['rows']) == 72
    assert len(result['totals']) == 9
    assert all(r['bootstrap_invalid_draws'] == 0 for r in result['rows'])
    assert max(r['maximum_valid_draw_reconciliation_error'] for r in result['totals']) < 1e-12
    a, b = result['rows'][:8], result['rows'][8:16]
    for ra, rb in zip(a, b):
        assert ra['net_ci95_low'] == rb['net_ci95_low']
        assert ra['net_ci95_high'] == rb['net_ci95_high']
    gross, fees = components['A01']['gross'], components['A01']['fees']
    daily = (gross - fees).sum(axis=1)
    original_prior = np.r_[1., np.cumprod(1 + daily)[:-1]]
    original_linked = original_prior[:, None] * (gross - fees)
    idx = result['indices'][0]
    new = mod.linked_component_totals(gross[idx], fees[idx])
    assert not np.allclose(original_linked[idx].sum(axis=0), new['net'], rtol=1e-3, atol=0)
    np.testing.assert_allclose(new['net'].sum(), np.prod(1 + daily[idx]) - 1, atol=1e-12)


def test_identity_calendar_keeps_entry_and_terminal_fees_once(monkeypatch):
    components, symbols = component_fixture(60)
    monkeypatch.setattr(mod, 'circular_block_indices', lambda n_days, **kwargs: np.tile(np.arange(n_days), (kwargs['replications'], 1)))
    result = mod.attribution_intervals(components, period='development', symbol_map=symbols, replications=4)
    for row in result['rows']:
        for name in ('gross', 'fees', 'net'):
            assert row[f'{name}_ci95_low'] == pytest.approx(row[f'{name}_linked_contribution'])
            assert row[f'{name}_ci95_high'] == pytest.approx(row[f'{name}_linked_contribution'])


def test_any_invalid_bootstrap_draw_disables_ci_without_silent_dropping(monkeypatch):
    components, symbols = component_fixture(60)
    actual = mod.linked_component_totals
    def invalid_first_draw(gross, fees):
        result = actual(gross, fees)
        if np.asarray(gross).ndim == 3:
            result['valid'][0] = False
        return result
    monkeypatch.setattr(mod, 'linked_component_totals', invalid_first_draw)
    result = mod.attribution_intervals(components, period='development', symbol_map=symbols, replications=4)
    assert all(r['bootstrap_invalid_draws'] == 1 for r in result['rows'])
    assert all(r['net_ci95_low'] is None and r['net_ci95_high'] is None for r in result['rows'])
    assert all(r['bootstrap_status'] == 'unavailable_invalid_bootstrap_draws' for r in result['rows'])


def test_circular_indices_are_seeded_true_blocks_and_synchronized():
    indices = mod.circular_block_indices(75, replications=10)
    np.testing.assert_array_equal(indices, mod.circular_block_indices(75, replications=10))
    assert indices.shape == (10, 75)
    for start in (0, 28, 56):
        block = indices[:, start:min(start + 28, 75)]
        assert np.all((np.diff(block, axis=1) % 75) == 1)
