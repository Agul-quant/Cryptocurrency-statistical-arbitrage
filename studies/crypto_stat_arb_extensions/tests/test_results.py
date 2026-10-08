"""Independent real-output checks; no strategy fitting, selection or network."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from crypto_stat_arb_extensions.core import DEFAULT_ROOT,sha256_file,verify_freeze,verify_baseline
from crypto_stat_arb_extensions.data import load_full_panel,load_history
from crypto_stat_arb_extensions.runner import select_champions,evaluate_holdout

READY=(DEFAULT_ROOT/'outputs/holdout_metrics.csv').exists()
pytestmark=pytest.mark.skipif(not READY,reason='Frozen cached research results not yet available')


@pytest.fixture(scope='module')
def research():
    from crypto_stat_arb.backtest import observed_asset_returns
    root=DEFAULT_ROOT;prices,volume,audit=load_full_panel(root)
    frames=pd.read_parquet(root/'outputs/selected_returns.parquet')
    weights=pd.read_parquet(root/'outputs/selected_weights.parquet')
    return root,prices,volume,audit,frames.loc[frames.split.eq('holdout')],weights.loc[weights.split.eq('holdout')],observed_asset_returns(prices)


STRATEGIES=['cross_momentum_h336_r168_b000','trend_long_cash_h336_r024_b000',
            'trend_long_short_h336_r024_b000','factor_residual_fixed',
            'reference_original_momentum','reference_original_reversal',
            'reference_scale_momentum','reference_scale_reversal']
SCENARIOS=[(0,1),(5,1),(10,1),(15,1),(20,1),(40,1),(20,2)]


@pytest.mark.parametrize('strategy',STRATEGIES)
@pytest.mark.parametrize('cost,lag',SCENARIOS)
def test_every_holdout_scenario_independent_accounting(research,strategy,cost,lag):
    root,prices,_,_,frames,weights,assets=research
    f=frames.loc[frames.strategy_id.eq(strategy)&frames.cost_bps.eq(cost)&frames.execution_lag.eq(lag)].set_index('bar_end').sort_index()
    w=weights.loc[weights.strategy_id.eq(strategy)&weights.execution_lag.eq(lag)].set_index('bar_end').sort_index()[prices.columns]
    assert len(f)==6552 and f.interval_hours.eq(1).all()
    assert f.index[0]==pd.Timestamp('2026-01-01 01:00',tz='UTC')
    assert f.index[-1]==pd.Timestamp('2026-10-01 00:00',tz='UTC')
    assert (f.index[1:]-f.index[:-1]==pd.Timedelta(hours=1)).all()
    gross=(w*assets.reindex(w.index)).sum(axis=1).to_numpy()
    changes=np.diff(w.to_numpy(),axis=0,prepend=np.zeros((1,8)))
    turnover=np.abs(changes).sum(axis=1);turnover[-1]+=np.abs(w.iloc[-1]).sum()
    net=gross-turnover*cost*1e-4;equity=np.cumprod(1+net)
    peak=np.maximum.accumulate(np.r_[1.,equity])[1:];drawdown=equity/peak-1
    for key,expected in [('gross_return',gross),('turnover',turnover),('cost',turnover*cost*1e-4),('net_return',net),('equity',equity),('drawdown',drawdown)]:
        np.testing.assert_allclose(f[key],expected,atol=1e-13,rtol=1e-12)
    daily=np.prod((1+net).reshape(273,24),axis=1)-1
    metrics=pd.read_csv(root/'outputs/holdout_metrics.csv')
    m=metrics.loc[metrics.strategy_id.eq(strategy)&metrics.cost_bps.eq(cost)&metrics.execution_lag.eq(lag)].iloc[0]
    np.testing.assert_allclose(m.total_return,equity[-1]-1,atol=1e-12)
    np.testing.assert_allclose(m.annual_return,daily.mean()*365,atol=1e-12)
    np.testing.assert_allclose(m.annual_volatility,daily.std(ddof=1)*np.sqrt(365),atol=1e-12)
    if daily.std(ddof=1)>1e-15:
        np.testing.assert_allclose(m.sharpe,daily.mean()/daily.std(ddof=1)*np.sqrt(365),atol=1e-12)
    else:assert pd.isna(m.sharpe)
    np.testing.assert_allclose(m.max_drawdown,-drawdown.min(),atol=1e-12)


def test_freeze_and_first_real_archive_chronology(research):
    root,*_=research;f=verify_freeze(root)
    a=json.loads((root/'outputs/holdout_access_receipt.json').read_text())
    assert pd.Timestamp(f['frozen_at_utc'])<pd.Timestamp(a['first_access_utc'])
    manifest=json.loads((root/'datasets/full/data/raw/manifest.json').read_text())
    new=[r for r in manifest['files'] if r['month']>='2026-01']
    assert len(new)==72
    assert all(pd.Timestamp(r['downloaded_utc'])>pd.Timestamp(a['first_access_utc']) for r in new)
    assert a['historical_close_and_volume_prefix_equals_frozen_history'] is True


def test_full_history_prefix_and_audited_gap(research):
    root,prices,volume,audit,*_=research
    hp,hv,ha=load_history(root)
    pd.testing.assert_frame_equal(prices.loc[hp.index],hp,check_freq=False)
    pd.testing.assert_frame_equal(volume.loc[hv.index],hv,check_freq=False)
    assert len(prices)==43824 and len(hp)==37272
    missing=prices.index[prices.isna().any(axis=1)]
    assert missing.tolist()==[pd.Timestamp('2023-03-24 14:00',tz='UTC')]
    assert audit['status']=='pass_with_documented_exceptions'
    assert not prices.loc[prices.index>pd.Timestamp('2026-01-01',tz='UTC')].isna().any().any()


def test_frozen_selection_validation_only(research):
    root,*_=research;s=json.loads((root/'outputs/selection.json').read_text())
    recomputed=select_champions(pd.read_csv(root/'outputs/historical_metrics.csv'))
    assert [x['strategy_id'] for x in recomputed]==[x['strategy_id'] for x in s['champions']]
    assert s['retrospective_2025_used_for_selection'] is False
    assert len(s['evaluated_strategies'])==8
    assert pd.read_csv(root/'outputs/historical_metrics.csv').shape[0]==51


def test_factor_formation_past_only_and_terminal_records_explicit(research):
    root,*_=research;models=pd.read_csv(root/'outputs/factor_models.csv')
    for col in ['refit_time','formation_price_start','fit_start','fit_end','calibration_start','calibration_end']:
        models[col]=pd.to_datetime(models[col],utc=True)
    assert not models.duplicated(['refit_time','symbol']).any()
    assert (models.calibration_end==models.refit_time-pd.Timedelta(days=1)).all()
    assert (models.fit_end<models.calibration_start).all()
    assert ((models.fit_end-models.fit_start)/pd.Timedelta(days=1)==29).all()
    assert ((models.calibration_end-models.calibration_start)/pd.Timedelta(days=1)==59).all()
    inside=models.loc[models.refit_time.ge(pd.Timestamp('2026-01-01',tz='UTC'))&models.refit_time.lt(pd.Timestamp('2026-10-01',tz='UTC'))]
    assert len(inside)==63
    assert len(models.loc[models.refit_time.eq(pd.Timestamp('2026-10-01',tz='UTC'))])==7
    events=pd.read_csv(root/'outputs/factor_events.csv')
    assert not events.duplicated(['decision_time','symbol','event']).any()


def test_regimes_unknown_not_filtered_and_family_size(research):
    root,*_=research;threshold=json.loads((root/'outputs/regime_thresholds.json').read_text())
    assert threshold['training_start'].startswith('2022-01-01')
    assert threshold['training_end_exclusive'].startswith('2024-01-01')
    regimes=pd.read_csv(root/'outputs/regime_summary.csv')
    assert set(regimes.regime)=={'high','low','unknown'}
    assert regimes.holm_family_size.eq(24).all()
    assert not any('sharpe' in c.lower() for c in regimes.columns)
    ic=pd.read_csv(root/'outputs/ic_summary.csv')
    assert ic.holm_family_size.eq(24).all()
    assert ic.groupby('split').size().eq(24).all()


def test_cost_stresses_monotonic_no_reselection(research):
    root,*_=research;m=pd.read_csv(root/'outputs/holdout_metrics.csv')
    for _,g in m.loc[m.execution_lag.eq(1)].groupby('strategy_id'):
        assert (g.sort_values('cost_bps').total_return.diff().dropna()<=0).all()
        assert g.gross_total_return.max()-g.gross_total_return.min()<1e-12
    manifest=json.loads((root/'outputs/run_manifest.json').read_text())
    assert manifest['parameter_reselection_after_holdout'] is False


def test_completed_evaluation_reuses_without_network(research,monkeypatch):
    root,*_=research
    import crypto_stat_arb_extensions.runner as runner
    monkeypatch.setattr(runner,'prepare_holdout',lambda root:pytest.fail('Completed evaluation must not reacquire/reselect'))
    access=root/'outputs/holdout_access_receipt.json';before=sha256_file(access)
    result=evaluate_holdout(root)
    assert result['status']=='complete' and sha256_file(access)==before


def test_original_project_and_bundle_still_unchanged(research):
    root,*_=research;preserved=verify_baseline(root)
    assert preserved=={'status':'unchanged','file_count':868,'zip_unchanged':True}
