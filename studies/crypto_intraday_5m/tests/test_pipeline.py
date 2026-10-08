import json
import numpy as np
import pandas as pd
import pytest
from crypto_intraday_5m import runner
from crypto_intraday_5m.core import load_config,write_json,source_hashes,DEFAULT_ROOT
from crypto_intraday_5m.backtest import candidate_grid


def table():
    return pd.DataFrame([{**s,'split':split,'cost_bps':20,'execution_lag':1,'sharpe':-1.,
                          'total_return':-.99,'terminal_log_equity':-5.,'mean_minute_turnover':.1}
                         for s in candidate_grid() for split in ['development','validation','retrospective','retrospective_2026']])


def test_declared_grid_parameters_exact():
    p=json.loads((DEFAULT_ROOT/'outputs/protocol.json').read_text())
    keys=['family','lookback_minutes','rebalance_minutes']
    assert [{k:s[k] for k in keys} for s in p['candidate_grid']]==[{k:s[k] for k in keys} for s in candidate_grid()]
    assert p['all_periods_exploratory_retrospective'] is True


def test_selection_2024_only():
    t=table();before=runner.select_strategies(t)
    t.loc[t.split.isin(['retrospective','retrospective_2026']),'sharpe']=np.arange(36)*1000
    assert runner.select_strategies(t)==before
    assert all(s['role']=='negative_control' for s in before)


def test_selection_cost_twenty_only():
    t=table();extra=t.copy();extra.cost_bps=0;extra.sharpe=999
    assert runner.select_strategies(pd.concat([t,extra]))==runner.select_strategies(t)


def test_ties_turnover_then_id():
    t=table();sid='momentum_m030_r060';t.loc[t.strategy_id.eq(sid),'mean_minute_turnover']=.001
    chosen=runner.select_strategies(t)
    assert chosen[0]['strategy_id']==sid
    assert chosen[1]['strategy_id']==sorted(t.loc[t.family.eq('reversal'),'strategy_id'].unique())[0]


def test_undefined_family_sharpe_not_invented():
    t=table();t.loc[t.family.eq('reversal'),'sharpe']=np.nan
    with pytest.raises(ValueError,match='No defined'):runner.select_strategies(t)


def test_nan_json_null(tmp_path):
    write_json(tmp_path/'x.json',{'sr':np.nan,'value':np.int64(18),'flag':np.bool_(True)})
    assert json.loads((tmp_path/'x.json').read_text())=={'sr':None,'value':18,'flag':True}


def test_changing_report_not_analysis_hash(tmp_path):
    (tmp_path/'configs').mkdir();(tmp_path/'configs/research.toml').write_text('x')
    (tmp_path/'pyproject.toml').write_text('x')
    d=tmp_path/'src/crypto_intraday_5m';d.mkdir(parents=True);(d/'reporting.py').write_text('color=1')
    (d/'backtest.py').write_text('rule=1');before=source_hashes(tmp_path)
    (d/'reporting.py').write_text('color=2');assert before==source_hashes(tmp_path)
    (d/'backtest.py').write_text('rule=2');assert before!=source_hashes(tmp_path)


def test_config_daily_minutes_and_no_fresh_holdout():
    c=load_config();assert c['data']['interval']=='5m';assert c['research']['primary_cost_bps']==20
    assert 'holdout' not in c['splits']
    assert (pd.Timestamp(c['splits']['retrospective_2026']['end'])-pd.Timestamp(c['splits']['retrospective_2026']['start'])).days==273
