#!/usr/bin/env python3
"""Reconcile the published fixed-study evidence; no prices, trades or bootstrap rerun."""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path

PERIODS=('development','validation','oos_partial_2026_jan_sep')
DAYS=(730,731,273)
SCENARIOS={(p,l,c)for p in PERIODS for l,c in [(1,c)for c in (0,5,10,15,20,40)]+[(2,20)]}
REPORTS=('01_development','02_validation','03_2026_evaluation')

def read(path):return json.loads(path.read_text())
def rows(path):
    with path.open(newline='')as f:return list(csv.DictReader(f))
def close(a,b):assert math.isclose(float(a),float(b),rel_tol=2e-12,abs_tol=2e-13),(a,b)
def holm3(values):
    assert len(values)==3 and all(0<=p<=1 for p in values)
    order=sorted(range(3),key=lambda i:values[i]);answer=[0.]*3;previous=0.
    for rank,i in enumerate(order):
        previous=max(previous,min(1.,(3-rank)*values[i]));answer[i]=previous
    return answer

def verify(root):
    primary_by_study={};count=0;output_copies=0
    for study in ('momentum','reversal'):
        d=root/'results'/('fixed_all22_'+study);primary=rows(d/'primary_summary.csv');scenarios=rows(d/'scenario_metrics.csv');inference=read(d/'primary_inference.json');flags=read(d/'classification.json')
        assert len(primary)==len(inference)==3
        assert [r['period']for r in primary]==[r['period']for r in inference]==list(PERIODS)
        assert len(scenarios)==21 and {(r['period'],int(r['execution_lag_h']),int(r['cost_bps']))for r in scenarios}==SCENARIOS
        assert all(r['status']=='evaluated'for r in scenarios)
        assert all(r['strategy_id']==study+'_h0672_r168'for r in primary+scenarios)
        pvalues=[r['primary_test']['holm3_input_p']for r in inference]
        adjusted=holm3(pvalues)
        for r,i,n,a in zip(primary,inference,DAYS,adjusted):
            assert int(r['n_calendar_days'])==n and int(r['n_hours'])==24*n
            scenario=next(x for x in scenarios if x['period']==r['period']and x['cost_bps']=='20'and x['execution_lag_h']=='1')
            for field in ('total_return','wealth_relative_excess_return','sharpe','cash_excess_sharpe','max_drawdown','annualized_full_l1_turnover'):close(r[field],scenario[field])
            for field in ('sharpe','gross_sharpe','cash_excess_sharpe'):close(r[field+'252'],float(r[field])*math.sqrt(252/365))
            close(r['wealth_relative_excess_return'],math.expm1(math.log1p(float(r['total_return']))-n*math.log1p(.03/365)))
            close(i['primary_test']['holm3_adjusted_p'],a)
            assert i['primary_test']['available'] and i['primary_test']['holm3_input_p']==i['primary_test']['centered_bootstrap_t_one_sided_p']
            expected=i['mean_cash_excess']['hac27_t']>0 and a<=.05
            assert i['statistical_period_pass']==expected
            count+=1
        assert flags['economic_all3_above_cash']==all(float(r['wealth_relative_excess_return'])>0 for r in primary)
        assert flags['risk_all3_hourly_dd_le_40pct']==all(float(r['max_drawdown'])<=.4 for r in primary)
        assert flags['statistical_all3_holm3_cash_mean']==all(r['statistical_period_pass']for r in inference)
        assert flags['deployment_authorized'] is False and flags['independent_unseen_confirmation'] is False
        assert flags['combined_conditional_pass'] is False
        primary_by_study[study]=primary
        for report in REPORTS:
            for name in ('primary_summary','scenario_metrics','primary_inference'):
                source=d/(name+'.csv');copy=root/'final_reports'/report/'exports'/f'fixed_all22_{study}_{name}.csv'
                assert copy.read_bytes()==source.read_bytes(),str(copy)
                output_copies+=1
    for report in REPORTS:
        snapshot=read(root/'final_reports'/report/'reviewed_snapshot.json')
        app=read(root/'final_reports'/report/'app/src/data.json')
        assert snapshot==app
        published=snapshot['queries']['fixed_all22_primary']['rows']
        assert len(published)==6
        assert [(r['study'],r['period'])for r in published]==[(s,p)for s in ('momentum','reversal')for p in PERIODS]
        for r in published:
            source=next(x for x in primary_by_study[r['study']]if x['period']==r['period'])
            for field in ('gross_total_return','total_return','wealth_relative_excess_return','sharpe','sharpe252','cash_excess_sharpe','cash_excess_sharpe252','max_drawdown','annualized_full_l1_turnover','cagr','annual_volatility'):close(r[field],source[field])
        for method in snapshot['queries']['fixed_all22_methods']['rows']:
            study=method['study'];flags=read(root/'results'/('fixed_all22_'+study)/'classification.json')
            expected=flags.get('strict_pre_panel_access_compliance',flags.get('strict_pre_panel_freeze_compliance'))
            assert method['strict_pre_panel_access_compliance'] is expected
            assert method['output_destination_is_publication_projection'] is True
            assert method['configuration']['output_destination']=='results/fixed_all22_'+study
        assert snapshot['buildStatus']=='complete'and snapshot['report']['asOf']=='2026-09-30'
    return {'status':'PASS','separate_studies':2,'primary_rows':count,'scenario_period_keys':42,'report_primary_rows_checked':18,'exact_companion_copies':output_copies,'pvalue_families':'two separate Holm3 families; never pooled','source_prices_loaded':False,'strategy_or_bootstrap_rerun':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=p.parse_args();print(json.dumps(verify(args.root.resolve()),indent=2,sort_keys=True))
