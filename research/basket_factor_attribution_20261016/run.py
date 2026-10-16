"""Finite post-hoc diagnostics from 27 saved paths; never run a trading rule."""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from research.basket_factor_attribution_20261016.gate import assert_frozen, save, sha, now
from research.basket_factor_attribution_20261016.accounting import build_inputs
from research.basket_factor_attribution_20261016.inference import (
    STRATEGY_ORDER, PERIOD_ORDER, fit_basket_model, attribution_intervals,
    adjust_joint_coefficient_family,
)

def clean(value):
    if isinstance(value, dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(v) for v in value]
    if isinstance(value, np.ndarray): return clean(value.tolist())
    if isinstance(value, (np.bool_,)): return bool(value)
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (float, np.floating)): return float(value) if np.isfinite(value) else None
    if isinstance(value, pd.Timestamp): return value.isoformat()
    return value

def csv(rows, name):
    table = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    table.to_csv(ROOT/'outputs'/name, index=False, float_format='%.17g')
    return table

def legacy_record(row):
    return clean({'strategy_id':row.comparison_id, 'period':row.period,
        'model_type':'legacy_btc_full_period_saved_HAC7',
        'alpha_annual':row.alpha_annual, 'alpha_ci95_low':row.alpha_ci_low,
        'alpha_ci95_high':row.alpha_ci_high, 'beta':row.beta,
        'beta_ci95_low':row.beta_ci_low, 'beta_ci95_high':row.beta_ci_high,
        'alpha_pvalue':row.alpha_pvalue, 'n_days':int(row.n_complete_utc_days),
        'covariance':'legacy_statsmodels_HAC7_no_finite_sample_correction',
        'selection_adjusted':False})

def main():
    assert_frozen('Execute the declared finite diagnostic fit and conditional resampling')
    if (ROOT/'outputs/computation_receipt.json').exists():
        raise RuntimeError('Completed diagnostic outputs already exist; do not overwrite a sealed result')
    inputs = build_inputs()
    coefficients, models, btc_coeff, btc_models, calendar, daily_rows, components = [], [], [], [], [], [], []
    coin_rows, bootstrap_totals, methods = [], [], []
    for period in PERIOD_ORDER:
        group = inputs['by_period'][period]
        for sid in STRATEGY_ORDER:
            y = group['strategy_daily'][sid]
            factors = group['coin_daily'][sid]
            fit = fit_basket_model(y, factors, strategy_id=sid, period=period, symbols=group['symbol_map'][sid])
            models.append(fit['joint_model']);coefficients.extend(fit['coefficients'])
            btc_models.append(fit['matched_btc_model']);btc_coeff.extend(fit['matched_btc_coefficients'])
            for i, day in enumerate(y.index):
                missing = [s for s in factors.columns if pd.isna(factors.iloc[i][s])]
                calendar.append({'strategy_id':sid, 'period':period, 'utc_day':day,
                    'included_joint_regression':bool(fit['fit_mask'][i]), 'missing_factor_symbols':','.join(missing)})
                daily_rows.append({'strategy_id':sid,'period':period,'utc_day':day,
                    'strategy_net_return':float(y.iloc[i]), **factors.iloc[i].to_dict()})
                for j,symbol in enumerate(factors.columns):
                    c = group['daily_components'][sid]
                    components.append({'strategy_id':sid,'period':period,'utc_day':day,'symbol':symbol,
                        'gross_component':float(c['gross'][i,j]), 'fee_component':float(c['fees'][i,j])})
            print('fit', sid, period, fit['joint_model']['n_fit_days'], '/',len(y), flush=True)
        boot = attribution_intervals(group['daily_components'], period=period, symbol_map=group['symbol_map'],
                                    replications=4000, seed=20261016, block_days=28)
        coin_rows.extend(boot['rows']);bootstrap_totals.extend(boot['totals']);methods.append(boot['method'])
        np.save(ROOT/'outputs'/('bootstrap_indices_'+period+'.npy'), boot['indices'], allow_pickle=False)
        print('bootstrap',period,'4000 synchronized draws',flush=True)
    coefficients = adjust_joint_coefficient_family(coefficients)
    assert len(coefficients)==243 and len(coin_rows)==216 and len(models)==27
    original = inputs['coin_attribution'].rename(columns={'comparison_id':'strategy_id'})
    coin = pd.DataFrame(coin_rows).merge(original,on=['strategy_id','period','symbol'],validate='one_to_one',suffixes=('','_saved'))
    for new,old in [('gross_linked_contribution','gross_linked_contribution_saved'),
                    ('fees_linked_contribution','linked_fees'),('net_linked_contribution','net_linked_contribution_saved')]:
        np.testing.assert_allclose(coin[new],coin[old],rtol=3e-10,atol=3e-12)
    legacy = [legacy_record(r) for r in inputs['legacy_metrics'].itertuples()]
    model_flat=[]
    for r in models:
        row={k:v for k,v in r.items() if not isinstance(v,(list,dict))}
        row.update(symbols=','.join(inputs['by_period'][r['period']]['symbol_map'][r['strategy_id']]),
                   vif_max=max([v for v in r['vif'].values() if v is not None],default=np.nan),
                   excluded_date_ranges_json=json.dumps(r['excluded_date_ranges']),
                   vif_json=json.dumps(r['vif']))
        model_flat.append(row)
    csv(coefficients,'joint_coefficients.csv');csv(model_flat,'joint_models.csv')
    csv(btc_coeff,'matched_btc_coefficients.csv');csv(legacy,'legacy_btc_comparison.csv')
    csv(coin,'coin_attribution.csv');csv(bootstrap_totals,'attribution_totals.csv')
    csv(calendar,'regression_sample_calendar.csv');csv(inputs['path_audits'],'path_accounting_audit.csv')
    daily_frame=pd.DataFrame(daily_rows);daily_frame.to_parquet(ROOT/'outputs/daily_model_inputs.parquet',index=False)
    pd.DataFrame(components).to_parquet(ROOT/'outputs/daily_attribution_components.parquet',index=False)
    save(ROOT/'outputs/joint_models.json',clean(models))
    save(ROOT/'outputs/matched_btc_models.json',clean(btc_models))
    save(ROOT/'outputs/metadata.json',clean(inputs['metadata']))
    save(ROOT/'outputs/bootstrap_methods.json',clean(methods))
    save(ROOT/'outputs/path_accounting_audit.json',clean(inputs['path_audits']))
    payload={'classification':'posthoc_fixed_strategy_attribution_no_reselection',
             'method':json.loads((ROOT/'protocol.json').read_text()), 'periods':{}}
    for period in PERIOD_ORDER:
        payload['periods'][period]={'models':[r for r in models if r['period']==period],
            'joint_coefficients':[r for r in coefficients if r['period']==period],
            'legacy_btc':[r for r in legacy if r['period']==period],
            'matched_btc_models':[r for r in btc_models if r['period']==period],
            'matched_btc_coefficients':[r for r in btc_coeff if r['period']==period],
            'coin_attribution':coin.loc[coin.period.eq(period)].to_dict('records'),
            'attribution_totals':[r for r in bootstrap_totals if r['period']==period]}
    save(ROOT/'outputs/report_payload.json',clean(payload))
    output_pins={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'outputs').iterdir()
                 if p.is_file() and p.name not in ('computation_receipt.json','source_access_receipt.json','access_freeze.json')}
    receipt={'status':'completed_fixed_27_path_diagnostic_computation_pending_independent_audit',
        'created_at_utc':now(),'paths':27,'coin_rows':216,'joint_coefficient_slots':243,
        'matched_btc_models':27,'legacy_btc_models':27,
        'all_accounting_checks_passed':all(r['all_accounting_checks_passed'] for r in inputs['path_audits']),
        'no_new_prices_or_strategy_execution_or_reselection':True,
        'protocol_sha256':sha(ROOT/'protocol.json'),'access_freeze_sha256':sha(ROOT/'outputs/access_freeze.json'),
        'artifact_sha256':output_pins}
    save(ROOT/'outputs/computation_receipt.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='artifact_sha256'},indent=2))

if __name__=='__main__': main()
