"""Real-cache independent arithmetic regressions; no fitting or network."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from crypto_intraday_5m.core import DEFAULT_ROOT,verify_preservation
from crypto_intraday_5m.data import load_panel
from crypto_intraday_5m.runner import _check_completed,select_strategies

READY=(DEFAULT_ROOT/'outputs/run_manifest.json').exists()
pytestmark=pytest.mark.skipif(not READY,reason='Completed cached pilot required')


@pytest.fixture(scope='module')
def cache():
    r=DEFAULT_ROOT;_check_completed(r);p,_,a=load_panel(r)
    asset=p.div(p.shift(1))-1
    retain=np.ones(len(p),dtype=bool);retain[0]=False
    for b in p.attrs['halt_bridges']:
        start,end=pd.Timestamp(b['start']),pd.Timestamp(b['end'])
        retain &= ~((p.index>start)&(p.index<end))
        asset.loc[end]=p.loc[end]/p.loc[start]-1
    return r,p,a,asset.loc[retain],pd.read_parquet(r/'outputs/selected_returns.parquet'),pd.read_parquet(r/'outputs/selected_weights.parquet')


@pytest.mark.parametrize('sid',['momentum_m015_r060','reversal_m015_r060'])
@pytest.mark.parametrize('split,cost,lag',[(s,c,1) for s in ['development','validation','retrospective'] for c in [0,20]]+ [('retrospective_2026',c,1) for c in [0,5,10,15,20,40]]+[('retrospective_2026',20,2)])
def test_saved_scenario_raw_price_reconstruction(cache,sid,split,cost,lag):
    r,p,a,asset,f,w=cache
    f=f.loc[f.strategy_id.eq(sid)&f.split.eq(split)&f.cost_bps.eq(cost)&f.execution_lag.eq(lag)].set_index('bar_end').sort_index()
    w=w.loc[w.strategy_id.eq(sid)&w.split.eq(split)&w.execution_lag.eq(lag)].set_index('bar_end').sort_index()[p.columns]
    assert f.index.equals(w.index)
    gross=(w*asset.reindex(w.index)).sum(axis=1).to_numpy()
    change=np.diff(w.to_numpy(),axis=0,prepend=np.zeros((1,8)))
    turn=np.abs(change).sum(axis=1);turn[-1]+=np.abs(w.iloc[-1]).sum()
    net=gross-turn*cost*1e-4;log=np.log1p(net).cumsum()
    for key,x in [('gross_return',gross),('turnover',turn),('net_return',net),('log_equity',log)]:
        np.testing.assert_allclose(f[key],x,atol=1e-10,rtol=1e-12)
    if split=='retrospective_2026':assert len(f)==78624 and f.interval_minutes.sum()==393120
    if split=='development':assert len(f)==210209 and f.interval_minutes.sum()==1051200
    days=(f.index-pd.Timedelta('1ns')).floor('D')
    assert f.interval_minutes.groupby(days).sum().eq(1440).all()
    daily=pd.Series(1+net,index=days).groupby(level=0).prod()-1
    m=pd.read_csv(r/'outputs/selected_metrics.csv')
    row=m.loc[m.strategy_id.eq(sid)&m.split.eq(split)&m.cost_bps.eq(cost)&m.execution_lag.eq(lag)].iloc[0]
    np.testing.assert_allclose(row.annual_return,daily.mean()*365,atol=1e-10)
    np.testing.assert_allclose(row.annual_volatility,daily.std(ddof=1)*np.sqrt(365),atol=1e-10)
    np.testing.assert_allclose(row.sharpe,daily.mean()/daily.std(ddof=1)*np.sqrt(365),atol=1e-10)


def test_all_cases_retained_and_selection_2024_only(cache):
    r,*_=cache;d=pd.read_csv(r/'outputs/experiments.csv')
    assert len(d)==504 and not d.duplicated(['strategy_id','split','cost_bps','execution_lag']).any()
    assert d.groupby(['split','cost_bps','execution_lag']).size().eq(18).all()
    selected=json.loads((r/'outputs/selection.json').read_text())
    for actual,saved in zip(select_strategies(d),selected['selected']):
        for key,value in actual.items():
            if key.startswith('validation_'):
                np.testing.assert_allclose(value,saved[key],rtol=1e-12,atol=1e-12)
            else:assert value==saved[key]
    assert selected['all_periods_exploratory_retrospective'] is True
    assert selected['retrospective_2025_or_2026_used_for_selection'] is False


def test_halt_no_interior_marks_and_complete_durations(cache):
    r,p,a,asset,f,w=cache
    assert p.isna().sum().sum()==128
    assert len(p)==508320 and a['duplicate_count']==0 and a['implicit_fill'] is False
    start,end=pd.Timestamp('2023-03-24 11:25',tz='UTC'),pd.Timestamp('2023-03-24 14:05',tz='UTC')
    assert not ((f.bar_end>start)&(f.bar_end<end)).any()
    assert f.loc[f.bar_end.eq(end),'interval_minutes'].eq(160).all()


def test_real_underflow_is_not_bar_insolvency(cache):
    r,*_=cache;d=pd.read_csv(r/'outputs/experiments.csv');under=d.loc[d.equity_underflow_count.gt(0)]
    assert len(under)==2
    assert set(under.split)=={'development'} and set(under.cost_bps)=={40}
    assert np.isfinite(under.terminal_log_equity).all()
    assert under.terminal_log_equity.lt(-745).all() and under.total_return.eq(-1).all()


def test_old_projects_and_bundles_preserved(cache):
    r,*_=cache;old=verify_preservation(r)
    assert sorted(x['file_count'] for x in old.values())==[868,1878]
    assert all(x['status']=='unchanged' and x['bundle_unchanged'] for x in old.values())
