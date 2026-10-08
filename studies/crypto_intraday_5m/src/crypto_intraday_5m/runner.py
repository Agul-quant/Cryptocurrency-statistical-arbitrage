"""Bounded exploratory pilot; selection uses2024 only, never2026 ranking."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .core import load_config,source_hashes,sha256_file,utc_now,versions,verify_preservation,write_json
from .data import load_panel
from .backtest import candidate_grid,generate_targets,observed_asset_returns,simulate,apply_costs
from .metrics import summarize,daily_returns


def _csv(path,frame):frame.to_csv(path,index=False,float_format='%.17g')


def select_strategies(table):
    eligible=table.loc[table.split.eq('validation')&table.cost_bps.eq(20)&table.execution_lag.eq(1)].copy()
    chosen=[]
    for family in ['momentum','reversal']:
        rows=eligible.loc[eligible.family.eq(family)].copy()
        rows=rows.loc[np.isfinite(pd.to_numeric(rows.sharpe,errors='coerce'))]
        if rows.empty:raise ValueError(f'No defined validation Sharpe for {family}.')
        row=rows.sort_values(['sharpe','mean_minute_turnover','strategy_id'],ascending=[False,True,True],kind='stable').iloc[0]
        chosen.append({'strategy_id':str(row.strategy_id),'family':family,
                       'lookback_minutes':int(row.lookback_minutes),'rebalance_minutes':int(row.rebalance_minutes),
                       'validation_sharpe':float(row.sharpe),'validation_total_return':float(row.total_return),
                       'validation_terminal_log_equity':float(row.terminal_log_equity),
                       'role':'champion' if row.sharpe>0 and row.total_return>0 else 'negative_control',
                       'label':f'{family.title()} {int(row.lookback_minutes)}m / rebalance {int(row.rebalance_minutes)}m'})
    return chosen


def _row(spec,split,cost,lag,result,gross,benchmark):
    stats=summarize(result,benchmark);gross_stats=summarize(gross,benchmark)
    held=result.held_weights;duration=result.frame.interval_minutes.astype(float)
    mean=lambda s:float((s*duration).sum()/duration.sum())
    return {**{k:spec[k] for k in ['strategy_id','family','lookback_minutes','rebalance_minutes']},
            'split':split,'cost_bps':float(cost),'execution_lag':lag,**stats,
            **{f'gross_{k}':gross_stats[k] for k in ['total_return','cagr','annual_return','annual_volatility','sharpe','max_drawdown','terminal_log_equity']},
            'mean_gross_exposure':mean(held.abs().sum(axis=1)),
            'mean_net_exposure':mean(held.sum(axis=1)),
            'fraction_flat':mean(held.abs().sum(axis=1).le(1e-12).astype(float)),
            'mean_daily_turnover':stats['total_turnover']/stats['n_days']}


def _frame(result,spec,split,cost,lag):
    df=result.frame.rename_axis('bar_end').reset_index()
    df['strategy_id']=spec['strategy_id'];df['split']=split;df['cost_bps']=float(cost);df['execution_lag']=lag
    return df


def _weights(result,spec,split,lag):
    df=result.held_weights.rename_axis('bar_end').reset_index()
    df['strategy_id']=spec['strategy_id'];df['split']=split;df['execution_lag']=lag
    return df


def _check_completed(root):
    root=Path(root);manifest=json.loads((root/'outputs/run_manifest.json').read_text())
    if manifest['analysis_source_sha256']!=source_hashes(root):raise RuntimeError('Completed analysis source/config differs; preserve results and use another experiment.')
    for relative,digest in manifest['analysis_output_sha256'].items():
        if sha256_file(root/relative)!=digest:raise RuntimeError(f'Completed output changed: {relative}')
    return manifest


def run_research(root):
    root=Path(root);o=root/'outputs';c=load_config(root)
    if (o/'run_manifest.json').exists() and json.loads((o/'run_manifest.json').read_text()).get('status')=='complete':
        return _check_completed(root)
    verify_preservation(root);started=utc_now();sources=source_hashes(root)
    prices,volume,audit=load_panel(root)
    if audit['status'] not in ['pass','pass_with_documented_exceptions']:raise RuntimeError('Data gate failed.')
    protocol=json.loads((o/'protocol.json').read_text());grid=candidate_grid()
    fields=['family','lookback_minutes','rebalance_minutes']
    if [{k:s[k] for k in fields} for s in grid]!=[{k:s[k] for k in fields} for s in protocol['candidate_grid']]:
        raise RuntimeError('Implemented candidate parameters differ from the predeclared18-case grid.')
    write_json(o/'protocol_alignment.json',{'verified_at_utc':utc_now(),'parameters_identical':True,
              'cosmetic_identifier_map':{old['strategy_id']:new['strategy_id'] for old,new in zip(protocol['candidate_grid'],grid)},
              'analysis_source_sha256':sources,'source_policy_locked_before_backtests':audit.get('source_policy_locked_at_utc')})
    periods=c['splits'];validation_end=pd.Timestamp(periods['validation']['end'],tz='UTC')
    early=prices.loc[prices.index<=validation_end].copy()
    early_returns=observed_asset_returns(early);early_benchmark=early_returns['BTCUSDT']
    scenarios=[(float(x),1) for x in c['research']['cost_scenarios_bps']]+[(20.,2)]
    rows=[]
    for number,spec in enumerate(grid,1):
        targets=generate_targets(early,spec['family'],spec['lookback_minutes'],spec['rebalance_minutes'])
        for split in ['development','validation']:
            w=periods[split]
            gross={lag:simulate(early,targets,w['start'],w['end'],0,lag,asset_returns=early_returns) for lag in [1,2]}
            for cost,lag in scenarios:
                result=gross[lag] if cost==0 else apply_costs(gross[lag],cost)
                rows.append(_row(spec,split,cost,lag,result,gross[lag],early_benchmark))
        print(f'Historical screening {number}/18: {spec["strategy_id"]}',flush=True)
    validation_table=pd.DataFrame(rows);_csv(o/'selection_evidence.csv',validation_table)
    chosen=select_strategies(validation_table)
    selection={'selected_at_utc':utc_now(),'selection_rule':c['research']['selection_rule'],'selected':chosen,
               'evaluated_strategies':chosen,'selection_period':'2024','selection_cost_bps':20,
               'retrospective_2025_or_2026_used_for_selection':False,
               'research_status':c['research']['research_status'],'all_periods_exploratory_retrospective':True,
               'selection_evidence_sha256':sha256_file(o/'selection_evidence.csv')}
    write_json(o/'selection.json',selection)
    full_returns=observed_asset_returns(prices);full_benchmark=full_returns['BTCUSDT']
    frames,weights=[] ,[]
    selected_ids={s['strategy_id'] for s in chosen}
    for number,spec in enumerate(grid,1):
        targets=generate_targets(prices,spec['family'],spec['lookback_minutes'],spec['rebalance_minutes'])
        for split,w in periods.items():
            if split not in ['retrospective','retrospective_2026'] and spec['strategy_id'] not in selected_ids:continue
            gross={lag:simulate(prices,targets,w['start'],w['end'],0,lag,asset_returns=full_returns) for lag in [1,2]}
            for cost,lag in scenarios:
                result=gross[lag] if cost==0 else apply_costs(gross[lag],cost)
                if split in ['retrospective','retrospective_2026']:
                    rows.append(_row(spec,split,cost,lag,result,gross[lag],full_benchmark))
                if spec['strategy_id'] in selected_ids and ((lag==1 and cost in [0,20]) or split=='retrospective_2026'):
                    frames.append(_frame(result,spec,split,cost,lag))
            if spec['strategy_id'] in selected_ids:
                for lag in ([1,2] if split=='retrospective_2026' else [1]):weights.append(_weights(gross[lag],spec,split,lag))
        print(f'Retrospective evaluation {number}/18: {spec["strategy_id"]}',flush=True)
    experiments=pd.DataFrame(rows)
    if len(experiments)!=504 or experiments.duplicated(['strategy_id','split','cost_bps','execution_lag']).any():
        raise RuntimeError('Expected exactly504 unique configuration-period-scenario measurements.')
    _csv(o/'experiments.csv',experiments)
    selected_metrics=experiments.loc[experiments.strategy_id.isin(selected_ids)].copy()
    _csv(o/'selected_metrics.csv',selected_metrics)
    pd.concat(frames,ignore_index=True).to_parquet(o/'selected_returns.parquet',index=False)
    pd.concat(weights,ignore_index=True).to_parquet(o/'selected_weights.parquet',index=False)
    if sources!=source_hashes(root):raise RuntimeError('Analysis source changed during execution; do not accept mixed-source outputs.')
    protected=verify_preservation(root)
    output_paths=['outputs/protocol.json','outputs/protocol_alignment.json','outputs/selection.json','outputs/selection_evidence.csv',
                  'outputs/experiments.csv','outputs/selected_metrics.csv','outputs/selected_returns.parquet','outputs/selected_weights.parquet',
                  'data/processed/bars.parquet','data/processed/data_quality.json','outputs/data_hourly_reconciliation.json',
                  'outputs/data_warmup_source_discrepancy_investigation.json']
    manifest={'status':'complete','started_at_utc':started,'completed_at_utc':utc_now(),'analysis_source_sha256':sources,
              'analysis_output_sha256':{p:sha256_file(root/p) for p in output_paths},
              'protocol_sha256':sha256_file(o/'protocol.json'),'selection_sha256':sha256_file(o/'selection.json'),
              'data_parquet_sha256':sha256_file(root/'data/processed/bars.parquet'),'data_quality':audit,
              'candidate_count':18,'metric_rows':504,'selected_models':2,'scenarios':scenarios,'splits':periods,
              'research_status':c['research']['research_status'],'all_periods_exploratory_retrospective':True,
              'selection_uses2024_only':True,'preservation':protected,'environment':versions(),
              'cost_semantics':'Full one-way L1 target changes incl entry/liquidation; ordinary weight drift excluded.',
              'lag_semantics':'lag1 completed-bar signal earns next5m interval under idealized close fill; lag2 adds5m.',
              'source_attribution':'Binance Vision; CC BY-NC-SA4.0; non-commercial educational research.',
              'source_documentation':'https://github.com/binance/binance-public-data',
              'terms_url':'https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md',
              'limitations':['Fixed survivor universe, theoretical shorts, no borrow/funding/margin/capacity model.',
                             'OHLCV does not establish bid/ask spreads, executable close prices or limit fills.',
                             'Lower bar interval does not reduce the20bps course cost assumption.',
                             '2026 already inspected at coarser frequency; no pristine independent holdout.',
                             'Monthly5m warmup differs from daily/hourly source at3closes/134volume sums, allbeforeDec28; retained unchanged.',
                             'Numeric wealth can underflow for extreme high-cost paths; log wealth remains finite, no epsilon clipping or false insolvency.',
                             'Cross-frequency candle agreement does not imply identical portfolio compounding at different target-weight observation frequencies.']}
    write_json(o/'run_manifest.json',manifest)
    return manifest


def verify_results(root):
    root=Path(root);m=_check_completed(root);prices,_,_=load_panel(root)
    asset=observed_asset_returns(prices)
    frames=pd.read_parquet(root/'outputs/selected_returns.parquet');held=pd.read_parquet(root/'outputs/selected_weights.parquet')
    metrics=pd.read_csv(root/'outputs/selected_metrics.csv');checks=[]
    for (sid,split,cost,lag),part in frames.groupby(['strategy_id','split','cost_bps','execution_lag']):
        f=part.set_index('bar_end').sort_index();w=held.loc[held.strategy_id.eq(sid)&held.split.eq(split)&held.execution_lag.eq(lag)].set_index('bar_end').sort_index()[prices.columns]
        pd.testing.assert_index_equal(w.index,f.index)
        gross=(w*asset.reindex(w.index)).sum(axis=1).to_numpy()
        changes=np.diff(w.to_numpy(),axis=0,prepend=np.zeros((1,8)))
        turnover=np.abs(changes).sum(axis=1);turnover[-1]+=np.abs(w.iloc[-1]).sum()
        net=gross-cost*1e-4*turnover;log=np.log1p(net).cumsum()
        for col,value in [('gross_return',gross),('turnover',turnover),('cost',cost*1e-4*turnover),('net_return',net),('log_equity',log)]:
            np.testing.assert_allclose(f[col],value,atol=1e-10,rtol=1e-12)
        with np.errstate(under='ignore'):eq=np.exp(log)
        np.testing.assert_allclose(f.equity,eq,atol=1e-13,rtol=1e-10)
        s=pd.Series(net,index=f.index);s.attrs={'interval_minutes':{t.isoformat():int(v) for t,v in f.interval_minutes.items() if v!=5}}
        daily=daily_returns(s)
        row=metrics.loc[metrics.strategy_id.eq(sid)&metrics.split.eq(split)&metrics.cost_bps.eq(cost)&metrics.execution_lag.eq(lag)].iloc[0]
        np.testing.assert_allclose(row.annual_return,daily.mean()*365,atol=1e-10)
        np.testing.assert_allclose(row.annual_volatility,daily.std(ddof=1)*np.sqrt(365),atol=1e-10)
        if daily.std(ddof=1)>1e-15:np.testing.assert_allclose(row.sharpe,daily.mean()/daily.std(ddof=1)*np.sqrt(365),atol=1e-10)
        checks.append({'strategy_id':sid,'split':split,'cost_bps':float(cost),'execution_lag':int(lag),'independent_accounting_daily_metrics':True})
    receipt={'verified_at_utc':utc_now(),'scenario_checks':checks,'source_outputs_locked':True,
             'all_periods_exploratory_retrospective':True,'preservation':verify_preservation(root)}
    write_json(root/'outputs/result_verification.json',receipt);return receipt
