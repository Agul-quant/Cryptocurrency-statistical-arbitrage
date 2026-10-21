"""Reproduce unchanged frozen strategies from included, checksum-pinned inputs."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from . import strategies, simulator, metrics, metrics_extra, backtest
from .metrics_adapter import summarize_full


def read_json(path):
    return json.loads(Path(path).read_text())


def load_panel(root):
    root=Path(root)
    manifest=read_json(root/'data/manifest.json')
    # Verify every source before any decode; no downloading or gap filling.
    for name, record in manifest['files'].items():
        path=root/'data'/name
        if path.stat().st_size!=record['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Input checksum mismatch: '+name)
    panel={name:pd.read_parquet(root/'data'/f'{name}.parquet') for name in manifest['names']}
    panel['decision_allowed']=panel['decision_allowed']['allowed']
    prices=panel['prices'];index=prices.index
    if (str(index.tz)!='UTC' or index.has_duplicates or not index.is_monotonic_increasing
        or not index.equals(pd.date_range(manifest['first_endpoint'],manifest['last_endpoint'],freq='h'))):
        raise ValueError('Complete declared hourly UTC source grid required')
    for name,value in panel.items():
        if not value.index.equals(index):raise ValueError('Mismatched panel clock: '+name)
        if name!='decision_allowed' and not value.columns.equals(prices.columns):raise ValueError('Mismatched source columns')
        if name not in ('prices','quote_volume'):
            if value.isna().to_numpy().any() or (isinstance(value,pd.DataFrame) and not all(pd.api.types.is_bool_dtype(t) for t in value.dtypes)):
                raise ValueError('Unknown lifecycle/decision permission: '+name)
    if (panel['observed']&prices.isna()).any().any():raise ValueError('Missing price cannot be observed')
    return panel


def subset_panel(panel,symbols):
    result={}
    for name,value in panel.items():
        result[name]=(value.loc[:,symbols].copy() if isinstance(value,pd.DataFrame) else value.copy())
        result[name].attrs=dict(value.attrs)
    return result


def generate(panel,case):
    controls={name:panel[name] for name in ('tradable','observed','decision_allowed','mandatory_exit')}
    return strategies.generate_targets(panel['prices'],case,**controls)


def cost_result(base,cost):
    """Apply a one-way full-L1 fee to the unchanged zero-fee accounting path."""
    if isinstance(cost,bool) or cost not in (0,5,10,15,20,40):raise ValueError('Unsupported fee scenario')
    frame=base.frame.copy()
    frame['cost']=frame.turnover*float(cost)*1e-4
    frame['net_return']=frame.gross_return-frame.cost
    values=frame.net_return.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values<=-1).any():raise ValueError('Noncompoundable scenario')
    frame['equity']=np.cumprod(1+values)
    if not np.isfinite(frame.equity).all() or (frame.equity<=0).any():raise ValueError('Invalid compounded equity')
    frame['drawdown']=frame.equity/frame.equity.cummax().clip(lower=1)-1
    return backtest.BacktestResult(frame,base.held_weights)


def checked_output(root, output):
    """Reject output paths or existing descendants that use symlinks."""
    from .output_safety import checked_output_path
    return checked_output_path(root,output,directory=True)


def reconcile_primary(root, rows, wanted, periods):
    """Compare every shared numeric primary metric with the supplied fixed results."""
    actual=pd.DataFrame(rows)
    actual=actual.loc[actual.cost_bps.eq(20)&actual.execution_lag_h.eq(1)].copy()
    expected=pd.read_csv(Path(root)/'results/strategy_metrics.csv')
    expected=expected.loc[expected.comparison_id.isin(wanted)&expected.period.isin(periods)].copy()
    keys=['comparison_id','period']
    required={(sid,period)for sid in wanted for period in periods}
    for frame in (actual,expected):
        pairs=list(frame[keys].itertuples(index=False,name=None))
        if len(pairs)!=len(required) or set(pairs)!=required:
            raise ValueError('Primary metric strategy/period coverage mismatch')
    actual=actual.set_index(keys).sort_index();expected=expected.set_index(keys).sort_index()
    numeric=[c for c in expected.select_dtypes(include=['number','bool']).columns if c in actual.columns]
    if not numeric:raise ValueError('No primary numeric metrics available for reconciliation')
    maximum=0.
    for column in numeric:
        a=pd.to_numeric(actual[column],errors='raise').to_numpy(dtype=float)
        e=pd.to_numeric(expected[column],errors='raise').to_numpy(dtype=float)
        if not np.array_equal(np.isnan(a),np.isnan(e)):
            raise AssertionError('Primary metric missingness differs: '+column)
        np.testing.assert_allclose(a,e,rtol=1e-10,atol=1e-12,equal_nan=True,err_msg='Primary metric: '+column)
        valid=np.isfinite(a)&np.isfinite(e)
        if valid.any():maximum=max(maximum,float(np.max(np.abs(a[valid]-e[valid]))))
    return {'status':'PASS','strategy_period_rows':len(actual),'numeric_columns':len(numeric),
            'numeric_cells_checked':len(actual)*len(numeric),'maximum_absolute_error':maximum,
            'relative_tolerance':1e-10,'absolute_tolerance':1e-12,'paired_missing_values':True}


def evaluate(root,output,*,all_scenarios=False,ids=None,periods=None):
    root=Path(root).resolve();output=checked_output(root,output)
    output.mkdir(parents=True,exist_ok=True)
    panel=load_panel(root);registry=read_json(root/'configs/frozen_strategies.json');protocol=read_json(root/'configs/research_protocol.json')
    wanted=set(registry['order'] if ids is None else ids)
    if wanted-set(registry['order']):raise ValueError('Unknown frozen strategy')
    grid={c['experiment_id']:c for c in read_json(root/'configs/configuration_space.json')['cases']}
    for strategy in registry['strategies']:
        if strategy['case']!=grid.get(strategy['experiment_id']):raise ValueError('Frozen case does not match current definition space')
        if len(strategy['symbols'])!=8 or len(set(strategy['symbols']))!=8:raise ValueError('Fixed basket must contain eight distinct economic slots')
    selected_periods=list(protocol['periods'] if periods is None else periods)
    if set(selected_periods)-set(protocol['periods']):raise ValueError('Unknown fixed period')
    modules=(strategies,simulator,metrics,metrics_extra,backtest)
    rows=[];daily=[];path_manifest={}
    for strategy in registry['strategies']:
        sid=strategy['comparison_id']
        if sid not in wanted:continue
        sub=subset_panel(panel,strategy['symbols']);target=generate(sub,strategy['case'])
        benchmark=simulator.asset_returns(sub['prices'])['BTCUSDT']
        for period in selected_periods:
            start,end=protocol['periods'][period]
            for lag in ((1,2) if all_scenarios else (1,)):
                base=simulator.simulate(sub['prices'],target,start,end,0,lag,hold_allowed=sub['hold_allowed'],mandatory_exit=sub['mandatory_exit'])
                for cost in ((0,5,10,15,20,40) if all_scenarios and lag==1 else (20,)):
                    result=cost_result(base,cost)
                    values=summarize_full(result,strategy['case'],benchmark,modules)
                    row={'comparison_id':sid,'period':period,'execution_lag_h':lag,'cost_bps':cost,**values};rows.append(row)
                    if cost==20 and lag==1:
                        path=output/'paths'/f'{sid}__{period}.parquet';path.parent.mkdir(exist_ok=True)
                        result.frame.to_parquet(path)
                        path_manifest[str(path.relative_to(output))]=hashlib.sha256(path.read_bytes()).hexdigest()
                        d=metrics.daily_returns(result.frame.net_return)
                        for date,value in d.items():daily.append({'comparison_id':sid,'period':period,'date':date.isoformat(),'net_return':value})
                print(sid,period,'lag',lag,'complete',flush=True)
    reconciliation=reconcile_primary(root,rows,wanted,selected_periods)
    pd.DataFrame(rows).to_csv(output/'strategy_metrics.csv',index=False,float_format='%.17g')
    pd.DataFrame(daily).to_csv(output/'daily_returns.csv',index=False,float_format='%.17g')
    receipt={'status':'complete','strategy_count':len(wanted),'periods':selected_periods,'scenario_rows':len(rows),'new_price_acquisition':False,'selection_changes':False,'paths_sha256':path_manifest,'primary_metric_reconciliation':reconciliation}
    (output/'run_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return pd.DataFrame(rows)
