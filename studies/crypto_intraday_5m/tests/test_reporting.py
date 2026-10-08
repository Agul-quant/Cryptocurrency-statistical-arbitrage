"""Artifact-specific guards and accounting; no network or selection work."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from crypto_intraday_5m.reporting import fmt,label,load_outputs,plot_equity,reconcile_selected,selected_specs,historical_break_even


def test_missing_sharpe_not_presented_as_zero():
    assert fmt(np.nan)=='N/A'
    assert fmt(None)=='N/A'
    assert fmt(0)=='0.00'


def test_labels_preserve_minutes_family_and_cadence():
    assert label('momentum_l005_r060')=='Momentum L5m / R60m'
    assert label('reversal_l030_r015')=='Reversal L30m / R15m'
    assert label('momentum_m005_r060')=='Momentum L5m / R60m'
    assert label('reversal_m030_r015')=='Reversal L30m / R15m'


def test_requires_explicit_selected_list():
    assert selected_specs({'selected':[{'strategy_id':'reversal_l005_r060'}]})==[{'strategy_id':'reversal_l005_r060'}]
    with pytest.raises(ValueError,match='explicit selected'):selected_specs({})


def test_incomplete_run_is_not_reported(tmp_path):
    (tmp_path/'outputs').mkdir();(tmp_path/'outputs/run_manifest.json').write_text(json.dumps({'status':'running'}))
    with pytest.raises(ValueError,match='complete audited'):load_outputs(tmp_path)


def test_missing_receipt_hashes_fail_closed(tmp_path):
    (tmp_path/'outputs').mkdir();(tmp_path/'outputs/run_manifest.json').write_text(json.dumps({'status':'complete'}))
    with pytest.raises(ValueError,match='hash map'):load_outputs(tmp_path)


def test_log_plot_preserves_numerical_underflow_not_false_bankruptcy():
    g=pd.DataFrame({'strategy_id':['momentum_l005_r060']*2,'split':['retrospective_2026']*2,
                    'execution_lag':[1,1],'cost_bps':[20,20],
                    'bar_end':pd.to_datetime(['2026-01-01T00:05:00Z','2026-10-01T00:00:00Z']),
                    'equity':[1.,0.],'log_equity':[0.,-1000.]})
    fig=plot_equity(g);line=fig.axes[0].lines[0]
    assert line.get_ydata()[-1]==pytest.approx(-1000/np.log(10))
    assert np.isfinite(line.get_ydata()).all();plt.close(fig)


def _accounting_case(monkeypatch,bridge=False):
    import crypto_intraday_5m.data as data
    index=pd.date_range('2022-01-01',periods=289,freq='5min',tz='UTC')
    close=pd.DataFrame({symbol:100*np.exp(np.arange(289)*(.0001 if i<4 else -.0001))
                        for i,symbol in enumerate(['BTCUSDT','ETHUSDT','LTCUSDT','ADAUSDT','LINKUSDT','DOGEUSDT','DOTUSDT','SOLUSDT'])},index=index)
    close.attrs={'halt_bridges':[]}
    observed=close.copy()
    if bridge:
        begin=index[24];end=index[56]
        close.attrs['halt_bridges']=[{'start':begin.isoformat(),'end':end.isoformat()}]
        observed=observed.loc[~((observed.index>begin)&(observed.index<end))]
    monkeypatch.setattr(data,'load_panel',lambda root:(close,close.copy(),{}))
    asset=observed.pct_change().iloc[1:]
    held=pd.DataFrame(np.tile([.125]*4+[-.125]*4,(len(asset),1)),index=asset.index,columns=asset.columns)
    gross=(held*asset).sum(axis=1);turnover=np.zeros(len(asset));turnover[0]=1;turnover[-1]+=1
    net=gross.to_numpy()-turnover*.002;equity=np.cumprod(1+net);durations=np.diff(observed.index.asi8)/(60*1e9)
    ret=pd.DataFrame({'bar_end':asset.index,'strategy_id':'momentum_l005_r060','split':'development','execution_lag':1,'cost_bps':20,'gross_return':gross.to_numpy(),'net_return':net,'turnover':turnover,'cost':turnover*.002,'equity':equity,'log_equity':np.cumsum(np.log1p(net)),'interval_minutes':durations})
    weights=held.reset_index(names='bar_end');weights['strategy_id']='momentum_l005_r060';weights['split']='development';weights['execution_lag']=1
    # Use one complete day, with legitimate undefined sample SD/Sharpe.
    experiments=pd.DataFrame([{'strategy_id':'momentum_l005_r060','split':'development','cost_bps':20,'execution_lag':1,'annual_volatility':np.nan,'sharpe':np.nan}])
    return {'returns':ret,'weights':weights,'experiments':experiments}


@pytest.mark.parametrize('bridge',[False,True])
def test_independent_accounting_entry_liquidation_elapsed_bridge(monkeypatch,tmp_path,bridge):
    d=_accounting_case(monkeypatch,bridge)
    result=reconcile_selected(tmp_path,d)
    assert result.full_l1_turnover.iloc[0]==pytest.approx(2)
    assert result.daily_observations.iloc[0]==1
    assert result.observations.iloc[0]==(257 if bridge else 288)


def test_independent_accounting_rejects_cost_discrepancy(monkeypatch,tmp_path):
    d=_accounting_case(monkeypatch);d['returns'].loc[0,'cost']+=.001
    with pytest.raises(AssertionError):reconcile_selected(tmp_path,d)


def test_independent_accounting_rejects_missing_elapsed_minutes(monkeypatch,tmp_path):
    d=_accounting_case(monkeypatch,bridge=True);d['returns'].loc[d['returns'].interval_minutes.eq(160),'interval_minutes']=5
    with pytest.raises(AssertionError,match='1440'):reconcile_selected(tmp_path,d)


def test_posthoc_break_even_uses_gross_and_full_l1_not_selection():
    g=pd.DataFrame({'strategy_id':['reversal_m015_r060','momentum_m015_r060'],
                    'split':['retrospective_2026']*2,'execution_lag':[1,1],'cost_bps':[0,0],
                    'gross_return':[.0002,-.0002],'turnover':[1.,1.]})
    result=historical_break_even({'returns':g})
    assert result['reversal_m015_r060']['cost_bps']==pytest.approx(2.)
    assert result['momentum_m015_r060']['cost_bps'] is None
    assert abs(result['reversal_m015_r060']['residual_terminal_log_equity'])<1e-12
