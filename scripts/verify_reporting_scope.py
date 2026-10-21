#!/usr/bin/env python3
"""Check current168-definition scope and saved aggregates without rerunning research."""
from pathlib import Path
import argparse,csv,hashlib,json,math,re

def read(p):return json.loads(p.read_text())
def rows(p):
 with p.open(newline='')as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(root):
 meta=read(root/'metadata/reporting_scope.json');grid=read(root/'configs/configuration_space.json');registry=read(root/'configs/frozen_strategies.json')
 assert grid['unique_case_count']==len(grid['cases'])==meta['reporting_configurations']==168
 assert grid['family_counts']==meta['families']and sum(meta['families'].values())==168
 assert len({x['experiment_id']for x in grid['cases']})==168
 assert {x['report_family']for x in grid['cases']}==set(meta['families'])
 assert meta['baskets']*168==meta['primary_pairs_per_period']==1111320
 assert 7*1111320==meta['scenario_keys_per_full_grid_period']==7779240
 assert meta['amended_after_evaluation']and not meta['frozen_nine_reselected']and not meta['historical_development_groups_reranked']
 assert len(registry['strategies'])==9
 pin=hashlib.sha256(json.dumps(registry['strategies'],sort_keys=True,separators=(',',':')).encode()).hexdigest();assert pin==meta['frozen_nine_strategy_definitions_sha256']
 for rel,pin in meta['protected_financial_files'].items():assert(root/rel).stat().st_size==pin['bytes']and sha(root/rel)==pin['sha256'],rel
 reports={'development':'01_development','validation':'02_validation','oos':'03_2026_evaluation'}
 for period,folder in reports.items():
  snapshot=read(root/'final_reports'/folder/'reviewed_snapshot.json');assert snapshot==read(root/'final_reports'/folder/'app/src/data.json')and snapshot['buildStatus']=='complete'
  htmls=list((root/'final_reports'/folder).glob('*.html'));assert len(htmls)==1
  snapshot_pin=re.search(r'<meta name="data-app-snapshot-sha256" content="([0-9a-f]{64})">',htmls[0].read_text());assert snapshot_pin and snapshot_pin.group(1)==sha(root/'final_reports'/folder/'reviewed_snapshot.json'),folder
  for f in(root/'results/retained_scope'/period).glob('*.csv'):
   qid=f.stem
   if qid not in snapshot['queries']:continue
   saved=rows(f);published=snapshot['queries'][qid]['rows'];assert len(saved)==len(published),(folder,qid)
   for a,b in zip(saved,published):
    for key,value in a.items():
     actual=b.get(key)
     if actual is None:assert value==''
     elif isinstance(actual,bool):assert value==str(actual)
     elif isinstance(actual,(int,float)):assert math.isclose(float(value),actual,rel_tol=1e-12,abs_tol=1e-12),(folder,qid,key)
     else:assert value==str(actual),(folder,qid,key)
 coverage=read(root/'final_reports/01_development/reviewed_snapshot.json')['queries']['coverage']['rows'][0]
 assert coverage['configurations']==168 and coverage['primaryPairs']==1111320 and coverage['scenarioKeys']==7779240 and coverage['undefinedSharpe']==0
 q=read(root/'final_reports/03_2026_evaluation/reviewed_snapshot.json')['queries'];cohort={x['Cohort']:x for x in q['cohort']['rows']}
 assert cohort['Broad survivors']['Pairs']==69108 and cohort['Strict both-positive']['Pairs']==39332 and cohort['Controls']['Pairs']==154404
 assert meta['retained_Q1_pairs']==69108+154404==223512
 assert math.isclose(cohort['Controls']['Profitable'],42045/154404,abs_tol=1e-14)
 assert len(q['family']['rows'])==10 and len(q['screening']['rows'])==4 and len(q['regime_tests']['rows'])==4
 assert not any(x['Reject 5%']for x in q['screening']['rows'])
 unavailable=next(x for x in q['regime_tests']['rows']if x['Regime']=='BTC trailing volatility');assert unavailable['Invalid draws']==29 and unavailable['Centered p']is None and unavailable['Holm-4 p']is None
 return {'status':'PASS','configurations':168,'primary_pairs_per_period':1111320,'retained_Q1_pairs':223512,'controls':154404,'protected_financial_files':len(meta['protected_financial_files']),'new_selection_or_strategy_execution':False}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args();print(json.dumps(verify(a.root.resolve()),indent=2,sort_keys=True))
