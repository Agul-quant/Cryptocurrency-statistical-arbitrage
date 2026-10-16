"""Independent saved-path/coin/bootstrap reconciliation; never simulate trades.

This audit intentionally does not import the production source, accounting or
inference implementations. It reads only the root-authorized pinned inputs and
new frozen outputs and writes this audit directory alone.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
PARENT = REPO / 'research/post_oos_diagnostics_20261015'
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from research.basket_factor_attribution_20261016.gate import assert_frozen, record_access


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def same(a, b, label, *, atol=4e-12):
    aa, bb = np.asarray(a, float), np.asarray(b, float)
    if aa.shape != bb.shape or not np.allclose(aa, bb, rtol=4e-10, atol=atol, equal_nan=True):
        raise AssertionError(label + ' does not independently reconcile')


def labels(index):
    return (index-pd.Timedelta(nanoseconds=1)).floor('D')


def main():
    assert_frozen('Independent accounting-only audit of saved fixed paths')
    record_access('Independent audit after root-owned fixed-source release')
    catalog = json.loads((ROOT/'required_source_pins.json').read_text())
    for rel, digest in catalog['source_sha256'].items():
        if sha(REPO/rel) != digest:
            raise AssertionError('Changed authorized source: '+rel)
    preservation = json.loads((ROOT/'audit/original_preservation.json').read_text())
    for rel, digest in preservation['earlier_documents'].items():
        if sha(REPO/rel) != digest:
            raise AssertionError('Changed earlier document: '+rel)
    for rel, digest in preservation['final_reports_20261015']['files'].items():
        if sha(REPO/'final_reports_20261015'/rel) != digest:
            raise AssertionError('Changed original final-report artifact: '+rel)
    # Check the original seal itself as well as its 1,004 content pins.
    if sha(REPO/'final_reports_20261015/final_delivery_manifest.json') != preservation['final_reports_20261015']['manifest_sha256']:
        raise AssertionError('Original report-set seal changed')
    receipt = json.loads((ROOT/'outputs/computation_receipt.json').read_text())
    custody_path = ROOT/'audit/volatile_log_custody.json'
    if sha(custody_path) != '7fbcc73c997377cde875a0c2c802fdc5da2da80a3467e3b8f06157d5d7eb50c7':
        raise AssertionError('Unverified technical stdout custody amendment')
    custody = json.loads(custody_path.read_text())
    if custody['computation_receipt_sha256'] != sha(ROOT/'outputs/computation_receipt.json'):
        raise AssertionError('Custody amendment refers to another computation')
    log_repair = custody['volatile_log_repair']
    if len(log_repair) != 1 or log_repair[0]['path'] != 'outputs/computation.log':
        raise AssertionError('Only the declared live stdout log can have an intermediate pin')
    volatile = {r['path']: r for r in log_repair}
    for rel, digest in receipt['artifact_sha256'].items():
        expected = volatile[rel]['final_sha256'] if rel in volatile else digest
        if rel in volatile and digest != volatile[rel]['intermediate_sha256']:
            raise AssertionError('Unexpected intermediate stdout pin')
        if sha(ROOT/rel) != expected:
            raise AssertionError('Changed computed output: '+rel)
    stable = {r:h for r,h in receipt['artifact_sha256'].items() if r not in volatile}
    if stable != custody['stable_scientific_artifact_sha256']:
        raise AssertionError('Scientific outputs differ from their original receipt')
    paid_coin = pd.read_csv(ROOT/'outputs/coin_attribution.csv')
    saved_coin = pd.read_csv(PARENT/'attribution/coin_contributions.csv')
    legacy_metrics = pd.read_csv(PARENT/'shared/metrics.csv')
    daily_inputs = pd.read_parquet(ROOT/'outputs/daily_model_inputs.parquet')
    daily_components = pd.read_parquet(ROOT/'outputs/daily_attribution_components.parquet')
    models = json.loads((ROOT/'outputs/joint_models.json').read_text())
    model_by = {(r['strategy_id'], r['period']): r for r in models}
    meta = json.loads((ROOT/'outputs/metadata.json').read_text())
    meta_by = {(r['comparison_id'], r['period']): r for r in meta}
    prices = pd.read_parquet(PARENT/'shared/data/prices.parquet')
    observed = pd.read_parquet(PARENT/'shared/data/observed.parquet')
    hold = pd.read_parquet(PARENT/'shared/data/hold_allowed.parquet')
    exits = pd.read_parquet(PARENT/'shared/data/mandatory_exit.parquet')
    # Independently rebuild only marked asset returns, including the explicit
    # sourced whole-venue bridge; do not call the production helper.
    ret = prices/prices.shift(1)-1
    keep = np.ones(len(prices), dtype=bool)
    keep[0] = False
    durations = {}
    for bridge in catalog['source_quality']['halt_bridges']:
        left, right = pd.Timestamp(bridge['start']), pd.Timestamp(bridge['end'])
        if not bridge['source'] or left not in prices.index or right not in prices.index:
            raise AssertionError('Unverifiable bridge')
        if left.floor('D') != (right-pd.Timedelta(nanoseconds=1)).floor('D'):
            raise AssertionError('Bridge crosses accounting day')
        keep &= ~((prices.index>left)&(prices.index<right))
        ret.loc[right] = prices.loc[right]/prices.loc[left]-1
        durations[right] = int((right-left)/pd.Timedelta(hours=1))
    ret = ret.loc[keep]
    order = ('A01','A02','A03','A04','B01','B03','B04','B05','B06')
    periods = {'development': ('2022-01-01','2024-01-01',730),
               'validation': ('2024-01-01','2026-01-01',731),
               'oos_partial_2026_jan_sep': ('2026-01-01','2026-10-01',273)}
    if tuple(catalog['registry']['order']) != order or len(paid_coin) != 216:
        raise AssertionError('Changed nine-case or coin-row coverage')
    registry = {s['comparison_id']:s for s in catalog['registry']['strategies']}
    path_audits, calendar_audits, bootstrap_audits = [], [], []
    max_error = 0.
    for rec in catalog['records']:
        sid, period, syms = rec['comparison_id'], rec['period'], rec['symbols']
        if rec['case'] != registry[sid]['case'] or syms != registry[sid]['symbols'] or rec['execution_lag_h'] != 1:
            raise AssertionError('Frozen definition or identity changed')
        frame = pd.read_parquet(PARENT/rec['primary_path'])
        base = pd.read_parquet(PARENT/rec['base_path'])
        held = pd.read_parquet(PARENT/rec['held_path'])
        target = pd.read_parquet(PARENT/rec['targets_path'])
        linked_saved = pd.read_parquet(PARENT/rec['coin_hourly_path'])
        start, end, n_days = periods[period]
        days = pd.date_range(start, pd.Timestamp(end)-pd.Timedelta(days=1), freq='D', tz='UTC')
        expected_hours = 24*n_days
        t = frame.index
        hour_durations = np.array([durations.get(z,1) for z in t])
        same(hour_durations, frame.interval_hours, 'declared elapsed hours')
        if int(hour_durations.sum()) != expected_hours:
            raise AssertionError('Requested period shortened')
        if not np.array_equal(np.diff(t.asi8)/3_600_000_000_000,hour_durations[1:]):
            raise AssertionError('Unknown accounting interval gap')
        coverage = pd.Series(hour_durations,index=labels(t)).groupby(level=0).sum()
        if not coverage.index.equals(days) or not coverage.eq(24).all():
            raise AssertionError('Strategy daily grid was compressed')
        w = held.to_numpy(float)
        ar = ret.loc[t,syms].to_numpy(float)
        if ((~np.isfinite(ar))&(np.abs(w)>1e-14)).any():
            raise AssertionError('Nonzero holding has missing asset return')
        # Explicit loop reconstructions use prior post-event targets, starting
        # from cash, and charge each coin terminal liquidation once.
        post = w.copy()
        event = exits.loc[t,syms].any(axis=1).to_numpy()
        post[event] = target.loc[t,syms].to_numpy()[event]
        prev = np.vstack([np.zeros(8),post[:-1]])
        ordinary = np.abs(w-prev)
        forced = np.abs(post-w)
        terminal = np.zeros_like(w)
        terminal[-1] = np.abs(post[-1])
        units = ordinary+forced+terminal
        fee = units*.002
        gross = np.where(np.isfinite(ar),ar*w,0.)
        net = (gross-fee).sum(axis=1)
        nav = np.cumprod(1+net)
        prior = np.r_[1.,nav[:-1]]
        gross_linked = gross*prior[:,None]
        fee_linked = fee*prior[:,None]
        coin_linked = gross_linked-fee_linked
        for a,b,name in [(gross.sum(axis=1),frame.gross_return,'gross'),
                (gross.sum(axis=1),base.net_return,'base gross net'),
                (ordinary.sum(axis=1),frame.ordinary_turnover,'ordinary'),
                (forced.sum(axis=1),frame.forced_event_turnover,'forced'),
                (units.sum(axis=1),frame.turnover,'full-L1'),(fee.sum(axis=1),frame.cost,'cost'),
                (net,frame.net_return,'net'),(nav,frame.equity,'NAV'),
                (coin_linked,linked_saved,'saved hourly coin link')]:
            same(a,b,sid+' '+period+' '+name)
        out = paid_coin.loc[paid_coin.strategy_id.eq(sid)&paid_coin.period.eq(period)].set_index('symbol').loc[syms]
        old = saved_coin.loc[saved_coin.comparison_id.eq(sid)&saved_coin.period.eq(period)].set_index('symbol').loc[syms]
        for metric,a in [('gross_linked_contribution',gross_linked.sum(axis=0)),
                         ('linked_fees',fee_linked.sum(axis=0)),
                         ('net_linked_contribution',coin_linked.sum(axis=0)),
                         ('full_l1_turnover',units.sum(axis=0)),
                         ('ordinary_turnover',ordinary.sum(axis=0)),
                         ('forced_turnover',forced.sum(axis=0)),
                         ('terminal_turnover',terminal.sum(axis=0))]:
            output_metric = 'fees_linked_contribution' if metric=='linked_fees' else metric
            same(a,out[output_metric],sid+' '+period+' current '+metric)
            same(a,old[metric],sid+' '+period+' original '+metric)
        expected_metric = legacy_metrics.loc[legacy_metrics.comparison_id.eq(sid)&legacy_metrics.period.eq(period)&legacy_metrics.execution_lag_h.eq(1)].iloc[0]
        same(nav[-1]-1,expected_metric.total_return,'saved strategy total return')
        same(coin_linked.sum(),nav[-1]-1,'all coin compound return')
        error = float(abs(coin_linked.sum()-(nav[-1]-1)))
        max_error = max(max_error,error)
        day_start_nav = pd.Series(prior,index=labels(t)).groupby(level=0).first()
        dg = pd.DataFrame(gross_linked,index=labels(t),columns=syms).groupby(level=0).sum().div(day_start_nav,axis=0)
        df = pd.DataFrame(fee_linked,index=labels(t),columns=syms).groupby(level=0).sum().div(day_start_nav,axis=0)
        dy = pd.Series(net,index=labels(t)).groupby(level=0).apply(lambda x:math.expm1(math.fsum(math.log1p(float(z)) for z in x)))
        current_y = daily_inputs.loc[daily_inputs.strategy_id.eq(sid)&daily_inputs.period.eq(period)].copy()
        current_y = current_y.set_index('utc_day').sort_index()
        if not current_y.index.equals(days):
            raise AssertionError('Daily strategy output lost dates')
        same(dy,current_y.strategy_net_return,'daily compounded strategy')
        same((dg-df).sum(axis=1),dy,'daily component vector')
        cp = daily_components.loc[daily_components.strategy_id.eq(sid)&daily_components.period.eq(period)]
        cg = cp.pivot(index='utc_day',columns='symbol',values='gross_component').loc[days,syms]
        cf = cp.pivot(index='utc_day',columns='symbol',values='fee_component').loc[days,syms]
        same(dg,cg,'exported normalized gross');same(df,cf,'exported normalized fee')
        # Independent strict factor construction checks every intraday return,
        # not merely endpoints. A venue bridge is an allowed elapsed interval;
        # lifecycle absence and forced partial exits remain unknown factors.
        finite = pd.DataFrame(np.isfinite(ar),index=t,columns=syms)
        known = finite & observed.loc[t,syms] & hold.loc[t,syms] & ~exits.loc[t,syms]
        known_day = known.groupby(labels(t)).all()
        factors = ((1+ret.loc[t,syms]).groupby(labels(t)).prod(min_count=1)-1).where(known_day)
        same(factors,current_y[syms],'strict observed factor daily returns')
        joint = factors.notna().all(axis=1)
        model = model_by[(sid,period)]
        if int(joint.sum()) != model['n_fit_days'] or n_days-int(joint.sum()) != model['n_excluded_days']:
            raise AssertionError('Regression complete-case calendar count mismatch')
        for symbol in syms:
            if int(factors[symbol].isna().sum()) != model['factor_missing_days'][symbol]:
                raise AssertionError('Missing-factor count changed')
        calendar_audits.append({'strategy_id':sid,'period':period,'strategy_days':n_days,
            'joint_days':int(joint.sum()),'excluded_days':int((~joint).sum()),
            'missing_by_symbol':{s:int(factors[s].isna().sum()) for s in syms},
            'all_factor_missingness_preserved':True})
        path_audits.append({'strategy_id':sid,'period':period,'net_return':float(nav[-1]-1),
            'coin_sum_error':error,'ordinary_units':float(ordinary.sum()),'forced_units':float(forced.sum()),
            'terminal_units':float(terminal.sum()),'elapsed_hours':expected_hours,'n_days':n_days,
            'source_partial_events':frame.attrs.get('partial_interval_events',[]),
            'all_checks_passed':True})
        # Bounded independent bootstrap draw audit. Unlike resampling existing
        # linked period P&L, rebuild NEW NAV for each synchronized index sequence.
        indices = np.load(ROOT/'outputs'/('bootstrap_indices_'+period+'.npy'),allow_pickle=False)
        rng = np.random.Generator(np.random.PCG64(20261016))
        starts = rng.integers(0,n_days,size=(4000,math.ceil(n_days/28)))
        independently_expected = ((starts[:,:,None]+np.arange(28))%n_days).reshape(4000,-1)[:,:n_days]
        if not np.array_equal(indices,independently_expected):
            raise AssertionError('Declared synchronized calendar bootstrap indices differ')
        selected_draws = [0,1,2,17,199,3999]
        draw_max_error = 0.
        for draw in selected_draws:
            wealth = 1.
            g_contribution = np.zeros(8)
            f_contribution = np.zeros(8)
            for take in indices[draw]:
                gi,fi = cg.iloc[take].to_numpy(),cf.iloc[take].to_numpy()
                g_contribution += wealth*gi
                f_contribution += wealth*fi
                wealth *= 1+float(np.sum(gi-fi))
            if not np.isfinite(wealth) or wealth<=0:
                raise AssertionError('Invalid audited bootstrap wealth')
            e = abs(float(np.sum(g_contribution-f_contribution))-(wealth-1))
            draw_max_error = max(draw_max_error,e)
            same(np.sum(g_contribution-f_contribution),wealth-1,'fresh NAV bootstrap draw')
        bootstrap_audits.append({'strategy_id':sid,'period':period,'audited_draws':selected_draws,
            'common_4000_indices_exact':True,'fresh_nav_relink_checks_passed':True,
            'maximum_draw_reconciliation_error':draw_max_error})
        print('PASS',sid,period,n_days,'days; joint',int(joint.sum()),'; terminal',float(terminal.sum()),flush=True)
    keys={(r['strategy_id'],r['period']) for r in path_audits}
    if len(keys)!=27 or keys!={(s,p) for s in order for p in periods}:
        raise AssertionError('27-path scope mismatch')
    freeze=json.loads((ROOT/'outputs/access_freeze.json').read_text())
    access=json.loads((ROOT/'outputs/source_access_receipt.json').read_text())
    if pd.Timestamp(access['created_at_utc'])<pd.Timestamp(freeze['created_at_utc']):
        raise AssertionError('Source access before new freeze')
    result={'status':'PASS_independent_accounting_coverage_preservation_and_bootstrap_draw_audit',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'auditor_code_sha256':sha(__file__),'frozen_source_files_verified':len(catalog['source_sha256']),
        'original_final_report_artifacts_unchanged':len(preservation['final_reports_20261015']['files']),
        'earlier_documents_unchanged':len(preservation['earlier_documents']),
        'computed_artifacts_reverified':len(receipt['artifact_sha256']),
        'technical_stdout_intermediate_pin_amendment_verified': True,
        'all_27_frozen_paths_unchanged':True,'all_216_coin_point_rows_reconciled':True,
        'all_strategy_days_730_731_273_preserved':True,'strict_factor_gap_handling_verified':True,
        'fresh_nav_bootstrap_draws_checked':27*6,'maximum_coin_return_reconciliation_error':max_error,
        'no_new_prices_strategies_or_selections':True,'access_follows_owned_freeze':True,
        'path_checks':path_audits,'factor_calendar_checks':calendar_audits,'bootstrap_draw_checks':bootstrap_audits}
    (ROOT/'audit/independent_accounting.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('path_checks','factor_calendar_checks','bootstrap_draw_checks')},indent=2))


if __name__=='__main__':
    main()
