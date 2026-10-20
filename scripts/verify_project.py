#!/usr/bin/env python3
"""Verify the current research package without network access or third-party packages."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlparse

MANIFEST = 'metadata/project_manifest.json'
IDS = {'A01','A02','A03','A04','B01','B03','B04','B05','B06'}

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def safe_path(root: Path, rel: str) -> Path:
    if not isinstance(rel, str) or '\\' in rel or Path(rel).is_absolute() or '..' in Path(rel).parts:
        raise ValueError(f'Unsafe package path: {rel!r}')
    p = root / rel
    if p.is_symlink() or not p.resolve().is_relative_to(root):
        raise ValueError(f'Package path escapes root: {rel}')
    return p

def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def verify(root: Path) -> dict:
    root = root.resolve()
    manifest = json.loads((root / MANIFEST).read_text())
    assert manifest['schema_version'] == 1
    assert manifest['strategy_ids'] == sorted(IDS)
    assert len(manifest['periods']) == 3
    files = manifest['files']
    assert MANIFEST not in files, 'Manifest cannot pin itself'
    for rel, pin in sorted(files.items()):
        p = safe_path(root, rel)
        assert p.is_file(), f'Missing file: {rel}'
        assert p.stat().st_size == pin['bytes'], f'Size mismatch: {rel}'
        assert digest(p) == pin['sha256'], f'Checksum mismatch: {rel}'
    pdfs = sorted(p for p in files if p.endswith('.pdf'))
    assert len(pdfs) == 3 and all(p.startswith('final_reports/') for p in pdfs), pdfs
    htmls = sorted(p for p in files if p.startswith('final_reports/') and p.endswith('.html'))
    assert len(htmls) == 3
    for rel in pdfs:
        assert (root / rel).read_bytes().startswith(b'%PDF-'), rel
    assert any(p.startswith('src/') and p.endswith('.py') for p in files), 'Python source absent'
    assert '.gitattributes' in files
    attributes = (root / '.gitattributes').read_text()
    assert 'linguist-generated' in attributes and 'final_reports/' in attributes
    grid = json.loads((root/'configs/configuration_space.json').read_text())
    assert grid['unique_case_count'] == len(grid['cases']) == 169
    assert len({row['experiment_id'] for row in grid['cases']}) == 169
    registry = json.loads((root/'configs/frozen_strategies.json').read_text())
    assert registry['order'] == sorted(IDS)
    assert {row['comparison_id'] for row in registry['strategies']} == IDS
    assert all(len(row['symbols']) == len(set(row['symbols'])) == 8 for row in registry['strategies'])
    assert len({coin for row in registry['strategies'] for coin in row['symbols']}) == 21
    dataset = json.loads((root/'metadata/dataset.json').read_text())
    assert dataset['n_full_search_slots'] == 22 and dataset['n_frozen_basket_union_slots'] == 21
    assert dataset['n_endpoints'] == 43824 and len(dataset['raw_schema']) == 12
    assert dataset['raw_ohlcv_archives_included'] is False
    assert manifest['data_universe_slots'] == 22 and manifest['frozen_strategy_union_slots'] == 21
    inventory = read_rows(root/'data/universe.csv')
    assert len(inventory) == 30
    assert sum(row['in_tiered_basket_search_22'] == 'True' for row in inventory) == 22
    assert sum(row['in_frozen_nine_union_21'] == 'True' for row in inventory) == 21
    protocol = json.loads((root/'configs/research_protocol.json').read_text())
    assert set(protocol['periods']) == set(manifest['periods'])
    assert protocol['primary_cost_bps'] == manifest['primary_cost_bps'] == 20
    assert protocol['primary_execution_lag'] == manifest['primary_execution_lag'] == 1
    cash = json.loads((root/'configs/cash_benchmark.json').read_text())
    assert cash['annual_nominal_rate'] == 0.03 and cash['calendar_days_per_fixed_year'] == 365
    assert cash['day_count'] == 'ACT/365F' and cash['daily_compounding'] is True
    assert cash['interest_credited_to_strategy'] is False and cash['benchmark_is_not_actual_instrument_yield'] is True
    assert cash['bootstrap']['replications'] == 4000 and cash['bootstrap']['block_days'] == 28
    assert cash['bootstrap']['seed'] == 20261016 and cash['bootstrap']['synchronized_nine'] is True
    for relative,pin in cash['input_pins'].items():
        assert relative in files and files[relative]['sha256'] == pin['sha256']
        assert files[relative]['bytes'] == pin['bytes']
    c = 0.03/365
    performance = read_rows(root/'results/cash_excess/performance.csv')
    assert len(performance) == 27
    for row in performance:
        n = manifest['periods'][row['period']]['days']
        assert int(row['n_calendar_days']) == n and row['cash_interest_credited_to_strategy'] == 'False'
        for value,expected in [
            (row['cash_daily_return'],c),
            (row['cash_compounded_return'],math.expm1(n*math.log1p(c))),
            (row['cash_effective_365_day_return'],math.expm1(365*math.log1p(c))),
            (row['wealth_relative_excess_return'],math.expm1(math.log1p(float(row['raw_net_return']))-n*math.log1p(c))),
            (row['annual_arithmetic_mean_excess'],float(row['raw_annual_arithmetic_return'])-0.03),
            (row['arithmetic_excess_annual_volatility'],float(row['raw_annual_daily_volatility'])),
            (row['cash_excess_sharpe'],float(row['annual_arithmetic_mean_excess'])/float(row['raw_annual_daily_volatility']))]:
            assert math.isclose(float(value),expected,rel_tol=1e-10,abs_tol=1e-12), (row['strategy_id'],row['period'],value,expected)
    mean_rows = read_rows(root/'results/cash_excess/mean_excess_inference.csv')
    assert len(mean_rows) == 27 and all(row['cash_excess_mean_multiplicity_family_size'] == '27' for row in mean_rows)
    assert all(row['original_acceptance_retested'] == 'False' for row in mean_rows)
    for name,count in [('joint_coefficients.csv',243),('matched_btc_coefficients.csv',54),('btc_full_period_coefficients.csv',54)]:
        rows=read_rows(root/'results/cash_excess'/name);assert len(rows) == count
        groups={}
        for row in rows:
            groups.setdefault((row['strategy_id'],row['period']),[]).append(row)
            if row['term'] != 'alpha_annual':
                for raw,adjusted in [('raw_estimate','cash_excess_estimate'),('raw_se','cash_excess_se'),('raw_ci95_low','cash_excess_ci95_low'),('raw_ci95_high','cash_excess_ci95_high')]:
                    assert math.isclose(float(row[raw]),float(row[adjusted]),rel_tol=1e-10,abs_tol=1e-12), (name,row['strategy_id'],row['period'],row['term'])
            if name == 'joint_coefficients.csv':
                assert row['cash_excess_coefficient_multiplicity_family_size'] == '243'
        assert len(groups) == 27
        for key,group in groups.items():
            alpha=next(row for row in group if row['term'] == 'alpha_annual')
            beta_sum=sum(float(row['raw_estimate']) for row in group if row['term'] != 'alpha_annual')
            expected=float(alpha['raw_estimate'])+0.03*(beta_sum-1)
            assert math.isclose(float(alpha['cash_excess_estimate']),expected,rel_tol=1e-10,abs_tol=1e-12), (name,key)
    cash_methods=json.loads((root/'results/cash_excess/methods.json').read_text())
    assert cash_methods['interest_credited_to_strategy'] is False
    assert cash_methods['strategy_trades_costs_selections_risk_limits_and_original_acceptance_tests_unchanged'] is True
    checked_rows = 0
    for contract in manifest.get('table_contracts', []):
        path = safe_path(root, contract['path'])
        assert contract['path'] in files
        rows = read_rows(path)
        assert len(rows) == contract['rows'], (contract['path'], len(rows), contract['rows'])
        if 'unique_keys' in contract:
            keys = [tuple(row[c] for c in contract['unique_keys']) for row in rows]
            assert len(set(keys)) == len(keys), f'Duplicate rows: {path}'
        for column, expected in contract.get('required_values', {}).items():
            observed = {row[column] for row in rows}
            assert observed == set(expected), (contract['path'], column, observed)
        for column in contract.get('finite_columns', []):
            assert all(math.isfinite(float(row[column])) for row in rows), (contract['path'], column)
        checked_rows += len(rows)
    if 'attribution_reconciliation' in manifest:
        rec = manifest['attribution_reconciliation']
        contributions = read_rows(root / rec['attribution_path'])
        totals = read_rows(root / rec['totals_path'])
        sums = {}
        for row in contributions:
            key = (row[rec['id_column']], row['period'])
            sums[key] = sums.get(key, 0.0) + float(row[rec['net_contribution_column']])
        assert len(sums) == 27
        for row in totals:
            key = (row[rec['id_column']], row['period'])
            assert math.isclose(sums[key], float(row[rec['total_return_column']]), rel_tol=1e-10, abs_tol=1e-10), key
    # Relative links in the reader-facing Markdown must resolve within this package.
    link_count = 0
    for rel in manifest.get('link_check_markdown', ['README.md']):
        p = safe_path(root, rel)
        for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)', p.read_text()):
            target = unquote(target.split('#')[0])
            if not target or urlparse(target).scheme or target.startswith('//'):
                continue
            q = (p.parent / target).resolve()
            assert q.is_relative_to(root) and q.exists(), f'Broken link in {rel}: {target}'
            link_count += 1
    allowed_directories = {'src','configs','data','results','tests','scripts','final_reports','metadata','docs','licenses'}
    allowed_root_files = {'README.md','NOTICE.md','requirements.lock.txt','.gitignore','.gitattributes'}
    assert all(p in allowed_root_files or Path(p).parts[0] in allowed_directories for p in files)
    return {'status':'PASS','files_verified':len(files),'table_rows_checked':checked_rows,
            'final_reports':len(pdfs),'relative_links_checked':link_count,
            'network_access':False,'trading_or_price_acquisition':False}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2, sort_keys=True))

if __name__ == '__main__':
    main()
