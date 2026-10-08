"""Chronology and preservation gates; synthetic tests never access 2026 data."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from crypto_stat_arb_extensions import core, data, runner
from crypto_stat_arb_extensions.strategies import candidate_grid, FACTOR_PARAMETERS


def table():
    rows=[]
    for spec in candidate_grid():
        for split in ['development','validation','retrospective','holdout']:
            rows.append({**spec,'split':split,'cost_bps':20,'execution_lag':1,
                         'sharpe':-.5,'mean_hourly_turnover':.01,'total_return':-.1})
    return pd.DataFrame(rows)


def test_grid_config_and_factor_agree():
    c=core.load_config()
    assert c['factor']==FACTOR_PARAMETERS
    assert len(candidate_grid())==17
    assert c['splits']['holdout']=={'start':'2026-01-01','end':'2026-10-01'}
    assert (pd.Timestamp(c['splits']['holdout']['end'])-pd.Timestamp(c['splits']['holdout']['start'])).days==273


def test_selection_ignores_2025_and_holdout():
    t=table();before=runner.select_champions(t)
    t.loc[t.split.isin(['retrospective','holdout']),'sharpe']=np.arange(t.split.isin(['retrospective','holdout']).sum())*1e6
    assert runner.select_champions(t)==before
    assert all(not s['positive_net_validation'] for s in before)


def test_selection_uses_twenty_bps_only():
    t=table();fake=t.loc[t.split.eq('validation')].copy();fake['cost_bps']=0;fake['sharpe']=1000
    assert runner.select_champions(pd.concat([t,fake]))==runner.select_champions(t)


def test_selection_ties_turnover_then_id():
    t=table()
    sid='cross_momentum_h672_r168_b025'
    t.loc[t.strategy_id.eq(sid)&t.split.eq('validation'),'mean_hourly_turnover']=.001
    chosen=runner.select_champions(t)
    assert chosen[0]['strategy_id']==sid
    family=t.loc[t.family.eq('trend_long_cash')&t.split.eq('validation')]
    assert chosen[1]['strategy_id']==sorted(family.strategy_id)[0]


def test_undefined_family_sharpe_not_invented():
    t=table();t.loc[t.family.eq('trend_long_cash'),'sharpe']=np.nan
    with pytest.raises(ValueError,match='No defined validation Sharpe'):runner.select_champions(t)


def test_holdout_download_blocked_before_freeze(tmp_path,monkeypatch):
    called=[]
    monkeypatch.setattr(data,'download_and_prepare',lambda *a:called.append(a))
    with pytest.raises(RuntimeError,match='No freeze receipt'):data.prepare_holdout(tmp_path)
    assert called==[]


def test_full_loader_blocked_before_freeze(tmp_path,monkeypatch):
    called=[]
    monkeypatch.setattr(data,'load_panel',lambda *a:called.append(a))
    with pytest.raises(RuntimeError,match='No freeze receipt'):data.load_full_panel(tmp_path)
    assert called==[]


def test_history_loader_refuses_future_panel(monkeypatch,tmp_path):
    audit=tmp_path/'datasets/history/data/processed/data_quality.json';audit.parent.mkdir(parents=True)
    audit.write_text(json.dumps({'end_open_time_exclusive':'2026-01-01T00:00:00+00:00'}))
    prices=pd.DataFrame({'BTCUSDT':[1]},index=pd.DatetimeIndex(['2026-01-01 01:00'],tz='UTC'))
    monkeypatch.setattr(data,'load_panel',lambda *a:(prices,prices,{}))
    with pytest.raises(RuntimeError,match='containing 2026'):data.load_history(tmp_path)


def test_history_future_declaration_rejected_without_price_read(monkeypatch,tmp_path):
    audit=tmp_path/'datasets/history/data/processed/data_quality.json';audit.parent.mkdir(parents=True)
    audit.write_text(json.dumps({'end_open_time_exclusive':'2026-10-01T00:00:00+00:00'}))
    called=[];monkeypatch.setattr(data,'load_panel',lambda *a:called.append(a))
    with pytest.raises(RuntimeError,match='before reading prices'):data.load_history(tmp_path)
    assert not called


def test_freeze_detects_source_mutation(tmp_path,monkeypatch):
    (tmp_path/'outputs').mkdir(); p=tmp_path/'outputs/freeze_receipt.json'
    p.write_text(json.dumps({'analysis_source_sha256':{'a':'one'},'frozen_evidence_sha256':{}}))
    monkeypatch.setattr(core,'source_hashes',lambda root:{'a':'two'})
    with pytest.raises(RuntimeError,match='differs from the frozen'):core.verify_freeze(tmp_path)


def test_freeze_detects_selection_mutation(tmp_path,monkeypatch):
    (tmp_path/'outputs').mkdir();e=tmp_path/'outputs/selection.json';e.write_text('{}')
    p=tmp_path/'outputs/freeze_receipt.json'
    p.write_text(json.dumps({'analysis_source_sha256':{},'frozen_evidence_sha256':{'outputs/selection.json':core.sha256_file(e)}}))
    monkeypatch.setattr(core,'source_hashes',lambda root:{})
    e.write_text('{"changed":true}')
    with pytest.raises(RuntimeError,match='Frozen evidence changed'):core.verify_freeze(tmp_path)


def test_reporting_appearance_not_trading_source(tmp_path):
    (tmp_path/'configs').mkdir();(tmp_path/'configs/research.toml').write_text('x')
    (tmp_path/'pyproject.toml').write_text('x')
    d=tmp_path/'src/crypto_stat_arb_extensions';d.mkdir(parents=True)
    (d/'strategies.py').write_text('rule=1');(d/'reporting.py').write_text('color=1')
    before=core.source_hashes(tmp_path);(d/'reporting.py').write_text('color=2')
    assert core.source_hashes(tmp_path)==before
    (d/'strategies.py').write_text('rule=2')
    assert core.source_hashes(tmp_path)!=before


def test_json_records_undefined_stats_as_null(tmp_path):
    core.write_json(tmp_path/'receipt.json',{'sharpe':np.nan,'cash':np.bool_(True),'count':np.int64(0)})
    assert json.loads((tmp_path/'receipt.json').read_text())=={'cash':True,'count':0,'sharpe':None}


def test_original_and_scaled_dependencies_are_exact_copies():
    root=core.DEFAULT_ROOT;snapshot=json.loads((root/'outputs/baseline_preservation.json').read_text())
    vendor=root/'src/crypto_stat_arb_extensions/_vendor'
    for name in ['__init__.py','backtest.py','data.py','metrics.py']:
        assert core.sha256_file(vendor/'crypto_stat_arb'/name)==snapshot['baseline_files_sha256'][f'src/crypto_stat_arb/{name}']
    assert core.sha256_file(vendor/'legacy/extended_backtest.py')==snapshot['baseline_files_sha256']['outputs/followups/time_scale_scan/extended_backtest.py']


def test_covariance_exposure_summary_distinguishes_cash():
    from crypto_stat_arb.backtest import BacktestResult
    index=pd.date_range('2024-01-01 01:00',periods=24,freq='h',tz='UTC',name='bar_end')
    held=pd.DataFrame(.125,index=index,columns=list('abcdefgh'));held.iloc[:,:4]=0
    frame=pd.DataFrame({'gross_return':0.,'net_return':0.,'turnover':0.,'cost':0.,'equity':1.,'drawdown':0.,'interval_hours':1},index=index)
    result=BacktestResult(frame,held)
    spec={'strategy_id':'cash','family':'trend_long_cash','lookback_h':336,'rebalance_h':24,'buffer_l1':0.}
    stats=runner._summary(result,result,spec,'validation',20,1,None)
    assert stats['mean_cash_allocation']==.5 and stats['mean_gross_exposure']==.5
    spec['family']='trend_long_short'
    assert runner._summary(result,result,spec,'validation',20,1,None)['mean_cash_allocation'] is None
