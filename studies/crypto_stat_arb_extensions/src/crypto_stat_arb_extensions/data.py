"""Separated history/holdout acquisition; no 2026 price access before freeze."""
from __future__ import annotations
import json
import shutil
from pathlib import Path
import pandas as pd

from crypto_stat_arb.data import download_and_prepare, load_panel, verify_checksum
from .core import load_config, sha256_file, utc_now, verify_baseline, verify_freeze, write_json


def history_root(root):
    return Path(root)/'datasets/history'


def full_root(root):
    return Path(root)/'datasets/full'


def _copy_verified_cache(source, destination):
    source,destination=Path(source),Path(destination)
    manifest=json.loads((source/'data/raw/manifest.json').read_text())
    copied=[]
    for entry in manifest['files']:
        if entry['month'] >= '2026-01':
            raise RuntimeError('Historical cache reuse may not copy 2026 prices.')
        old=source/entry['archive_path']; checksum=old.with_name(old.name+'.CHECKSUM')
        digest=verify_checksum(old,checksum)
        if digest != entry['sha256']:
            raise RuntimeError('Source cache manifest disagrees with verified archive.')
        for p in [old,checksum]:
            relative=p.relative_to(source);target=destination/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if sha256_file(target)!=sha256_file(p):
                    raise RuntimeError(f'Existing copied cache differs: {relative}')
            else:shutil.copy2(p,target)
        copied.append({'archive_path':entry['archive_path'],'sha256':digest})
    repairs=source/'data/raw/repairs'
    if repairs.exists():
        for p in repairs.rglob('*'):
            if p.is_file():
                target=destination/p.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists():shutil.copy2(p,target)
                elif sha256_file(target)!=sha256_file(p):
                    raise RuntimeError(f'Repair cache differs: {target.name}')
    target_manifest=destination/'data/raw/manifest.json'
    if not target_manifest.exists():
        target_manifest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/'data/raw/manifest.json',target_manifest)
    return copied


def prepare_history(root):
    root=Path(root);config=load_config(root)
    if pd.Timestamp(config['data']['history_end']) > pd.Timestamp('2026-01-01'):
        raise RuntimeError('Historical preparation cannot include 2026.')
    if (root/'outputs/freeze_receipt.json').exists():
        verify_freeze(root)
        close,volume,audit=load_history(root)
        return audit
    preservation=verify_baseline(root)
    baseline=Path(json.loads((root/'outputs/baseline_preservation.json').read_text())['baseline_root'])
    cache=history_root(root)
    copies=_copy_verified_cache(baseline,cache)
    settings={**config['data'],'end':config['data']['history_end']}
    audit=download_and_prepare(cache,{'data':settings})
    close,_,_=load_panel(cache)
    if close.index.max()>pd.Timestamp(config['data']['history_end'],tz='UTC'):
        raise RuntimeError('Historical price panel crosses its cutoff.')
    write_json(root/'outputs/history_data_receipt.json',{
        'prepared_at_utc':utc_now(),'data_root':str(cache),
        'source_attribution':'Binance Vision; non-commercial educational research; CC BY-NC-SA 4.0',
        'cached_archive_count':len(copies),'copied_archives':copies,
        'coverage_start':config['data']['start'],'coverage_end':config['data']['history_end'],
        'prices_after_history_cutoff_accessed':False,
        'audit':audit,'parquet_sha256':sha256_file(cache/'data/processed/bars.parquet'),
        'baseline_preservation':preservation,
    })
    verify_baseline(root)
    return audit


def load_history(root):
    audit_path=history_root(root)/'data/processed/data_quality.json'
    declared=json.loads(audit_path.read_text())
    if pd.Timestamp(declared['end_open_time_exclusive'])>pd.Timestamp('2026-01-01',tz='UTC'):
        raise RuntimeError('Historical loader refuses declared 2026 outcomes before reading prices.')
    close,volume,audit=load_panel(history_root(root))
    if close.index.max()>pd.Timestamp('2026-01-01',tz='UTC'):
        raise RuntimeError('Historical loader refuses a panel containing 2026 outcomes.')
    return close,volume,audit


def prepare_holdout(root):
    root=Path(root);freeze=verify_freeze(root);config=load_config(root)
    verify_baseline(root)
    access_path=root/'outputs/holdout_access_receipt.json'
    full=full_root(root)
    if not access_path.exists():
        existing=list((full/'data/raw').rglob('*2026*.zip')) if (full/'data/raw').exists() else []
        if existing:raise RuntimeError('Unreceipted 2026 cache exists; cannot claim fresh access chronology.')
        write_json(access_path,{
            'first_access_utc':utc_now(),'freeze_timestamp_utc':freeze['frozen_at_utc'],
            'freeze_receipt_sha256':sha256_file(root/'outputs/freeze_receipt.json'),
            'selection_sha256':freeze['selection_sha256'],
            'meaning':'Start of the first permitted acquisition operation; recorded before any 2026 archive read/download.',
            'historical_holdout_not_prospective_live_test':True,
        })
    access=json.loads(access_path.read_text())
    if pd.Timestamp(access['first_access_utc'])<=pd.Timestamp(freeze['frozen_at_utc']):
        raise RuntimeError('Holdout access must follow the frozen protocol.')
    if access['freeze_receipt_sha256']!=sha256_file(root/'outputs/freeze_receipt.json'):
        raise RuntimeError('Original holdout access was authorized by a different freeze receipt.')
    _copy_verified_cache(history_root(root),full)
    access.setdefault('download_started_utc',utc_now());write_json(access_path,access)
    try:
        settings={**config['data'],'end':config['data']['holdout_end']}
        audit=download_and_prepare(full,{'data':settings})
        close,volume,_=load_panel(full)
        history_close,history_volume,_=load_history(root)
        pd.testing.assert_frame_equal(close.loc[history_close.index],history_close,check_freq=False)
        pd.testing.assert_frame_equal(volume.loc[history_volume.index],history_volume,check_freq=False)
        expected=pd.Timestamp(config['data']['holdout_end'],tz='UTC')
        if close.index.max()!=expected:raise RuntimeError('Full data do not reach the fixed holdout endpoint.')
        access['download_completed_utc']=utc_now()
        access['verified_2026_archive_count']=sum(e['month']>='2026-01' for e in json.loads((full/'data/raw/manifest.json').read_text())['files'])
        access['audit']=audit;access['parquet_sha256']=sha256_file(full/'data/processed/bars.parquet')
        access['historical_close_and_volume_prefix_equals_frozen_history']=True
        write_json(access_path,access)
        write_json(root/'outputs/holdout_status.json',{'status':'data_ready_not_evaluated','updated_at_utc':utc_now()})
        verify_freeze(root);verify_baseline(root)
        return audit
    except Exception as error:
        write_json(root/'outputs/holdout_status.json',{
            'status':'not_evaluated','reason':str(error),'updated_at_utc':utc_now(),
            'period_shortened':False,'prices_filled':False,
        })
        raise


def load_full_panel(root):
    root=Path(root);verify_freeze(root)
    access_path=root/'outputs/holdout_access_receipt.json'
    if not access_path.exists():raise RuntimeError('Full panel has no authorized holdout access receipt.')
    access=json.loads(access_path.read_text())
    if not access.get('download_completed_utc'):
        raise RuntimeError('Holdout acquisition/data quality is not complete.')
    close,volume,audit=load_panel(full_root(root))
    if sha256_file(full_root(root)/'data/processed/bars.parquet')!=access['parquet_sha256']:
        raise RuntimeError('Holdout data differ from the original verified acquisition snapshot.')
    return close,volume,audit
