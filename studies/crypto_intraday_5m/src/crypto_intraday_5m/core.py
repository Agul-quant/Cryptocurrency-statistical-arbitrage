"""JSON, fingerprints and preservation shared by the isolated pilot."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,tomllib,platform
from importlib.metadata import version,PackageNotFoundError
import numpy as np
import pandas as pd

DEFAULT_ROOT=Path(__file__).resolve().parents[2]


def utc_now():return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write_json(path,value):
    def clean(x):
        if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
        if isinstance(x,(list,tuple)):return [clean(v) for v in x]
        if isinstance(x,(pd.Timestamp,Path)):return str(x)
        if isinstance(x,np.bool_):return bool(x)
        if isinstance(x,np.integer):return int(x)
        if isinstance(x,(np.floating,float)):return float(x) if np.isfinite(x) else None
        return x
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(clean(value),sort_keys=True,indent=2,allow_nan=False)+'\n')
    temporary.replace(path)


def load_config(root=DEFAULT_ROOT):
    with (Path(root)/'configs/research.toml').open('rb') as stream:config=tomllib.load(stream)
    if config['data']['interval']!='5m' or config['research']['primary_cost_bps']!=20:
        raise ValueError('This declared pilot uses actual5m bars and20bps primary costs.')
    return config


def source_hashes(root=DEFAULT_ROOT):
    root=Path(root);files=[root/'configs/research.toml',root/'pyproject.toml']
    files += [p for p in (root/'src/crypto_intraday_5m').rglob('*.py') if p.name!='reporting.py']
    return {str(p.relative_to(root)):sha256_file(p) for p in sorted(files)}


def verify_preservation(root=DEFAULT_ROOT,require_present=True):
    receipt=json.loads((Path(root)/'outputs/preservation.json').read_text());result={}
    exclude={'tmp','__pycache__','.pytest_cache','.git','build','dist'}
    for folder,record in receipt['projects'].items():
        p=Path(folder)
        if not p.exists():
            if require_present:raise FileNotFoundError(f'Preserved project unavailable: {folder}')
            result[folder]={'status':'not_locally_available','snapshot_file_count':record['file_count']};continue
        for rel,digest in record['files_sha256'].items():
            f=p/rel
            if not f.is_file() or sha256_file(f)!=digest:raise RuntimeError(f'Preserved file changed: {folder}/{rel}')
        actual={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and
                not any(part in exclude or part.endswith('.egg-info') for part in f.relative_to(p).parts)}
        if actual!=set(record['files_sha256']):raise RuntimeError(f'Preserved project file inventory changed: {folder}')
        if sha256_file(record['bundle_path'])!=record['bundle_sha256']:raise RuntimeError('Preserved ZIP changed.')
        result[folder]={'status':'unchanged','file_count':record['file_count'],'bundle_unchanged':True}
    return result


def versions():
    out={'python':platform.python_version()}
    for name in ['numpy','pandas','scipy','statsmodels','pyarrow','matplotlib','reportlab','nbclient','nbformat','pytest']:
        try:out[name]=version(name)
        except PackageNotFoundError:out[name]=None
    return out
