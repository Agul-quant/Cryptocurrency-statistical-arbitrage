#!/usr/bin/env python3
"""Reconcile saved fixed-study performance; no price loading or statistical rerun."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path

PERIODS=('development','validation','oos_partial_2026_jan_sep')
DAYS=(730,731,273)
SCENARIOS={(p,l,c)for p in PERIODS for l,c in [(1,c)for c in (0,5,10,15,20,40)]+[(2,20)]}
REPORTS=('01_development','02_validation','03_2026_evaluation')
POINT_FIELDS=('gross_total_return','total_return','sharpe','sharpe252','gross_sharpe','gross_sharpe252','max_drawdown','annualized_full_l1_turnover','cagr','annual_volatility','btc_alpha_annual','btc_beta','btc_alpha_ci_low','btc_alpha_ci_high','btc_beta_ci_low','btc_beta_ci_high')

def read(path):return json.loads(path.read_text())
def rows(path):
    with path.open(newline='')as f:return list(csv.DictReader(f))
def close(a,b):assert math.isclose(float(a),float(b),rel_tol=2e-12,abs_tol=2e-13),(a,b)
def flatten(obj,prefix=''):
    out={}
    for key,value in obj.items():
        name=prefix+key
        if isinstance(value,dict):out.update(flatten(value,name+'.'))
        else:out[name]=value
    return out

def verify(root):
    primary_by_study={};inference_by_study={};scenario_by_study={};count=0;copies=0;numeric_checks=0
    for study in ('momentum','reversal'):
        d=root/'results'/('fixed_all22_'+study)
        primary=rows(d/'primary_summary.csv');scenarios=rows(d/'scenario_metrics.csv');inference=read(d/'primary_inference.json');csv_inference=rows(d/'primary_inference.csv');methods=read(d/'methods.json')
        assert len(primary)==len(inference)==len(csv_inference)==3
        assert [r['period']for r in primary]==[r['period']for r in inference]==list(PERIODS)
        assert len(scenarios)==21 and {(r['period'],int(r['execution_lag_h']),int(r['cost_bps']))for r in scenarios}==SCENARIOS
        assert all(r['status']=='evaluated'for r in scenarios)
        assert all(r['strategy_id']==study+'_h0672_r168'for r in primary+scenarios)
        cfg=methods['configuration']
        assert cfg['case']['family']==study and cfg['case']['lookback_h']==672 and cfg['case']['rebalance_h']==168
        assert cfg['case']['buffer_l1']==cfg['case']['phase_hours']==0
        assert len(cfg['symbols'])==len(set(cfg['symbols']))==22
        assert cfg['annual_days']==365 and cfg['companion_sharpe_days']==252
        assert cfg['primary']=={'cost_bps':20,'execution_lag_h':1}
        assert cfg['output_destination']=='results/fixed_all22_'+study
        assert methods['chronology']['strict_pre_panel_access_compliance']is(study=='reversal')
        for r,i,flat,n in zip(primary,inference,csv_inference,DAYS):
            assert int(r['n_calendar_days'])==i['n_calendar_days']==n and int(r['n_hours'])==24*n
            assert set(i)=={'period','n_calendar_days','first_utc_day','last_utc_day','performance','raw_mean_descriptive','intervals95','methods'}
            assert set(i['intervals95'])=={'raw_sharpe365','raw_sharpe252'}
            scenario=next(x for x in scenarios if x['period']==r['period']and x['cost_bps']=='20'and x['execution_lag_h']=='1')
            for field in POINT_FIELDS:close(r[field],scenario[field]);numeric_checks+=1
            for field in ('sharpe','gross_sharpe'):close(r[field+'252'],float(r[field])*math.sqrt(252/365));numeric_checks+=1
            close(i['performance']['raw_net_return'],r['total_return']);close(i['performance']['raw_cagr'],r['cagr'])
            for scale in (365,252):
                close(i['performance']['raw_sharpe'+str(scale)],r['sharpe'+('252'if scale==252 else'')]);numeric_checks+=1
            for endpoint in ('low','high'):
                close(i['intervals95']['raw_sharpe252'][endpoint],i['intervals95']['raw_sharpe365'][endpoint]*math.sqrt(252/365));numeric_checks+=1
            rawmean=i['raw_mean_descriptive'];mean=rawmean.get('daily_mean',rawmean.get('mean'));close(rawmean['hac27_t'],mean/rawmean['hac27_se']);numeric_checks+=1
            for key,value in flatten(i).items():
                if isinstance(value,(int,float))and not isinstance(value,bool):close(flat[key],value);numeric_checks+=1
                elif isinstance(value,bool):assert flat[key]==str(value)
                else:assert flat[key]==str(value)
            count+=1
        primary_by_study[study]=primary;inference_by_study[study]=inference;scenario_by_study[study]=scenarios
        for report in REPORTS:
            for name in ('primary_summary','scenario_metrics','primary_inference'):
                source=d/(name+'.csv');copy=root/'final_reports'/report/'exports'/f'fixed_all22_{study}_{name}.csv'
                assert copy.read_bytes()==source.read_bytes(),str(copy)
                copies+=1
    for report in REPORTS:
        snapshot=read(root/'final_reports'/report/'reviewed_snapshot.json');app=read(root/'final_reports'/report/'app/src/data.json')
        assert snapshot==app
        published=snapshot['queries']['fixed_all22_primary']['rows']
        assert len(published)==6
        assert [(r['study'],r['period'])for r in published]==[(s,p)for s in ('momentum','reversal')for p in PERIODS]
        for r in published:
            source=next(x for x in primary_by_study[r['study']]if x['period']==r['period'])
            for field in POINT_FIELDS:close(r[field],source[field]);numeric_checks+=1
        published_inference=snapshot['queries']['fixed_all22_inference']['rows'];assert len(published_inference)==6
        for r in published_inference:
            source=next(x for x in inference_by_study[r['study']]if x['period']==r['period'])
            for field,value in flatten(source).items():
                if isinstance(value,(int,float))and not isinstance(value,bool):close(r[field],value);numeric_checks+=1
        published_scenarios=snapshot['queries']['fixed_all22_scenarios']['rows'];assert len(published_scenarios)==42
        for r in published_scenarios:
            source=next(x for x in scenario_by_study[r['study']]if x['period']==r['period']and float(x['execution_lag_h'])==r['execution_lag_h']and float(x['cost_bps'])==r['cost_bps'])
            for field in POINT_FIELDS:close(r[field],source[field]);numeric_checks+=1
        for method in snapshot['queries']['fixed_all22_methods']['rows']:
            study=method['study'];source=read(root/'results'/('fixed_all22_'+study)/'methods.json')
            assert method['strict_pre_panel_access_compliance']is source['chronology']['strict_pre_panel_access_compliance']
            assert method['configuration']==source['configuration']
        assert snapshot['buildStatus']=='complete'and snapshot['report']['asOf']=='2026-09-30'
    return {'status':'PASS','separate_studies':2,'primary_rows':count,'scenario_period_keys':42,'report_primary_rows_checked':18,'exact_companion_copies':copies,'numeric_reconciliation_checks':numeric_checks,'uncertainty_scope':'saved descriptive means and marginal raw Sharpe intervals','source_prices_loaded':False,'strategy_or_statistical_rerun':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=p.parse_args();print(json.dumps(verify(args.root.resolve()),indent=2,sort_keys=True))
