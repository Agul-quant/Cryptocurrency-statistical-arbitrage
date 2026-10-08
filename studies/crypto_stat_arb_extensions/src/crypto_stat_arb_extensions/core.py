"""Shared provenance and untouched baseline API access."""
from __future__ import annotations
import hashlib
import json
import platform
import tomllib
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import numpy as np
import pandas as pd

BASELINE_ROOT = Path('/Users/cosdis/Desktop/job/quant_projects/crypto_stat_arb')
DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    def clean(x):
        if isinstance(x, dict): return {str(k): clean(v) for k,v in x.items()}
        if isinstance(x, (list,tuple)): return [clean(v) for v in x]
        if isinstance(x, (pd.Timestamp, Path)): return str(x)
        if isinstance(x, np.integer): return int(x)
        if isinstance(x, (np.floating,float)): return float(x) if np.isfinite(x) else None
        if isinstance(x, np.bool_): return bool(x)
        return x
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(clean(value), indent=2, sort_keys=True, allow_nan=False)+'\n')
    temporary.replace(path)


def load_config(root=DEFAULT_ROOT):
    with (Path(root)/'configs/research.toml').open('rb') as stream:
        config = tomllib.load(stream)
    if config['research']['primary_cost_bps'] != 20:
        raise ValueError('The course primary cost remains 20 bps.')
    if config['diagnostics']['regime_filters_trade']:
        raise ValueError('This frozen study does not trade regime filters.')
    for previous, following in [('development','validation'),('validation','retrospective'),('retrospective','holdout')]:
        if config['splits'][previous]['end'] != config['splits'][following]['start']:
            raise ValueError('Research windows must be chronological and contiguous.')
    return config


def get_scaled_generator():
    from ._vendor.legacy.extended_backtest import generate_scaled_targets
    return generate_scaled_targets


def source_hashes(root):
    root = Path(root)
    # Report appearance and independent verification tests are not trading rules.
    paths = [root/'configs/research.toml',root/'pyproject.toml']
    paths += [p for p in (root/'src/crypto_stat_arb_extensions').rglob('*.py')
              if p.name != 'reporting.py']
    return {str(p.relative_to(root)): sha256_file(p) for p in sorted(paths)}


def verify_baseline(root=DEFAULT_ROOT, *, require_present=True):
    receipt = json.loads((Path(root)/'outputs/baseline_preservation.json').read_text())
    baseline = Path(receipt['baseline_root'])
    if not baseline.exists():
        if require_present: raise FileNotFoundError('Original baseline is unavailable for preservation check.')
        return {'status':'not_locally_available','snapshot_file_count':receipt['baseline_file_count']}
    differences = []
    for relative, digest in receipt['baseline_files_sha256'].items():
        p = baseline/relative
        if not p.is_file() or sha256_file(p) != digest: differences.append(relative)
    excluded={'tmp','__pycache__','.pytest_cache','.git'}
    current={str(p.relative_to(baseline)) for p in baseline.rglob('*') if p.is_file()
             and not any(part in excluded or part.endswith('.egg-info') for part in p.relative_to(baseline).parts)}
    differences.extend(sorted(current-set(receipt['baseline_files_sha256'])))
    bundle = baseline.parent/'crypto_stat_arb_project.zip'
    if not bundle.is_file() or sha256_file(bundle) != receipt['original_bundle_sha256']:
        differences.append('original_project_zip')
    if differences: raise RuntimeError(f'Original baseline modified: {differences[:10]}')
    return {'status':'unchanged','file_count':receipt['baseline_file_count'],'zip_unchanged':True}


def verify_freeze(root=DEFAULT_ROOT):
    root=Path(root)
    path=root/'outputs/freeze_receipt.json'
    if not path.exists(): raise RuntimeError('No freeze receipt; 2026 price access is forbidden.')
    freeze=json.loads(path.read_text())
    if source_hashes(root) != freeze['analysis_source_sha256']:
        raise RuntimeError('Analysis source/config differs from the frozen pre-holdout protocol.')
    for relative,digest in freeze['frozen_evidence_sha256'].items():
        if sha256_file(root/relative) != digest:
            raise RuntimeError(f'Frozen evidence changed: {relative}')
    return freeze


def versions():
    result={'python':platform.python_version()}
    for name in ['numpy','pandas','scipy','statsmodels','pyarrow','matplotlib','reportlab','nbformat','nbclient','nbconvert','pytest']:
        try:result[name]=version(name)
        except PackageNotFoundError:result[name]=None
    return result
