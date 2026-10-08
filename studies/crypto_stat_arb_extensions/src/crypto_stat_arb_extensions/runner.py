"""Chronological extension pipeline with an irreversible pre-access freeze."""
from __future__ import annotations
import json
import shutil
from pathlib import Path
import numpy as np
import pandas as pd

from crypto_stat_arb.backtest import generate_targets as original_targets, observed_asset_returns, simulate
from crypto_stat_arb.metrics import summarize, daily_returns
from .core import (load_config, sha256_file, source_hashes, utc_now, verify_baseline,
                   verify_freeze, versions, write_json)
from .data import (prepare_holdout, load_history, load_full_panel, history_root, full_root)


def _csv(path, frame):
    frame.to_csv(path,index=False,float_format='%.17g')


def _historical_splits(config):
    return {k:v for k,v in config['splits'].items() if k!='holdout'}


def _label(spec):
    family=spec['family']; h=spec['lookback_h']; r=spec['rebalance_h']
    if family=='factor_residual':return 'BTC-factor residual reversal'
    horizon=f'{h//24}d' if h>=24 and h%24==0 else f'{h}h'
    cadence='weekly' if r==168 else 'daily' if r==24 else f'{r}h'
    name={'cross_momentum':'Cross momentum','trend_long_cash':'Trend long/cash',
          'trend_long_short':'Trend long/short','momentum':'Momentum','reversal':'Reversal'}[family]
    prefix={'original_reference':'Original ', 'time_scale_reference':'Scale-scan '}.get(spec.get('role'),'')
    buffer=f"; buffer {spec['buffer_l1']:g}" if spec.get('buffer_l1',0)>0 else ''
    return f'{prefix}{name} ({horizon}; {cadence}{buffer})'


def select_champions(metrics):
    """Select solely on the fixed 2024/20 bps criterion, including negative controls."""
    candidates=metrics.loc[metrics['split'].eq('validation') & metrics['cost_bps'].eq(20)
                           & metrics['execution_lag'].eq(1)].copy()
    selected=[]
    for family in ['cross_momentum','trend_long_cash','trend_long_short']:
        rows=candidates.loc[candidates.family.eq(family)].copy()
        rows=rows.loc[np.isfinite(pd.to_numeric(rows.sharpe,errors='coerce'))]
        if rows.empty:
            raise ValueError(f'No defined validation Sharpe for tuned family {family}; do not invent a champion.')
        best=rows.sort_values(['sharpe','mean_hourly_turnover','strategy_id'],
                             ascending=[False,True,True],kind='stable').iloc[0]
        selected.append({
            'strategy_id':str(best.strategy_id),'family':family,'lookback_h':int(best.lookback_h),
            'rebalance_h':int(best.rebalance_h),'buffer_l1':float(best.buffer_l1),
            'role':'champion','validation_sharpe':float(best.sharpe),
            'validation_total_return':float(best.total_return),
            'positive_net_validation':bool(best.sharpe>0 and best.total_return>0),
        })
    return selected


def _reference_specs(root):
    root=Path(root);reference=root/'reference_receipts';reference.mkdir(exist_ok=True)
    preservation=json.loads((root/'outputs/baseline_preservation.json').read_text())
    baseline=Path(preservation['baseline_root'])
    sources={'original_selection.json':baseline/'outputs/selection.json',
             'time_scale_selection.json':baseline/'outputs/followups/time_scale_scan/selection.json'}
    for name,p in sources.items():
        target=reference/name
        if not target.exists():shutil.copy2(p,target)
        elif p.exists() and sha256_file(p)!=sha256_file(target):
            raise RuntimeError('Reference selection receipt differs from the preserved original.')
    originals=json.loads((reference/'original_selection.json').read_text())['selected']
    scales=json.loads((reference/'time_scale_selection.json').read_text())['net_selected']
    specs=[]
    for role,chosen,prefix in [('original_reference',originals,'reference_original'),
                               ('time_scale_reference',scales,'reference_scale')]:
        for selected in chosen:
            spec={k:selected[k] for k in ['family','lookback_h','rebalance_h']}
            spec.update(strategy_id=f'{prefix}_{spec["family"]}',buffer_l1=0.0,role=role,
                        original_strategy_id=selected.get('strategy_id',selected.get('experiment_id')))
            spec['label']=_label(spec);specs.append(spec)
    return specs


def _make_target(prices,spec,factor):
    from .strategies import generate_targets
    from .core import get_scaled_generator
    if spec['family']=='factor_residual':return factor.targets
    if spec.get('role')=='original_reference':
        return original_targets(prices,spec['family'],spec['lookback_h'],spec['rebalance_h'])
    if spec.get('role')=='time_scale_reference':
        return get_scaled_generator()(prices,spec['family'],spec['lookback_h'],spec['rebalance_h'])
    return generate_targets(prices,spec)


def _summary(result,gross,spec,split,cost,lag,benchmark):
    net_stats=summarize(result,benchmark);gross_stats=summarize(gross,benchmark)
    weights=result.held_weights;gross_exposure=weights.abs().sum(axis=1);net_exposure=weights.sum(axis=1)
    long_exposure=weights.clip(lower=0).sum(axis=1);short_exposure=-weights.clip(upper=0).sum(axis=1)
    durations=result.frame.interval_hours.astype(float)
    weighted_mean=lambda series:float((series*durations).sum()/durations.sum())
    return {**{k:spec[k] for k in ['strategy_id','family','lookback_h','rebalance_h','buffer_l1']},
            'role':spec.get('role','candidate'),'label':spec.get('label',_label(spec)),
            'split':split,'cost_bps':float(cost),'execution_lag':int(lag),**net_stats,
            **{f'gross_{k}':gross_stats[k] for k in ['total_return','cagr','annual_return','annual_volatility','sharpe','max_drawdown']},
            'mean_gross_exposure':weighted_mean(gross_exposure),'mean_net_exposure':weighted_mean(net_exposure),
            'mean_long_exposure':weighted_mean(long_exposure),'mean_short_exposure':weighted_mean(short_exposure),
            'fraction_flat':weighted_mean(gross_exposure.le(1e-12).astype(float)),
            'mean_unused_gross_budget':weighted_mean((1-gross_exposure).clip(lower=0)),
            'mean_cash_allocation':weighted_mean((1-long_exposure).clip(lower=0)) if spec['family']=='trend_long_cash' else None,
            'maximum_gross_exposure':float(gross_exposure.max()),
            'minimum_net_exposure':float(net_exposure.min()),'maximum_net_exposure':float(net_exposure.max())}


def _returns(result,spec,split,cost,lag):
    frame=result.frame.rename_axis('bar_end').reset_index()
    for name,value in [('strategy_id',spec['strategy_id']),('split',split),('cost_bps',float(cost)),('execution_lag',int(lag))]:
        frame[name]=value
    return frame


def _weights(result,spec,split,lag):
    frame=result.held_weights.rename_axis('bar_end').reset_index()
    frame['strategy_id']=spec['strategy_id'];frame['split']=split;frame['execution_lag']=lag
    return frame


def _diagnostic_kwargs(config):
    d=config['diagnostics']
    return {'n_bootstrap':d['bootstrap_replicates'],'block_days':d['bootstrap_block_days'],'seed':d['bootstrap_seed']}


def screen_history(root):
    root=Path(root);output=root/'outputs';config=load_config(root)
    if (output/'freeze_receipt.json').exists():
        verify_freeze(root)
        return json.loads((output/'screen_receipt.json').read_text())
    verify_baseline(root);started=utc_now();initial_hashes=source_hashes(root)
    from .strategies import candidate_grid, generate_factor_targets, FACTOR_PARAMETERS
    from .diagnostics import signal_ic,regime_features,fit_regime_thresholds,regime_diagnostics
    if config['factor']!=FACTOR_PARAMETERS:
        raise ValueError('Factor configuration differs from the implemented predeclared model.')
    grid=candidate_grid()
    if len(grid)!=17:raise ValueError('The study must retain the 17 bounded candidates.')
    grid_receipt={'declared_at_utc':utc_now(),'candidates':grid,'candidate_count':17,
                  'existing_plain_controls':4,'new_formulations':13,
                  'historical_status':'Exploratory; 2025 previously inspected.',
                  'analysis_source_sha256':initial_hashes}
    write_json(output/'candidate_grid.json',grid_receipt)
    prices,volume,audit=load_history(root);splits=_historical_splits(config)
    benchmark=observed_asset_returns(prices)['BTCUSDT']
    factor=generate_factor_targets(prices)
    history_cutoff=pd.Timestamp(config['data']['history_end'],tz='UTC')
    _csv(output/'history_factor_models.csv',factor.models.loc[factor.models.refit_time<history_cutoff])
    _csv(output/'history_factor_events.csv',factor.events.loc[factor.events.decision_time<history_cutoff])
    targets={spec['strategy_id']:_make_target(prices,spec,factor) for spec in grid}
    rows=[]
    for number,spec in enumerate(grid,1):
        for split,window in splits.items():
            gross=simulate(prices,targets[spec['strategy_id']],window['start'],window['end'],0,1)
            net=simulate(prices,targets[spec['strategy_id']],window['start'],window['end'],20,1)
            rows.append(_summary(net,gross,spec,split,20,1,benchmark))
        print(f'Historical candidates {number:02d}/17: {spec["strategy_id"]}',flush=True)
    metrics=pd.DataFrame(rows);_csv(output/'historical_metrics.csv',metrics)
    champions=select_champions(metrics)
    fixed={**next(s for s in grid if s['family']=='factor_residual'),'role':'fixed_model'}
    evaluated=champions+[fixed]+_reference_specs(root)
    for spec in evaluated:spec['label']=_label(spec)
    if len(evaluated)!=8 or len({s['strategy_id'] for s in evaluated})!=8:
        raise ValueError('The holdout must contain eight uniquely identified frozen models.')
    features=regime_features(prices,volume)
    thresholds=fit_regime_thresholds(features,config['splits']['development']['start'],config['splits']['development']['end'])
    write_json(output/'regime_thresholds.json',thresholds)
    features.rename_axis('decision_date').reset_index().to_parquet(output/'history_regime_features.parquet',index=False)
    ic_daily,ic_summary=signal_ic(prices,splits,lookbacks=config['diagnostics']['ic_lookbacks_hours'],
                                forward_horizons=config['diagnostics']['ic_forward_hours'],**_diagnostic_kwargs(config))
    _csv(output/'history_ic_daily.csv',ic_daily);_csv(output/'history_ic_summary.csv',ic_summary)
    selected_rows,frames,weights,annual=[] ,[],[],[]
    for spec in evaluated:
        sid=spec['strategy_id']
        if sid not in targets:targets[sid]=_make_target(prices,spec,factor)
        target=targets[sid]
        for split,window in splits.items():
            gross=simulate(prices,target,window['start'],window['end'],0,1)
            net=simulate(prices,target,window['start'],window['end'],20,1)
            selected_rows.append(_summary(net,gross,spec,split,20,1,benchmark))
            frames.extend([_returns(gross,spec,split,0,1),_returns(net,spec,split,20,1)])
            weights.append(_weights(net,spec,split,1))
        for year in range(2022,2026):
            begin=f'{year}-01-01';finish=f'{year+1}-01-01'
            gross=simulate(prices,target,begin,finish,0,1)
            net=simulate(prices,target,begin,finish,20,1)
            annual.append({**_summary(net,gross,spec,str(year),20,1,benchmark),'year':year,'reset_from_cash':True})
    _csv(output/'historical_selected_metrics.csv',pd.DataFrame(selected_rows))
    _csv(output/'annual_metrics.csv',pd.DataFrame(annual))
    return_frames=pd.concat(frames,ignore_index=True)
    return_frames.to_parquet(output/'history_selected_returns.parquet',index=False)
    pd.concat(weights,ignore_index=True).to_parquet(output/'history_selected_weights.parquet',index=False)
    primary=return_frames.loc[return_frames.cost_bps.eq(20)&return_frames.execution_lag.eq(1)]
    observations,regimes=regime_diagnostics(primary,features,thresholds,splits,**_diagnostic_kwargs(config))
    _csv(output/'history_regime_observations.csv',observations);_csv(output/'history_regime_summary.csv',regimes)
    selection={'selected_at_utc':utc_now(),'selection_rule':config['research']['selection_rule'],
               'selection_period':'2024','selection_cost_bps':20,'champions':champions,
               'evaluated_strategies':evaluated,'retrospective_2025_used_for_selection':False,
               '2026_prices_accessed':False,'regimes_control_trading':False,
               'candidate_count':17,'validation_evidence_sha256':sha256_file(output/'historical_metrics.csv')}
    write_json(output/'selection.json',selection)
    if source_hashes(root)!=initial_hashes:
        raise RuntimeError('Analysis sources changed during historical screening; rerun before freezing.')
    receipt={'started_at_utc':started,'completed_at_utc':utc_now(),'status':'screened_not_frozen',
             'analysis_source_sha256':initial_hashes,'history_data_sha256':sha256_file(history_root(root)/'data/processed/bars.parquet'),
             'candidate_rows':len(metrics),'selection_sha256':sha256_file(output/'selection.json'),
             'history_data_quality':audit,'environment':versions(),'baseline_preservation':verify_baseline(root)}
    write_json(output/'screen_receipt.json',receipt)
    write_json(output/'run_manifest.json',{**receipt,'stage':'screened','2026_prices_accessed':False})
    print('Historical screening complete; no 2026 prices accessed.',flush=True)
    return receipt


def freeze_study(root):
    root=Path(root);output=root/'outputs'
    if (output/'freeze_receipt.json').exists():return verify_freeze(root)
    screen=json.loads((output/'screen_receipt.json').read_text())
    if screen['analysis_source_sha256']!=source_hashes(root):
        raise RuntimeError('Historical screening source hashes are stale.')
    tests=json.loads((output/'pre_holdout_tests.json').read_text())
    if tests['analysis_source_sha256']!=source_hashes(root) or tests['exit_code']!=0:
        raise RuntimeError('Current analysis source must pass pre-holdout tests before freeze.')
    if not tests.get('original_tests_passed') or not tests.get('time_scale_tests_passed'):
        raise RuntimeError('Existing project and time-scale tests must also pass.')
    if (output/'holdout_access_receipt.json').exists() or list((full_root(root)/'data/raw').rglob('*2026*.zip')):
        raise RuntimeError('Holdout access already exists before first freeze.')
    selection=json.loads((output/'selection.json').read_text())
    for spec in select_champions(pd.read_csv(output/'historical_metrics.csv')):
        existing=next(s for s in selection['champions'] if s['family']==spec['family'])
        for key,value in spec.items():
            if key in ['validation_sharpe','validation_total_return']:
                if not np.isclose(existing[key],value,rtol=1e-12,atol=1e-12):
                    raise RuntimeError('Selection receipt differs from validation-only recomputation.')
            elif existing[key]!=value:
                raise RuntimeError('Selection receipt differs from validation-only recomputation.')
    evidence=['outputs/baseline_preservation.json','outputs/candidate_grid.json','outputs/selection.json',
              'outputs/regime_thresholds.json','outputs/historical_metrics.csv','outputs/historical_selected_metrics.csv',
              'outputs/annual_metrics.csv','outputs/history_factor_models.csv','outputs/history_factor_events.csv',
              'outputs/history_ic_daily.csv','outputs/history_ic_summary.csv','outputs/history_selected_returns.parquet',
              'outputs/history_selected_weights.parquet','outputs/history_regime_observations.csv',
              'outputs/history_regime_summary.csv','outputs/history_data_receipt.json','outputs/screen_receipt.json',
              'outputs/pre_holdout_tests.json','datasets/history/data/processed/bars.parquet',
              'datasets/history/data/processed/data_quality.json','reference_receipts/original_selection.json',
              'reference_receipts/time_scale_selection.json']
    evidence += [str(p.relative_to(root)) for p in sorted((history_root(root)/'data/raw').rglob('*')) if p.is_file()]
    sources=source_hashes(root)
    freeze={'frozen_at_utc':utc_now(),'analysis_source_sha256':sources,'analysis_hashes':sources,
            'frozen_evidence_sha256':{relative:sha256_file(root/relative) for relative in evidence},
            'selection_sha256':sha256_file(output/'selection.json'),'protocol':load_config(root),
            'holdout_price_access_before_freeze':False,'baseline_preservation':verify_baseline(root),
            'holdout_label':'New-to-analysis historical holdout; January–September 2026, not prospective live trading.'}
    write_json(output/'freeze_receipt.json',freeze)
    print('Study frozen before holdout price acquisition:',freeze['frozen_at_utc'],flush=True)
    return freeze


def _merge_csv(root,name,historical,extra):
    old=pd.read_csv(Path(root)/'outputs'/historical)
    _csv(Path(root)/'outputs'/name,pd.concat([old,extra],ignore_index=True))


def evaluate_holdout(root):
    root=Path(root);output=root/'outputs';freeze=verify_freeze(root);config=load_config(root)
    status_path=output/'holdout_status.json'
    if status_path.exists() and json.loads(status_path.read_text()).get('status')=='complete':
        manifest=json.loads((output/'run_manifest.json').read_text())
        for relative,digest in manifest['analysis_output_sha256'].items():
            if sha256_file(root/relative)!=digest:raise RuntimeError(f'Completed holdout output modified: {relative}')
        print('Completed frozen holdout reused; no new evaluation or reselection.',flush=True)
        return manifest
    prepare_holdout(root)
    write_json(status_path,{'status':'evaluating','evaluation_started_at_utc':utc_now(),'parameter_reselection':False})
    started=utc_now();prices,volume,audit=load_full_panel(root)
    selection=json.loads((output/'selection.json').read_text());evaluated=selection['evaluated_strategies']
    from .strategies import generate_factor_targets
    from .diagnostics import signal_ic,regime_features,regime_diagnostics
    factor=generate_factor_targets(prices);benchmark=observed_asset_returns(prices)['BTCUSDT']
    split=config['splits']['holdout'];scenarios=[(c,1) for c in config['research']['cost_scenarios_bps']]+[(20,2)]
    rows,frames,weights=[],[],[]
    for number,spec in enumerate(evaluated,1):
        target=_make_target(prices,spec,factor)
        gross_by_lag={lag:simulate(prices,target,split['start'],split['end'],0,lag) for lag in [1,2]}
        for cost,lag in scenarios:
            gross=gross_by_lag[lag]
            result=gross if cost==0 else simulate(prices,target,split['start'],split['end'],cost,lag)
            rows.append(_summary(result,gross,spec,'holdout',cost,lag,benchmark))
            frames.append(_returns(result,spec,'holdout',cost,lag))
        for lag in [1,2]:weights.append(_weights(gross_by_lag[lag],spec,'holdout',lag))
        print(f'Frozen holdout {number}/8: {spec["strategy_id"]}',flush=True)
    holdout_metrics=pd.DataFrame(rows);_csv(output/'holdout_metrics.csv',holdout_metrics)
    holdout_returns=pd.concat(frames,ignore_index=True)
    pd.concat([pd.read_parquet(output/'history_selected_returns.parquet'),holdout_returns],ignore_index=True).to_parquet(output/'selected_returns.parquet',index=False)
    pd.concat([pd.read_parquet(output/'history_selected_weights.parquet'),pd.concat(weights,ignore_index=True)],ignore_index=True).to_parquet(output/'selected_weights.parquet',index=False)
    _merge_csv(root,'factor_models.csv','history_factor_models.csv',factor.models.loc[factor.models.refit_time>=pd.Timestamp(split['start'],tz='UTC')])
    _merge_csv(root,'factor_events.csv','history_factor_events.csv',factor.events.loc[factor.events.decision_time>=pd.Timestamp(split['start'],tz='UTC')])
    holdout_splits={'holdout':split}
    ic_daily,ic_summary=signal_ic(prices,holdout_splits,lookbacks=config['diagnostics']['ic_lookbacks_hours'],
                                forward_horizons=config['diagnostics']['ic_forward_hours'],**_diagnostic_kwargs(config))
    _merge_csv(root,'ic_daily.csv','history_ic_daily.csv',ic_daily);_merge_csv(root,'ic_summary.csv','history_ic_summary.csv',ic_summary)
    features=regime_features(prices,volume)
    features.rename_axis('decision_date').reset_index().to_parquet(output/'regime_features.parquet',index=False)
    thresholds=json.loads((output/'regime_thresholds.json').read_text())
    primary=holdout_returns.loc[holdout_returns.cost_bps.eq(20)&holdout_returns.execution_lag.eq(1)]
    observations,regimes=regime_diagnostics(primary,features,thresholds,holdout_splits,**_diagnostic_kwargs(config))
    _merge_csv(root,'regime_observations.csv','history_regime_observations.csv',observations)
    _merge_csv(root,'regime_summary.csv','history_regime_summary.csv',regimes)
    verify_freeze(root);preservation=verify_baseline(root)
    completed=utc_now();access=json.loads((output/'holdout_access_receipt.json').read_text())
    paths=['outputs/holdout_metrics.csv','outputs/selected_returns.parquet','outputs/selected_weights.parquet',
           'outputs/factor_models.csv','outputs/factor_events.csv','outputs/ic_daily.csv','outputs/ic_summary.csv',
           'outputs/regime_features.parquet','outputs/regime_observations.csv','outputs/regime_summary.csv',
           'outputs/holdout_access_receipt.json','datasets/full/data/processed/bars.parquet']
    manifest={'status':'complete','started_at_utc':started,'completed_at_utc':completed,
              'freeze_timestamp_utc':freeze['frozen_at_utc'],'freeze_receipt_sha256':sha256_file(output/'freeze_receipt.json'),
              'selection_sha256':freeze['selection_sha256'],'first_holdout_access_utc':access['first_access_utc'],
              'analysis_source_sha256':freeze['analysis_source_sha256'],
              'analysis_output_sha256':{p:sha256_file(root/p) for p in paths},
              'candidate_count':17,'evaluated_models':8,'holdout_metric_rows':len(rows),
              'holdout_period':split,'holdout_calendar_days':273,'holdout_elapsed_hours':6552,
              'history_data_quality':json.loads((history_root(root)/'data/processed/data_quality.json').read_text()),
              'holdout_data_quality':audit,'environment':versions(),'baseline_preservation':preservation,
              'parameter_reselection_after_holdout':False,'regime_filters_trade':False,
              'source_documentation':'https://github.com/binance/binance-public-data',
              'terms_url':'https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md',
              'source_attribution':'Binance Vision (data.binance.vision); CC BY-NC-SA 4.0; non-commercial educational research',
              'limitations':['Fixed purposive survivor universe, not a point-in-time market universe.',
                             'USDT returns are not identical to USD returns.',
                             'Shorts are theoretical; borrow, funding, margin, capacity and liquidation excluded.',
                             'Course target-weight turnover ignores ordinary weight drift.',
                             'Idealized close execution; cost scenarios do not establish achievable fills.',
                             'Historical archives may contain later revisions; retrieval is not proof of original timestamp availability.',
                             '2022–2025 extensions exploratory; new-to-analysis 2026 holdout is historical, not prospective.',
                             'Nine-month holdout has limited precision; selecting among historical candidates creates optimism.',
                             'No eligible factor spread/all-cash is a valid research outcome.']}
    write_json(output/'run_manifest.json',manifest)
    write_json(status_path,{'status':'complete','evaluation_started_at_utc':started,
                           'evaluation_completed_at_utc':completed,'parameter_reselection':False,
                           'freeze_receipt_sha256':manifest['freeze_receipt_sha256']})
    print('Nine-month frozen holdout evaluation complete.',flush=True)
    return manifest


def verify_results(root):
    """Independent arithmetic checks from saved holdings and observed prices."""
    root=Path(root);freeze=verify_freeze(root);prices,_,_=load_full_panel(root)
    manifest=json.loads((root/'outputs/run_manifest.json').read_text())
    for relative,digest in manifest['analysis_output_sha256'].items():
        if sha256_file(root/relative)!=digest:raise RuntimeError(f'Output SHA mismatch: {relative}')
    returns=pd.read_parquet(root/'outputs/selected_returns.parquet')
    holdings=pd.read_parquet(root/'outputs/selected_weights.parquet')
    returns=returns.loc[returns.split.eq('holdout')];holdings=holdings.loc[holdings.split.eq('holdout')]
    assets=observed_asset_returns(prices);checks=[]
    for (sid,cost,lag),rows in returns.groupby(['strategy_id','cost_bps','execution_lag']):
        rows=rows.set_index('bar_end').sort_index()
        held=holdings.loc[holdings.strategy_id.eq(sid)&holdings.execution_lag.eq(lag)].set_index('bar_end').sort_index()[prices.columns]
        pd.testing.assert_index_equal(rows.index,held.index)
        if len(rows)!=6552 or int(rows.interval_hours.sum())!=6552:
            raise AssertionError('Holdout must cover all 6552 elapsed hours.')
        gross=(held*assets.reindex(held.index)).sum(axis=1)
        change=held.diff();change.iloc[0]=held.iloc[0]
        turnover=change.abs().sum(axis=1);turnover.iloc[-1]+=held.iloc[-1].abs().sum()
        net=gross-turnover*cost*1e-4;equity=(1+net).cumprod()
        np.testing.assert_allclose(rows.gross_return,gross,atol=1e-14,rtol=0)
        np.testing.assert_allclose(rows.turnover,turnover,atol=1e-14,rtol=0)
        np.testing.assert_allclose(rows.net_return,net,atol=1e-14,rtol=0)
        np.testing.assert_allclose(rows.equity,equity,atol=1e-13,rtol=1e-12)
        if len(daily_returns(net))!=273:raise AssertionError('Partial or missing holdout daily intervals.')
        checks.append({'strategy_id':sid,'cost_bps':cost,'execution_lag':int(lag),
                       'held_pnl_turnover_cost_equity_reconciled':True})
    access=json.loads((root/'outputs/holdout_access_receipt.json').read_text())
    if pd.Timestamp(freeze['frozen_at_utc'])>=pd.Timestamp(access['first_access_utc']):
        raise AssertionError('Holdout access preceded freeze.')
    receipt={'verified_at_utc':utc_now(),'holdout_scenario_checks':checks,
             'baseline_preservation':verify_baseline(root),'freeze_chronology_verified':True,
             'original_code_and_selection_unchanged':True,'verification_status':'ready_with_disclosed_research_limitations'}
    write_json(root/'outputs/result_verification.json',receipt)
    return receipt
