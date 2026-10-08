"""Rebuild the revised original report locally from pinned existing results.

No legacy host paths, original outer ZIPs, downloads or strategy selection are
used. New output lives under local_outputs/, not inside a frozen study.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'studies/crypto_stat_arb'
REVISION = ROOT / 'studies/crypto_stat_arb_report_revision'


def main():
    manifest = json.loads((ROOT / 'provenance/study_snapshot.json').read_text())['study_files']
    # Verify every actual reporting input before importing the preserved builder.
    inputs = ['outputs/' + n for n in [
        'experiments.csv', 'final_metrics.csv', 'annual_metrics.csv',
        'activity_diagnostics.csv', 'selected_returns.parquet',
        'selection.json', 'run_manifest.json',
    ]] + ['data/processed/data_quality.json']
    names = {
        'validation': 'validation_sharpe.png', 'equity': 'test_equity_drawdown.png',
        'robustness': 'cost_timing_stress.png', 'activity': 'activity_diagnostic.png',
    }
    inputs += ['reports/figures/' + n for n in names.values()]
    for rel in inputs:
        expected = manifest['crypto_stat_arb'][rel]['sha256']
        actual = hashlib.sha256((STUDY / rel).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f'Pinned reporting input changed: {rel}')
    rel = 'reporting_with_universe_story.py'
    source = REVISION / rel
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['crypto_stat_arb_report_revision'][rel]['sha256']:
        raise RuntimeError('Pinned universe-report source changed.')
    spec = importlib.util.spec_from_file_location('local_universe_report', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = module._load(STUDY)
    figures = {key: str(STUDY / 'reports/figures' / name) for key, name in names.items()}
    output = module._render_pdf(ROOT / 'local_outputs/universe_report', results, figures)
    print(output)


if __name__ == '__main__':
    main()
