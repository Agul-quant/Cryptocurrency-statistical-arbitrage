#!/usr/bin/env python3
"""Read-only current-layout checksum and evidence checker; never fit or fetch.

Historical publication files remain immutable. This explicit maintenance check
accounts for every one of their 250 current attribution-publication inputs,
including retired reader bytes, rather than weakening old preservation checks.
"""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
MANIFEST_REL = 'provenance/latest_final_reports_20261019.json'
SELF_REL = 'scripts/verify_latest_final_reports.py'
PRIOR_REL = 'provenance/basket_attribution_publication_20261016.json'
OLDER_REL = 'provenance/final_reports_20261016_distribution.json'
HELPER_REL = 'scripts/verify_basket_attribution_publication.py'
EDITION = 'final_reports_20261016'
OLD_EDITION = 'final_reports_20261015'
EVIDENCE = 'provenance/prior_report_evidence_20261015'
BASE = 'b965678aacec9f653c27a41a9351dda3ee913dd6'
ANCHORS = {
    PRIOR_REL: '6510a4e20f0bfdbac0144c2ab9d12a7bc19afa7f63b0385bad676d9c8cfd3ec6',
    OLDER_REL: '126e5eb1e648958ab315ab541b4e2b3bc7c85ffa2ae9397d416f0c566f97fbdc',
    HELPER_REL: '2ff27f8a48ad0e57c3d75c9751ec080a3159d248f3d78c132a42fc5086d1cfde',
    EDITION + '/final_delivery_manifest.json': '4184aae05ba980d8c6568f22e8563cea0b965d54e4982813b41699dc95aca5fd',
    'research/basket_factor_attribution_20261016/outputs/final_delivery_manifest.json': '99344c0eb405c4b434a94dcca7f05d00e789396a44fe2ba448948c310595fde0',
}


def require(ok, label):
    if not ok:
        raise ValueError(label)


def safe(rel):
    require(isinstance(rel, str) and rel and '\\' not in rel
            and all(ord(c) >= 32 for c in rel), 'Unsafe path')
    p = PurePosixPath(rel)
    require(not p.is_absolute() and p.as_posix() == rel
            and all(x not in ('', '.', '..') for x in rel.split('/')), 'Noncanonical path: ' + rel)
    cursor = ROOT
    for part in p.parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), 'Symlink in path: ' + rel)
    require(cursor.resolve().is_relative_to(ROOT.resolve()), 'Escaping path: ' + rel)
    return cursor


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def pin(rel, expected):
    require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected), 'Invalid hash: ' + rel)
    p = safe(rel)
    require(p.is_file() and p.stat().st_size < 100 * 1024 * 1024, 'Missing/oversized file: ' + rel)
    require(sha(p) == expected, 'Changed bytes: ' + rel)
    return p


def pairs(items):
    d = {}
    for k, v in items:
        require(k not in d, 'Duplicate JSON key: ' + k)
        d[k] = v
    return d


def load(rel):
    return json.loads(safe(rel).read_text(encoding='utf-8'), object_pairs_hook=pairs)


def main():
    for rel, expected in ANCHORS.items():
        pin(rel, expected)
    # Import only the unchanged, byte-anchored standard-library inspection
    # helpers. Its own historical verify() is deliberately NOT called, changed,
    # monkeypatched, or made to pretend retired working-tree bytes still exist.
    spec = importlib.util.spec_from_file_location('historical_attribution_inspection', safe(HELPER_REL))
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    require(prior.ROOT == ROOT, 'Inspection helpers resolve a different checkout')
    old = load(PRIOR_REL)
    older = load(OLDER_REL)
    current = load(MANIFEST_REL)
    require(current.get('schema_version') == 1
            and current.get('classification') == 'latest_only_final_reports_distribution'
            and current.get('base_remote_commit') == BASE, 'Unexpected maintenance identity')
    require(current.get('removed_report_directory') == OLD_EDITION
            and current.get('evidence_directory') == EVIDENCE, 'Unexpected layout')
    require(current.get('no_strategy_or_result_changes') is True
            and current.get('no_new_pdf_or_html') is True, 'Maintenance scope changed')
    require(not safe(OLD_EDITION).exists(), 'Superseded reader directory still exists')
    artifacts = prior.sha_map(current['artifact_sha256'], 'current artifact inventory')
    require(MANIFEST_REL not in artifacts and SELF_REL in artifacts, 'Missing verifier/recursive manifest pin')
    require(not any(p.startswith(OLD_EDITION + '/') for p in artifacts), 'Old reader path in current inventory')
    for rel, expected in artifacts.items():
        pin(rel, expected)
    for rel, expected in ANCHORS.items():
        require(artifacts.get(rel) == expected, 'Anchor missing from current inventory: ' + rel)
    declarations = {x['path']: x for x in current['prior_publications']}
    require(set(declarations) == {PRIOR_REL, OLDER_REL}, 'Historical publication inventory changed')
    require(declarations[PRIOR_REL]['sha256'] == ANCHORS[PRIOR_REL]
            and declarations[PRIOR_REL]['inputs_count'] == 250
            and declarations[PRIOR_REL]['artifact_count'] == 111
            and declarations[PRIOR_REL]['baseline_count'] == 139, 'Historical attribution inventory counts changed')
    require(declarations[OLDER_REL]['sha256'] == ANCHORS[OLDER_REL]
            and declarations[OLDER_REL]['inputs_count'] == 140
            and declarations[OLDER_REL]['scope'] == 'historical_metadata_only', 'Older metadata scope changed')
    source = dict(old['artifact_sha256'])
    require(len(source) == 111 and len(old['baseline_preserved_sha256']) == 139
            and not set(source).intersection(old['baseline_preserved_sha256']), 'Historical input identity collision')
    source.update(old['baseline_preserved_sha256'])
    require(len(source) == 250 and len(older['artifact_sha256']) == 140, 'Historical input count mismatch')
    dispositions = current['prior_input_dispositions']
    require(set(dispositions) == set(source), 'Every one of 250 historical inputs needs exactly one disposition')
    counts = {x: 0 for x in ('unchanged', 'relocated', 'alias', 'reader-retired', 'navigation-amended')}
    retired = set()
    for original, expected in source.items():
        record = dispositions[original]
        action = record['disposition']
        require(action in counts and record['prior_sha256'] == expected, 'Incorrect prior disposition: ' + original)
        counts[action] += 1
        if action == 'reader-retired':
            require(original.startswith(OLD_EDITION + '/')
                    and (original.endswith(('.pdf', '.html')) or original == OLD_EDITION + '/README.md'),
                    'Only superseded reader files may be retired: ' + original)
            require(record.get('historical_commit') == BASE and 'current_path' not in record
                    and 'current_sha256' not in record and not safe(original).exists(), 'Invalid retirement: ' + original)
            retired.add(original)
            continue
        destination, digest = record['current_path'], record['current_sha256']
        require(artifacts.get(destination) == digest, 'Unpinned disposition target: ' + original)
        pin(destination, digest)
        if action == 'unchanged':
            require(destination == original and digest == expected, 'Unchanged bytes/path altered: ' + original)
        elif action == 'relocated':
            require(original.startswith(OLD_EDITION + '/') and original.endswith('.json')
                    and destination == EVIDENCE + '/' + original[len(OLD_EDITION) + 1:]
                    and digest == expected, 'Incorrect byte-preserving evidence relocation: ' + original)
        elif action == 'alias':
            require(original.startswith(OLD_EDITION + '/') and original.endswith('.csv')
                    and destination == EDITION + '/' + original[len(OLD_EDITION) + 1:]
                    and digest == expected, 'Incorrect latest-copy evidence alias: ' + original)
        elif action == 'navigation-amended':
            require(original in {'README.md', 'docs/FINAL_REPORTS_PUBLICATION.md', 'docs/ATTRIBUTION_PUBLICATION.md'}
                    and destination == original and digest != expected, 'Unexpected navigation amendment: ' + original)
    require(counts['relocated'] == 19 and counts['alias'] == 26 and counts['reader-retired'] == 7
            and counts['navigation-amended'] == 3 and counts['unchanged'] == 195, 'Disposition totals changed')
    require(set(current['retired_reader_paths']) == retired, 'Retired reader inventory incomplete')
    relocated_actual = {p.relative_to(ROOT).as_posix() for p in safe(EVIDENCE).rglob('*') if p.is_file()}
    relocated_expected = {r['current_path'] for r in dispositions.values() if r['disposition'] == 'relocated'}
    require(relocated_actual == relocated_expected, 'Provenance-only evidence contains unexpected/missing files')
    require(all(p.endswith('.json') for p in relocated_actual), 'Reader copy in provenance-only directory')
    require(current['latest_report_source_seal'] == old['report_source_seal']
            and current['diagnostic_source_seal'] == old['diagnostic_source_seal'], 'Source seals changed')
    seal, overlap = prior.verify_seal(old['report_source_seal'], artifacts, 'latest report source seal')
    sealed = set()
    sealroot = PurePosixPath(old['report_source_seal']['path']).parent
    for rel, digest in seal['artifact_sha256'].items():
        full = (sealroot / rel).as_posix()
        if artifacts.get(full) == digest:
            sealed.add(full)
    for original, record in old['report_source_aliases'].items():
        require(seal['artifact_sha256'].get(original) == record['sha256']
                and artifacts.get(record['distributed_path']) == record['sha256'], 'Sealed report alias changed')
        sealed.add(record['distributed_path'])
    # This helper explicitly verifies all 38 published owned scientific files,
    # the three declared deterministic index omissions, frozen code, source
    # metadata, calendar/coin/243-coefficient slots and custody relationships.
    diagnostic, scientific_coins, scientific_coefficients = prior.verify_diagnostic(old, artifacts)
    prior.declared_scope(current)
    reports = current['reports']
    require(len(reports) == 3 and {r['period'] for r in reports} == set(prior.PERIODS), 'Three report periods required')
    byperiod = {r['period']: r for r in old['reports']}
    expected_pdfs, expected_htmls = set(), set()
    original_queries_checked = 0
    csvlinks = 0
    for report in reports:
        period = report['period']
        original_report = byperiod[period]
        for field in ('title', 'period', 'pdf', 'html', 'snapshot', 'coin_export', 'coefficient_export'):
            require(report[field] == original_report[field], 'Current report identity changed: ' + period + '/' + field)
        expected_pdfs.add(report['pdf'])
        expected_htmls.add(report['html'])
        for field in ('pdf', 'html', 'snapshot', 'coin_export', 'coefficient_export'):
            require(report[field] in artifacts and report[field] in sealed, 'Unsealed report target: ' + field)
        with safe(report['pdf']).open('rb') as f:
            require(f.read(5) == b'%PDF-', 'Invalid PDF')
        prior.verify_html(report['html'])
        snapshot = load(report['snapshot'])
        require(snapshot['buildStatus'] == 'complete', 'Incomplete report')
        q = snapshot['queries']
        require(prior.NEW_QUERIES <= set(q), 'Attribution queries missing')
        for query, count in (('basket_attribution_summary', 9), ('basket_attribution_diagnostics', 9), ('basket_attribution_methods', 1)):
            require(len(q[query]['rows']) == count and all(x['period'] == period for x in q[query]['rows']), 'Query period/count mismatch')
        methods = q['basket_attribution_methods']['rows'][0]
        require(methods['protocol_sha256'] == artifacts[prior.DIAGNOSTIC_REL + '/protocol.json']
                and methods['payload_sha256'] == artifacts[prior.DIAGNOSTIC_REL + '/outputs/report_payload.json'], 'Query scientific source mismatch')
        coins, coefficients = prior.csv_rows(report['coin_export']), prior.csv_rows(report['coefficient_export'])
        require(coins == [r for r in scientific_coins if r['period'] == period]
                and coefficients == [r for r in scientific_coefficients if r['period'] == period], 'Report scientific export projection changed')
        prior.slots(coins, period)
        prior.slots(coefficients, period, True)
        prior.slots(q['basket_attribution_coins']['rows'], period)
        prior.slots(q['basket_attribution_coefficients']['rows'], period, True)
        prior.snapshot_matches_csv(q['basket_attribution_coins']['rows'], coins, ('strategy_id', 'period', 'symbol'), period + '/coins')
        prior.snapshot_matches_csv(q['basket_attribution_coefficients']['rows'], coefficients, ('strategy_id', 'period', 'term'), period + '/coefficients')
        pins_rel = (PurePosixPath(report['html']).parent / 'attribution_source_pins.json').as_posix()
        require(pins_rel in artifacts, 'Report source pins missing')
        pins = load(pins_rel)
        require(pins['period'] == period and pins['frozen_identities'] == list(prior.IDS)
                and pins['snapshot_sha256'] == artifacts[report['snapshot']], 'Report source identities changed')
        for rel, digest in prior.sha_map(pins['input_sha256'], 'report science pins').items():
            require(artifacts.get(prior.DIAGNOSTIC_REL + '/' + rel) == digest, 'Report science input changed')
        historic = original_report['prior_snapshot']
        require(report['historical_prior_snapshot'] == historic
                and report['prior_snapshot'] == dispositions[historic]['current_path']
                and dispositions[historic]['disposition'] == 'relocated', 'Incorrect archived snapshot mapping')
        previous = load(report['prior_snapshot'])
        require({k: v for k, v in q.items() if k not in prior.NEW_QUERIES} == previous['queries'], 'Original reviewed query changed')
        original_queries_checked += len(previous['queries'])
        # Older snapshots are provenance only, not live link bases. Map any
        # older CSV target through its explicit checksum alias, never silently
        # accept a dangling older folder link.
        historic_folder = PurePosixPath(historic).parent
        for text in prior.strings(previous):
            for target in prior.markdown_targets(text):
                from urllib.parse import unquote, urlsplit
                u = urlsplit(target)
                if not u.scheme and not u.netloc and u.path.lower().endswith('.csv'):
                    from posixpath import normpath
                    oldtarget = normpath((historic_folder / unquote(u.path)).as_posix())
                    require(oldtarget in dispositions and dispositions[oldtarget]['disposition'] == 'alias', 'Unmapped historical CSV link: ' + oldtarget)
                    pin(dispositions[oldtarget]['current_path'], dispositions[oldtarget]['current_sha256'])
                    csvlinks += 1
        folder = safe(report['html']).parent
        for text in prior.strings(snapshot):
            for target in prior.markdown_targets(text):
                prior.link_target(folder, target, report['snapshot'], csv_only=True)
    require({p for p in artifacts if p.endswith('.pdf')} == expected_pdfs, 'Maintenance inventory has extra reader PDFs')
    require({p for p in artifacts if p.endswith('.html')} == expected_htmls, 'Maintenance inventory has extra reader HTML')
    actualpdf = {p.relative_to(ROOT).as_posix() for p in safe(EDITION).rglob('*.pdf')}
    actualhtml = {p.relative_to(ROOT).as_posix() for p in safe(EDITION).glob('*/*.html')}
    require(actualpdf == expected_pdfs and actualhtml == expected_htmls, 'Latest edition reader count differs from three pairs')
    for rel in ('README.md', 'docs/FINAL_REPORTS_PUBLICATION.md', 'docs/ATTRIBUTION_PUBLICATION.md'):
        require(rel in artifacts, 'Current navigation unpinned')
        p = safe(rel)
        for target in prior.markdown_targets(p.read_text(encoding='utf-8')):
            prior.link_target(p.parent, target, rel)
    for rel in old['required_relative_targets']:
        require(rel in artifacts, 'Required current export omitted')
        safe(rel).is_file() or require(False, 'Missing current export')
    return dict(status='PASS', latest_reader_reports=3, reader_pdf_html_pairs=3,
                historical_inputs_explicitly_accounted=250, dispositions=counts,
                original_query_objects_unchanged=original_queries_checked,
                historical_csv_alias_links_verified=csvlinks, report_seal_overlap=overlap,
                retired_reader_bytes_available_only_in_git_history=True,
                strategy_results_or_scientific_outputs_changed=False,
                new_prices_or_trading_models=False, **diagnostic)


if __name__ == '__main__':
    try:
        print(json.dumps(main(), indent=2, sort_keys=True))
    except Exception as exc:
        print('Latest-only report verification FAILED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
