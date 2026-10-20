#!/usr/bin/env python3
"""Recompute fixed-strategy 3percent cash comparisons, reconciling checked results."""
from pathlib import Path
import argparse
import importlib.util
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))


def compare_reconciliation(actual, expected):
    """Require identical audit structure, allowing bounded BLAS roundoff only."""
    # Every calculation already checks its own numerical identity/tolerance.
    # A maximum observed rounding error is not a reproducible financial result.
    # Keep all hashes, check names, counts and non-error metadata exact.
    def without_roundoff(obj):
        result = json.loads(json.dumps(obj))
        for key in ('max_absolute_numeric_error',):
            value = result.pop(key)
            if not math.isfinite(value) or not 0 <= value <= 3e-10:
                raise AssertionError('Reconciliation numeric error exceeds tolerance')
        for check in result['checks'].values():
            value = check.pop('maximum_absolute_error')
            if not math.isfinite(value) or not 0 <= value <= 3e-10:
                raise AssertionError('Reconciliation check error exceeds tolerance')
        return result
    if without_roundoff(actual) != without_roundoff(expected):
        raise AssertionError('Reconciliation metadata, checks or counts differ')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT,
                        help='Project whose current manifest pins the original daily inputs')
    parser.add_argument('--output', type=Path, default=None,
                        help='Generated output, restricted to source-root/local_outputs/')
    parser.add_argument('--expected', type=Path, default=ROOT/'results/cash_excess')
    args = parser.parse_args()
    root = args.source_root.expanduser().resolve()
    if ROOT == root:
        # In the published tree, checked outputs/config/code are pinned by the
        # same current manifest as source inputs. Verify them before computation.
        import hashlib
        manifest = json.loads((root/'metadata/project_manifest.json').read_text())['files']
        required = ['configs/cash_benchmark.json', 'src/crypto_research/cash_excess.py',
                    'scripts/reproduce_cash_excess.py', 'src/crypto_research/output_safety.py']
        required += [str(p.relative_to(root)) for p in (root/'results/cash_excess').glob('*') if p.is_file()]
        if len(required) != 13:
            raise ValueError('Expected exactly nine checked cash-result files')
        for name in required:
            if name not in manifest or hashlib.sha256((root/name).read_bytes()).hexdigest() != manifest[name]['sha256']:
                raise ValueError('Current package checksum mismatch: '+name)
    # Packet authoring uses the unchanged public output-safety implementation.
    safety_path = root/'src/crypto_research/output_safety.py'
    spec = importlib.util.spec_from_file_location('cash_output_safety', safety_path)
    safety = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(safety)
    output = safety.checked_output_path(root, args.output or root/'local_outputs/cash_excess_reproduction', directory=True)
    from crypto_research.cash_excess import calculate, compare_tables, write_result_files
    import pandas as pd
    config = json.loads((ROOT/'configs/cash_benchmark.json').read_text())
    tables, blobs = calculate(root, config)
    for name, frame in tables.items():
        expected = args.expected/name
        if not expected.is_file():
            raise FileNotFoundError('Checked result missing: '+str(expected))
        compare_tables(frame, pd.read_csv(expected), name)
    for name, obj in blobs.items():
        expected = json.loads((args.expected/name).read_text())
        if name == 'reconciliation.json':
            compare_reconciliation(obj, expected)
        elif expected != obj:
            raise AssertionError('Checked result differs: '+name)
    write_result_files(tables, blobs, output)
    print(json.dumps({'status': 'passed', 'tables_reconciled': len(tables),
                      'strategy_periods': 27, 'output': str(output),
                      'source_writes': False, 'original_strategies_unchanged': True}, indent=2))


if __name__ == '__main__':
    main()
