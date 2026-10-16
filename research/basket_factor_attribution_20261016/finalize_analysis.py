"""Final source, result, chronology and preservation acceptance; no model fits."""
from pathlib import Path
import json
import sys
from datetime import datetime
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from research.basket_factor_attribution_20261016.gate import assert_frozen,sha,save,now

def read(rel):return json.loads((ROOT/rel).read_text())
def pin(path,digest):
    if sha(path)!=digest:raise ValueError('Changed pinned artifact: '+str(path))

def check():
    freeze=assert_frozen('Final additional-attribution acceptance')
    access=read('outputs/source_access_receipt.json')
    assert datetime.fromisoformat(freeze['created_at_utc'])<datetime.fromisoformat(access['created_at_utc'])
    for rel,digest in read('required_source_pins.json')['source_sha256'].items():pin(REPO/rel,digest)
    custody=read('audit/volatile_log_custody.json')
    pin(ROOT/'outputs/computation_receipt.json',custody['computation_receipt_sha256'])
    for rel,digest in custody['stable_scientific_artifact_sha256'].items():pin(ROOT/rel,digest)
    for r in custody['volatile_log_repair']:pin(ROOT/r['path'],r['final_sha256'])
    preservation=read('audit/original_preservation.json')
    old=REPO/'final_reports_20261015'
    pin(old/'final_delivery_manifest.json',preservation['final_reports_20261015']['manifest_sha256'])
    for rel,digest in preservation['final_reports_20261015']['files'].items():pin(old/rel,digest)
    for rel,digest in preservation['earlier_documents'].items():pin(REPO/rel,digest)
    for rel in ['audit/independent_accounting.json','audit/independent_inference_audit.json']:
        assert read(rel)['status'].upper().startswith('PASS'),rel
    coeff=pd.read_csv(ROOT/'outputs/joint_coefficients.csv')
    coins=pd.read_csv(ROOT/'outputs/coin_attribution.csv')
    models=pd.read_csv(ROOT/'outputs/joint_models.csv')
    calendar=pd.read_csv(ROOT/'outputs/regression_sample_calendar.csv')
    totals=pd.read_csv(ROOT/'outputs/attribution_totals.csv')
    saved=pd.read_csv(REPO/'research/post_oos_diagnostics_20261015/shared/metrics.csv')
    saved=saved[saved.execution_lag_h.eq(1)].set_index(['comparison_id','period'])
    assert len(coeff)==243 and len(coins)==216 and len(models)==27
    assert coeff.groupby(['strategy_id','period']).size().eq(9).all()
    assert coins.groupby(['strategy_id','period']).size().eq(8).all()
    assert totals.bootstrap_invalid_draws.eq(0).all()
    for row in models.itertuples():
        n={'development':730,'validation':731,'oos_partial_2026_jan_sep':273}[row.period]
        assert row.n_calendar_days==n and row.n_parameters==9
        cal=calendar[(calendar.strategy_id==row.strategy_id)&(calendar.period==row.period)]
        assert len(cal)==n and cal.included_joint_regression.sum()==row.n_fit_days
        q=coins[(coins.strategy_id==row.strategy_id)&(coins.period==row.period)]
        np.testing.assert_allclose(q.net_linked_contribution.sum(),saved.loc[(row.strategy_id,row.period),'total_return'],rtol=3e-10,atol=3e-12)
        np.testing.assert_allclose(q.gross_linked_contribution-q.fees_linked_contribution,q.net_linked_contribution,rtol=3e-10,atol=3e-12)
    assert models.n_parameters.eq(9).all() and models['rank'].eq(9).all()
    return {'status':'passed_additional_fixed_nine_basket_attribution','created_at_utc':now(),
            'paths':27,'coin_rows':216,'joint_coefficient_slots':243,'joint_alpha_slots':27,'conditional_beta_slots':216,
            'all_original_frozen_strategies_and_financial_results_unchanged':True,
            'original_final_report_artifacts_unchanged':len(preservation['final_reports_20261015']['files']),
            'earlier_document_pins_unchanged':len(preservation['earlier_documents']),
            'all_saved_source_pins_unchanged':len(read('required_source_pins.json')['source_sha256']),
            'independent_accounting_and_inference_audits':'passed','no_invalid_bootstrap_draws':True,
            'chronology':'additional_diagnostic_freeze_precedes_additional_access_but_not_prior_result_knowledge',
            'new_strategy_selections':0,'strategy_reruns':0,'market_downloads':0,
            'classification':'post-hoc fixed-strategy explanatory research, not a fresh OOS test',
            'known_technical_amendment':'volatile stdout log intermediate hash only, no numerical changes'}

if __name__=='__main__':
    result=check()
    artifacts={}
    for p in ROOT.rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.log':continue
        rel=str(p.relative_to(ROOT))
        if rel in ['outputs/final_delivery_manifest.json','outputs/final_manifest_verification.json']:continue
        artifacts[rel]=sha(p)
    result['artifact_sha256']=artifacts
    destination=ROOT/'outputs/final_delivery_manifest.json'
    with destination.open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    for rel,digest in artifacts.items():pin(ROOT/rel,digest)
    save(ROOT/'outputs/final_manifest_verification.json',{'status':'passed','manifest_sha256':sha(destination),
          'owned_artifacts':len(artifacts),'all_numerical_outputs_and_original_preservation_verified':True})
    print(json.dumps({k:v for k,v in result.items() if k!='artifact_sha256'},indent=2))
