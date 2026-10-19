"""Synthetic accounting, allocation, scheduling and causality checks."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from crypto_research import strategies as s,simulator as sim,backtest
from crypto_research.runner import cost_result,load_panel,subset_panel
ROOT=Path(__file__).resolve().parents[1]

def fixture(n=800):
    idx=pd.date_range('2022-01-01',periods=n,freq='h',tz='UTC')
    x=np.arange(n)[:,None];j=np.arange(8)[None,:]
    return pd.DataFrame(100*np.exp((j-3.5)*x/10000+0.02*np.sin(x/13+j)),index=idx,columns=['BTCUSDT','ETHUSDT']+[f'C{i}USDT' for i in range(6)])

def case(family='momentum',cadence=24,buffer=0):
    return {'family':family,'lookback_h':24,'rebalance_h':cadence,'buffer_l1':buffer,'phase_hours':0,'grid_id':'time_scale'}

@pytest.mark.parametrize('family',['momentum','reversal','cross_momentum','trend_long_cash','trend_long_short'])
def test_future_price_prefix_invariance(family):
    p=fixture();a=s.generate_targets(p,case(family));q=p.copy();q.iloc[500:]*=50
    b=s.generate_targets(q,case(family));pd.testing.assert_frame_equal(a.iloc[:500],b.iloc[:500])

@pytest.mark.parametrize('family',['momentum','reversal','cross_momentum'])
def test_neutral_rank_gross_budget(family):
    t=s.generate_targets(fixture(),case(family))
    np.testing.assert_allclose(t.sum(axis=1),0,atol=1e-14)
    assert t.abs().sum(axis=1).max()<=1+1e-14

@pytest.mark.parametrize('family',['trend_long_cash','trend_long_short'])
def test_fixed_eighth_allocations(family):
    t=s.generate_targets(fixture(),case(family))
    assert set(np.round(t.to_numpy().ravel(),12)).issubset({-.125,0.,.125})
    assert t.abs().sum(axis=1).max()<=1
    if family=='trend_long_cash':assert (t>=0).all().all()

def test_weekly_is_monday_midnight():
    p=fixture(1000);t=s.generate_targets(p,case(cadence=168));changes=t.diff().abs().sum(axis=1)>0
    dates=t.index[changes];assert len(dates)>3
    assert (dates.dayofweek==0).all() and (dates.hour==0).all()

def test_whole_target_buffer():
    p=fixture();plain=s.generate_targets(p,case());buffered=s.generate_targets(p,case(buffer=.25))
    before=np.zeros(8)
    for i,row in enumerate(buffered.to_numpy()):
        target=plain.iloc[i].to_numpy();distance=np.abs(target-before).sum()
        if i and i%24==0 and distance<.25-1e-12:np.testing.assert_array_equal(row,before)
        if np.abs(row-before).sum()>1e-12:np.testing.assert_array_equal(row,target)
        before=row

def test_equal_scores_cash():
    p=fixture();p[:]=100
    t=s.generate_targets(p,case());assert np.count_nonzero(t.to_numpy())==0

def test_full_l1_entry_liquidation_and_nav():
    p=fixture(100);target=pd.DataFrame(.125,index=p.index,columns=p.columns)
    base=sim.simulate(p,target,p.index[0],p.index[-1],0,1)
    paid=cost_result(base,20)
    assert paid.frame.turnover.iloc[0]==pytest.approx(1)
    assert paid.frame.turnover.iloc[-1]==pytest.approx(1)
    assert paid.frame.turnover.sum()==pytest.approx(2)
    np.testing.assert_allclose(paid.frame.cost,.002*paid.frame.turnover,atol=0,rtol=0)
    np.testing.assert_allclose(paid.frame.net_return,paid.frame.gross_return-paid.frame.cost)
    np.testing.assert_allclose(paid.frame.equity,np.cumprod(1+paid.frame.net_return))

def test_inactive_slot_stays_cash():
    p=fixture();active=pd.DataFrame(True,index=p.index,columns=p.columns);active.iloc[:,0]=False
    t=s.generate_targets(p,case('trend_long_cash'),active)
    assert (t.iloc[:,0]==0).all();assert (t.abs().sum(axis=1)<=7/8).all()

def test_frozen_grid_and_periods():
    cases=s.candidate_grid();assert len(cases)==169
    assert len({x['experiment_id'] for x in cases})==169
    p=json.loads((ROOT/'configs/research_protocol.json').read_text())
    assert p['periods']['development'][1]==p['periods']['validation'][0]
    assert p['periods']['validation'][1]==p['periods']['oos_partial_2026_jan_sep'][0]
    assert p['periods']['oos_partial_2026_jan_sep'][1]=='2026-10-01T00:00:00Z'

def test_complete_pinned_inputs_and_subsets():
    panel=load_panel(ROOT);reg=json.loads((ROOT/'configs/frozen_strategies.json').read_text())
    assert len(reg['strategies'])==9 and panel['prices'].shape==(43824,21)
    for x in reg['strategies']:
        sub=subset_panel(panel,x['symbols']);assert sub['prices'].shape[1]==8
        assert sub['prices'].attrs==panel['prices'].attrs
        assert sub['decision_allowed'].equals(panel['decision_allowed'])


@pytest.mark.parametrize('where',['results','data','.', '../outside'])
def test_output_rejects_saved_or_external_locations(tmp_path,where):
    from crypto_research.runner import checked_output
    root=tmp_path/'package';root.mkdir()
    with pytest.raises(ValueError):checked_output(root,root/where)


def test_output_rejects_symlink_escape(tmp_path):
    from crypto_research.runner import checked_output
    root=tmp_path/'package';root.mkdir();outside=tmp_path/'external';outside.mkdir()
    (root/'local_outputs').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):checked_output(root,root/'local_outputs'/'run')


def test_output_accepts_private_subdirectory(tmp_path):
    from crypto_research.runner import checked_output
    root=tmp_path/'package';root.mkdir()
    assert checked_output(root,root/'local_outputs'/'run')==root/'local_outputs'/'run'


def test_primary_reconciliation_detects_changed_metric(tmp_path):
    from crypto_research.runner import reconcile_primary
    root=tmp_path/'package';(root/'results').mkdir(parents=True)
    rows=[{'comparison_id':'A03','period':'validation','cost_bps':20,'execution_lag_h':1,'total_return':-.2,'undefined_metric':float('nan')}]
    pd.DataFrame(rows).to_csv(root/'results/strategy_metrics.csv',index=False)
    result=reconcile_primary(root,rows,{'A03'},['validation'])
    assert result['numeric_cells_checked']==4 and result['maximum_absolute_error']==0
    changed=[dict(rows[0],total_return=.1)]
    with pytest.raises(AssertionError):reconcile_primary(root,changed,{'A03'},['validation'])


@pytest.mark.parametrize('kind',['metrics_file','paths_directory'])
def test_output_rejects_symlink_descendants(tmp_path,kind):
    from crypto_research.runner import checked_output
    root=tmp_path/'package';root.mkdir()
    output=root/'local_outputs'/'run';output.mkdir(parents=True)
    if kind=='metrics_file':
        target=root/'README.md';target.write_text('protected')
        (output/'strategy_metrics.csv').symlink_to(target)
    else:
        target=root/'results';target.mkdir()
        (output/'paths').symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError):checked_output(root,output)
    if kind=='metrics_file':assert target.read_text()=='protected'


def test_diagnostic_output_rejects_target_symlink(tmp_path):
    from crypto_research.output_safety import checked_output_path
    root=tmp_path/'package';root.mkdir()
    protected=root/'results.json';protected.write_text('protected')
    output=root/'local_outputs';output.mkdir()
    (output/'diagnostic.json').symlink_to(protected)
    with pytest.raises(ValueError):checked_output_path(root,output/'diagnostic.json')
    assert protected.read_text()=='protected'
