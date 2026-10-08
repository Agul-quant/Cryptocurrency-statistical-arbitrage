"""Add the audited universe story to a separate copy of the original report.

Reads locked results and existing figures only. No download, trading, strategy
selection, notebook execution, or original-project write is performed.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ORIGINAL = Path('/Users/cosdis/Desktop/job/quant_projects/crypto_stat_arb')
REVISION = Path(__file__).resolve().parent
ZIP = ORIGINAL.parent / 'crypto_stat_arb_project.zip'

BLOCKS = [
    ('SubCustom', 'Start with the course question'),
    ('BodyCustom', 'The assignment asks whether momentum or reversal in cryptocurrency price-volume data can survive trading costs. It permits a flexible research design but does not prescribe any coin names, a universe size, or an asset-selection rule. The original project operationalized that question with an hourly, cross-sectional backtest and a fixed universe before comparing strategy parameters.'),
    ('SubCustom', 'How the eight coins were defined'),
    ('BodyCustom', 'The configured instruments are BTCUSDT, ETHUSDT, LTCUSDT, ADAUSDT, LINKUSDT, DOGEUSDT, DOTUSDT and SOLUSDT. The retained report describes them as eight present-day recognizable coins and a <b>purposive survivor sample</b>. They were specified directly in the configuration and downloader; they were not produced by a recorded market-cap, liquidity, correlation or profitability screen. The precise reason for choosing each coin, or choosing eight rather than another number, is not documented.'),
    ('BodyCustom', 'Using a single exchange and the same USDT quote currency gives a consistent source and numeraire. The eight pairs have archived hourly data from December 2021 through December 2025, subject to the disclosed halt and metadata exceptions. These are practical advantages of the setup, not evidence that they were formal historical selection criteria.'),
    ('SubCustom', 'What was the bigger pool?'),
    ('BodyCustom', '<b>No larger candidate pool was enumerated in the retained project.</b> There is no recorded initial coin count, rejected-asset list, ranking, or point-in-time eligibility table. All Binance spot USDT pairs would be a natural broader opportunity set for a different study, but the original project did not demonstrate that it screened that set. It would therefore be incorrect to claim that these were the eight most liquid coins or that only eight survived a market-wide screen.'),
    ('SubCustom', 'Data checking is not universe selection'),
    ('BodyCustom', 'Acquisition started with the eight configured pairs and verified 392 monthly archives: 49 per pair. The subsequent audit checked coverage, checksums, duplicates, OHLCV consistency and the documented exceptions. It did not compare these eight with excluded coins. The 18 candidates in the original research were <b>strategy configurations</b> (nine momentum and nine reversal), not 18 competing coins; 2024 selected signal parameters while the asset universe stayed fixed.'),
    ('SubCustom', 'What this means for the story'),
    ('BodyCustom', 'The findings are conditional on this fixed survivor universe, not a point-in-time representation of the full crypto market. Failed, delisted and newly listed alternatives were not represented, so generalization is limited. This revised report preserves the original 18-configuration study and its initial 2025 evaluation; later exploratory scans and the 2026 historical holdout remain separate.'),
    ('SmallCustom', '<b>Universe evidence:</b> supplied ClassProject.docx; configs/research.toml; src/crypto_stat_arb/data.py; data/raw/manifest.json; data/processed/data_quality.json; README.md; and the preserved report implementation. No retrospective asset-screening story has been invented.'),
]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def original_snapshot():
    # Bytecode and pytest cache are execution byproducts, not research artifacts.
    values = {}
    for path in sorted(ORIGINAL.rglob('*')):
        if path.is_file() and not {'__pycache__', '.pytest_cache'}.intersection(path.parts):
            values[str(path.relative_to(ORIGINAL))] = digest(path)
    values['../crypto_stat_arb_project.zip'] = digest(ZIP)
    return values


def main():
    before = original_snapshot()
    source_path = ORIGINAL / 'src/crypto_stat_arb/reporting.py'
    source = source_path.read_text()
    anchor = "    # 2: point-in-time partitions and actual data status."
    assert source.count(anchor) == 1
    # Only the PDF authoring function's section numbers change. All metrics,
    # existing prose and frozen figures are retained.
    for number in range(8, 1, -1):
        source = source.replace(f"    title({number}, ", f"    title({number + 1}, ")
    insertion = ["    title(2, 'Research story and choice of universe')"]
    for style, text in BLOCKS:
        insertion.append(f"    add({text!r}, {style!r})")
    insertion.append('    page()\n')
    source = source.replace(anchor, '\n'.join(insertion) + '\n' + anchor)
    source = source.replace('if count!=8:', 'if count!=9:')
    source = source.replace('fixed eight-page design:', 'revised nine-page design:')
    source = source.replace('notebook and eight-page course PDF.', 'notebook and revised nine-page course PDF.')
    copied = REVISION / 'reporting_with_universe_story.py'
    copied.write_text(source)
    spec = importlib.util.spec_from_file_location('revised_reporting', copied)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = module._load(ORIGINAL)
    figures = {key: str(ORIGINAL / 'reports/figures' / name) for key, name in {
        'validation': 'validation_sharpe.png',
        'equity': 'test_equity_drawdown.png',
        'robustness': 'cost_timing_stress.png',
        'activity': 'activity_diagnostic.png',
    }.items()}
    result = module._render_pdf(REVISION, data, figures)
    after = original_snapshot()
    assert before == after, 'Original research artifacts changed.'
    text = ['# Research story and choice of universe']
    for style, body in BLOCKS:
        body = body.replace('<b>', '**').replace('</b>', '**')
        text.append(('## ' if style == 'SubCustom' else '') + body)
    (REVISION / 'universe_story.md').write_text('\n\n'.join(text) + '\n')
    audit = {
        'change': 'Added one universe-story page after the original summary; preserved original findings and figures.',
        'source_project': str(ORIGINAL),
        'source_report_sha256': before['reports/project_report.pdf'],
        'source_reporting_sha256': before['src/crypto_stat_arb/reporting.py'],
        'original_artifacts_unchanged': before == after,
        'original_file_count_excluding_caches': len(before) - 1,
        'original_zip_sha256': before['../crypto_stat_arb_project.zip'],
        'revised_report': str(result),
        'revised_report_sha256': digest(result),
        'larger_coin_pool_documented': False,
        'strategy_or_data_reselection': False,
        'fresh_price_access': False,
    }
    (REVISION / 'revision_manifest.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
