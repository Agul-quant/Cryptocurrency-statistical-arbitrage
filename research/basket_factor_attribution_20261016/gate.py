"""Owned, read-only-parent access gate for a finite post-hoc diagnostic study."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat()

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')

def assert_frozen(operation='diagnostic source access'):
    freeze = json.loads((ROOT/'outputs/access_freeze.json').read_text())
    if freeze.get('authorized') is not True:
        raise RuntimeError('This finite diagnostic study has not been released')
    for rel, digest in freeze['code_sha256'].items():
        if sha(ROOT/rel) != digest:
            raise RuntimeError('Changed diagnostic code after freeze: '+rel)
    for rel, key in [('protocol.json','protocol_sha256'),('required_source_pins.json','source_pins_sha256')]:
        if sha(ROOT/rel) != freeze[key]:
            raise RuntimeError('Changed diagnostic design/source list: '+rel)
    return freeze

def record_access(operation):
    freeze = assert_frozen(operation)
    path = ROOT/'outputs/source_access_receipt.json'
    if not path.exists():
        save(path, {'status':'first_additional_diagnostic_access_after_owned_freeze',
                    'created_at_utc':now(), 'operation':operation,
                    'access_freeze_sha256':sha(ROOT/'outputs/access_freeze.json'),
                    'protocol_sha256':freeze['protocol_sha256'],
                    'classification':'post-hoc diagnostics on previously inspected history',
                    'no_new_prices_no_strategy_rerun_no_reselection':True})
    else:
        receipt = json.loads(path.read_text())
        if receipt['access_freeze_sha256'] != sha(ROOT/'outputs/access_freeze.json'):
            raise RuntimeError('Access receipt belongs to a different analysis freeze')
    return path
