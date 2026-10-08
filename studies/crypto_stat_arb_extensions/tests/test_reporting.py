"""Presentation contracts: honest undefined metrics, named controls, no 2026 reads."""
import json
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from crypto_stat_arb_extensions.reporting import (fmt,label,plot_ic,plot_regimes,
    plot_factor,verify_frozen_inputs,sha256)


def test_undefined_metric_is_not_zero():
    assert fmt(np.nan)=='N/A'
    assert fmt(None)=='N/A'
    assert fmt(np.inf)=='N/A'
    assert fmt(0,True)=='0.00%'
    assert fmt(-.2,True)=='-20.00%'


def test_bounded_strategy_labels_keep_differences():
    a=label('cross_momentum_h336_r024_b000')
    b=label('cross_momentum_h336_r024_b025')
    c=label('cross_momentum_h672_r168_b000')
    assert a=='CS momentum 14d daily'
    assert b==a+' + buffer'
    assert c=='CS momentum 28d weekly'
    assert 'long/cash' in label('trend_long_cash_h336_r024_b000')
    assert 'long/short' in label('trend_long_short_h672_r168_b000')
    assert label('factor_residual_fixed')=='BTC-factor reversal'
    assert '1h' in label('reversal_h001_r024')


def test_ic_forward_horizon_schema_and_star():
    rows=[dict(split='validation',lookback_h=l,forward_horizon_h=f,mean_ic=.1 if l==1 else -.05,p_holm=.01 if f==1 else .2)
          for l in [1,24] for f in [1,24,168]]
    fig=plot_ic(pd.DataFrame(rows))
    texts=[t.get_text() for a in fig.axes for t in a.texts]
    assert '+0.10*' in texts
    assert '-0.05' in texts
    plt.close(fig)


def test_regime_duplicate_conditional_rows_are_one_contrast():
    rows=[]
    for f in ['relative_quote_volume','btc_volatility_30d','return_dispersion_24h']:
        for r in ['high','low','unknown']:
            rows.append(dict(split='holdout',strategy_id='factor_residual_fixed',feature=f,regime=r,high_minus_low_net_return=.001,ci_low=-.002,ci_high=.003))
    fig=plot_regimes(pd.DataFrame(rows))
    assert len(fig.axes)==3
    assert all(len(ax.collections)==2 for ax in fig.axes) # one point and one interval
    plt.close(fig)


def test_skipped_factor_extremes_are_not_entries():
    models=pd.DataFrame([dict(refit_time='2026-01-01T00:00:00Z',symbol='ETHUSDT',eligible=True)])
    events=pd.DataFrame([dict(decision_time='2026-01-02T00:00:00Z',event='entry',symbol='ETHUSDT'),
                         dict(decision_time='2026-01-03T00:00:00Z',event='entry_skipped_extreme',symbol='ETHUSDT')])
    fig=plot_factor(models,events)
    assert fig.axes[1].patches[0].get_height()==1
    plt.close(fig)


def _receipt(tmp_path,freeze='2026-10-06T12:00:00Z',access='2026-10-06T13:00:00Z'):
    (tmp_path/'outputs').mkdir()
    (tmp_path/'outputs/selection.json').write_text('{}')
    r={'frozen_at_utc':freeze,'analysis_hashes':{},'selection_sha256':sha256(tmp_path/'outputs/selection.json')}
    (tmp_path/'outputs/freeze_receipt.json').write_text(json.dumps(r))
    (tmp_path/'outputs/holdout_access_receipt.json').write_text(json.dumps({'first_access_utc':access}))


def test_chronology_receipt_root_schema(tmp_path):
    _receipt(tmp_path)
    with patch('crypto_stat_arb_extensions.core.verify_freeze') as guard:
        receipt=verify_frozen_inputs(tmp_path)
        guard.assert_called_once_with(tmp_path)
    assert receipt['freeze_at_utc']<receipt['first_holdout_access_utc']


def test_chronology_rejects_prefreeze_access(tmp_path):
    _receipt(tmp_path,access='2026-10-06T11:00:00Z')
    with patch('crypto_stat_arb_extensions.core.verify_freeze'):
        with pytest.raises(ValueError,match='Freeze did not precede'):
            verify_frozen_inputs(tmp_path)


def test_chronology_rejects_changed_selection(tmp_path):
    _receipt(tmp_path)
    (tmp_path/'outputs/selection.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='Selection differs'):
        verify_frozen_inputs(tmp_path)


def test_factor_chart_excludes_unused_terminal_refit():
    models=pd.DataFrame([dict(refit_time='2026-09-01T00:00:00Z',symbol='ETHUSDT',eligible=True),
                         dict(refit_time='2026-10-01T00:00:00Z',symbol='ETHUSDT',eligible=True)])
    events=pd.DataFrame([dict(decision_time='2026-09-02T00:00:00Z',event='entry',symbol='ETHUSDT'),
                         dict(decision_time='2026-10-01T00:00:00Z',event='entry',symbol='ETHUSDT')])
    fig=plot_factor(models,events)
    assert sum(p.get_height() for p in fig.axes[0].patches)==1
    assert fig.axes[1].patches[0].get_height()==1
    plt.close(fig)
