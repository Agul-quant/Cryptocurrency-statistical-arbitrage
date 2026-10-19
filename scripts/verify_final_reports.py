#!/usr/bin/env python3
"""Read-only undated-layout checker; no model fitting, network, or file writes.

Explicitly verify all 65 byte-preserving reader-directory relocations, the four
narrow navigation/custody amendments, and all 250 historical input dispositions.
Historical manifests and inspection helpers are kept byte-identical; original
path references are interpreted only by this declared prefix mapping.
"""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
MANIFEST_REL = 'provenance/final_reports_layout.json'
PREVIOUS_REL = 'provenance/latest_final_reports_20261019.json'
SELF_REL = 'scripts/verify_final_reports.py'
PREVIOUS_SELF_REL = 'scripts/verify_latest_final_reports.py'
PRIOR_REL = 'provenance/basket_attribution_publication_20261016.json'
OLDER_REL = 'provenance/final_reports_20261016_distribution.json'
HELPER_REL = 'scripts/verify_basket_attribution_publication.py'
SOURCE_EDITION = 'final_reports_20261016'
EDITION = 'final_reports'
OLD_EDITION = 'final_reports_20261015'
EVIDENCE = 'provenance/prior_report_evidence_20261015'
BASE = 'b965678aacec9f653c27a41a9351dda3ee913dd6'
LAYOUT_BASE = '4bb4d39b2e3956b4ff1b597d792953faae78dd56'
PREVIOUS_PINS = {
    '971eb5baa87f502d3e792395e37acd02bfddaf3a9f939fe293b6d4d875c7b2b3',
    '5f9ee32b96e48f8a2efffb3b8837bc8addbbb15dd3cfc059649185d9b18d0c4b',
}
AMENDED = {'README.md', 'docs/FINAL_REPORTS_PUBLICATION.md',
           'docs/ATTRIBUTION_PUBLICATION.md', '.gitattributes'}
ANCHORS = {
    PRIOR_REL: '6510a4e20f0bfdbac0144c2ab9d12a7bc19afa7f63b0385bad676d9c8cfd3ec6',
    OLDER_REL: '126e5eb1e648958ab315ab541b4e2b3bc7c85ffa2ae9397d416f0c566f97fbdc',
    HELPER_REL: '2ff27f8a48ad0e57c3d75c9751ec080a3159d248f3d78c132a42fc5086d1cfde',
    SOURCE_EDITION + '/final_delivery_manifest.json': '4184aae05ba980d8c6568f22e8563cea0b965d54e4982813b41699dc95aca5fd',
    'research/basket_factor_attribution_20261016/outputs/final_delivery_manifest.json': '99344c0eb405c4b434a94dcca7f05d00e789396a44fe2ba448948c310595fde0',
}

# A narrowly bounded GitHub-language-statistics maintenance amendment.
LANGUAGE_BASE = 'a3d7fdbfecfa681e41e92b7b52771446970ceb92'
PRE_LANGUAGE_ATTRIBUTES_SHA256 = '839d70ef3ee6ea032411a7594bdfbd50b98005489bc704ef52c006fe448b82e3'
PRE_LANGUAGE_VERIFIER_SHA256 = '2f1ba419ab6b4601ca409281737de558bb6647e2b4ab82b480351e7f98497228'
PRE_LANGUAGE_MANIFESTS = {'public': 'a08af129e4b562307be056bee5b86c47e6aa8269023493a2feb779ccd2e772b7', 'owner': '41dce50fe8d2a54347a12881604f44fe3a5a5f81e027afcd1387bd01d86eb79a'}
LINGUIST_BLOCK = b'\n# Generated reports must not outweigh the Python research engine in language statistics.\n# Keep all report files; these attributes affect GitHub Linguist metadata only.\nfinal_reports/**/*.html linguist-generated\nstudies/crypto_intraday_5m/notebooks/intraday_5m_research.html linguist-generated\nstudies/crypto_stat_arb/notebooks/crypto_stat_arb_research.html linguist-generated\nstudies/crypto_stat_arb/outputs/followups/time_scale_scan/time_scale_research.html linguist-generated\nstudies/crypto_stat_arb_extensions/notebooks/expanded_crypto_research.html linguist-generated\n# Saved executed report companions contain large embedded outputs; do not count them as engine source.\nstudies/crypto_intraday_5m/notebooks/intraday_5m_research.ipynb -linguist-detectable\nstudies/crypto_stat_arb/notebooks/crypto_stat_arb_research.ipynb -linguist-detectable\nstudies/crypto_stat_arb/outputs/followups/time_scale_scan/time_scale_research.ipynb -linguist-detectable\nstudies/crypto_stat_arb_extensions/notebooks/expanded_crypto_research.ipynb -linguist-detectable\n'
EXCLUDED_REPORT_ASSETS = {'final_reports/01_development/01_development_and_robustness.html': '5598dbeab3ac063f292084716ed91edc8c417753e9801ed5be6d1b40455ebafb', 'final_reports/02_validation/02_validation_and_frozen_selection.html': '19290cb9fd0b41e06744eaf5a1878845e1709413daf9d9778510ff46b6541f83', 'final_reports/03_2026_evaluation/03_2026_evaluation_and_conclusions.html': 'b8de1807f1d915a22ca27fb89cec25ae135b569b0af9632c50f4ee735f3558ab', 'studies/crypto_intraday_5m/notebooks/intraday_5m_research.html': '602e893af1ee0663e798e7becfd56f5082394835d1c25cc217eaacbb7ee0d4f2', 'studies/crypto_intraday_5m/notebooks/intraday_5m_research.ipynb': 'b78f673920908c3acbd81589294474a700ff2e49b4daaa1acc00d9a9d320bcfa', 'studies/crypto_stat_arb/notebooks/crypto_stat_arb_research.html': '1a83fe6686d0e964c86eaed86a891a781fb44d628073a1ee05370c9f5c51c585', 'studies/crypto_stat_arb/notebooks/crypto_stat_arb_research.ipynb': '45cab6f6d78a17907487cdf5129bd8fe7c1866ca20133cc8576924ef07ea5c5b', 'studies/crypto_stat_arb/outputs/followups/time_scale_scan/time_scale_research.html': '745bf71bd0d8e9f2afe5f417fb243a52b8a360fb5a2f0f6efaf565e9b3bd9863', 'studies/crypto_stat_arb/outputs/followups/time_scale_scan/time_scale_research.ipynb': '965450414d1dd0d203a34fc1397e97b4a686171c697c927d5bfe3e7eaa2dc617', 'studies/crypto_stat_arb_extensions/notebooks/expanded_crypto_research.html': 'adebd9ba82ea56e4de84eaf76cfc21175ac469fa4cb03ea6eaa51374a63b4145', 'studies/crypto_stat_arb_extensions/notebooks/expanded_crypto_research.ipynb': 'd2f8fafe96236bebd7b1a31c000fa004784998c3ea4063e67ed495284964057e'}


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


def moved(rel):
    """The sole authorized path transformation; no filename/hash substitutions."""
    return EDITION + rel[len(SOURCE_EDITION):] if rel.startswith(SOURCE_EDITION + '/') else rel


def verify_layout(layout, previous):
    require(layout.get('schema_version') == 1
            and layout.get('classification') == 'undated_final_reports_layout'
            and layout.get('base_remote_commit') == LAYOUT_BASE, 'Unexpected current layout identity')
    require(layout.get('source_prefix') == SOURCE_EDITION and layout.get('current_prefix') == EDITION,
            'Unexpected reader-directory mapping')
    require(layout.get('no_strategy_or_result_changes') is True
            and layout.get('no_new_pdf_or_html') is True, 'Changed report/scientific scope')
    require(layout.get('previous_layout', {}).get('path') == PREVIOUS_REL
            and layout['previous_layout'].get('sha256') in PREVIOUS_PINS,
            'Unexpected previous maintenance authority')
    pin(PREVIOUS_REL, layout['previous_layout']['sha256'])
    source = previous['artifact_sha256']
    require(len(source) == 219, 'Unexpected preceding current inventory')
    artifacts = layout['artifact_sha256']
    require(set(artifacts) == {moved(rel) for rel in source} | {PREVIOUS_REL, SELF_REL},
            'Current inventory must preserve all previous owned files plus prior manifest/new checker')
    require(MANIFEST_REL not in artifacts and artifacts[PREVIOUS_REL] == layout['previous_layout']['sha256'],
            'Recursive/missing current manifest authority')
    aliases = layout['reader_path_relocations']
    expected = {rel for rel in source if rel.startswith(SOURCE_EDITION + '/')}
    require(len(expected) == 65 and set(aliases) == expected, 'Exactly 65 explicit reader path mappings required')
    for rel in expected:
        record = aliases[rel]
        require(record == {'current_path': moved(rel), 'sha256': source[rel]},
                'Reader relocation changes identity/bytes: ' + rel)
        require(artifacts.get(moved(rel)) == source[rel], 'Reader hash changed: ' + rel)
    amendments = layout['navigation_and_custody_amendments']
    require(set(amendments) == AMENDED, 'Only three navigation files and custody attributes may change')
    for rel, expected_pin in source.items():
        if rel in amendments:
            record = amendments[rel]
            require(record == {'prior_sha256': expected_pin, 'current_sha256': artifacts[moved(rel)]}
                    and record['current_sha256'] != expected_pin, 'Invalid authorized amendment: ' + rel)
        else:
            require(artifacts.get(moved(rel)) == expected_pin, 'Unapproved changed bytes: ' + rel)
    # Preserve the original byte-custody prefix; only the exact declared
    # language-statistics block may follow it. No source-language relabelling.
    attrs = safe('.gitattributes').read_bytes()
    require(attrs.endswith(LINGUIST_BLOCK), 'Missing/changed report-only Linguist block')
    custody_attrs = attrs[:-len(LINGUIST_BLOCK)]
    require(hashlib.sha256(custody_attrs).hexdigest() == PRE_LANGUAGE_ATTRIBUTES_SHA256,
            'Original byte-custody attribute prefix changed')
    old_attrs = SOURCE_EDITION + '/** -text'
    new_attrs = EDITION + '/** -text'
    require(custody_attrs.count(new_attrs.encode()) == 1 and old_attrs.encode() not in custody_attrs,
            'Missing/ambiguous undated binary-custody rule')
    reconstructed = custody_attrs.replace(new_attrs.encode(), old_attrs.encode())
    require(hashlib.sha256(reconstructed).hexdigest() == source['.gitattributes'],
            'Custody attributes changed beyond the directory pattern')
    verify_language_statistics(layout, attrs)
    previous_reports = previous['reports']
    expected_reports = [{key: moved(value) if isinstance(value, str) else value
                         for key, value in row.items()} for row in previous_reports]
    require(layout['reports'] == expected_reports, 'Report identity changed beyond prefix relocation')
    for rel in AMENDED - {'.gitattributes'}:
        require(SOURCE_EDITION not in safe(rel).read_text(encoding='utf-8'),
                'Dated reader label still in current navigation: ' + rel)
    require(not safe(SOURCE_EDITION).exists(), 'Dated reader directory still exists')
    return artifacts



def verify_language_statistics(layout, attrs):
    """Verify exact metadata-only changes and every excluded asset's old bytes."""
    import copy
    amended = layout.get('language_statistics_amendment')
    require(isinstance(amended, dict), 'Missing language-statistics maintenance authority')
    variant = 'owner' if 'local_working_tree_variant' in layout else 'public'
    prior_manifest = PRE_LANGUAGE_MANIFESTS[variant]
    artifacts = layout['artifact_sha256']
    expected = dict(
        schema_version=1, classification='github_linguist_report_exclusions',
        base_remote_commit=LANGUAGE_BASE, previous_manifest_sha256=prior_manifest,
        previous_attributes_sha256=PRE_LANGUAGE_ATTRIBUTES_SHA256,
        current_attributes_sha256=hashlib.sha256(attrs).hexdigest(),
        previous_verifier_sha256=PRE_LANGUAGE_VERIFIER_SHA256,
        current_verifier_sha256=artifacts[SELF_REL],
        excluded_asset_sha256=EXCLUDED_REPORT_ASSETS,
        generated_html_files=7, executed_report_notebooks=4,
        language_statistics_only=True, excluded_asset_bytes_unchanged=True,
        python_sources_excluded=False, language_relabelling_used=False)
    require(amended == expected, 'Unexpected language-statistics amendment scope')
    require(layout['scope'].get('linguist_language_classification_changed') is True,
            'Current language-statistics scope must disclose the amendment')
    # Reconstruct the exact previous manifest, preserving public/owner README
    # authorities and all 221 owned artifacts except the two declared metadata pins.
    original = copy.deepcopy(layout)
    del original['language_statistics_amendment']
    original['scope']['linguist_language_classification_changed'] = False
    original['artifact_sha256']['.gitattributes'] = PRE_LANGUAGE_ATTRIBUTES_SHA256
    original['artifact_sha256'][SELF_REL] = PRE_LANGUAGE_VERIFIER_SHA256
    original['navigation_and_custody_amendments']['.gitattributes']['current_sha256'] = PRE_LANGUAGE_ATTRIBUTES_SHA256
    original_bytes = (json.dumps(original, indent=2, sort_keys=True) + '\n').encode('utf-8')
    require(hashlib.sha256(original_bytes).hexdigest() == prior_manifest,
            'Changes outside the two approved language-statistics metadata pins')
    for rel, expected_hash in EXCLUDED_REPORT_ASSETS.items():
        pin(rel, expected_hash)


def verify_moved_report_seal(record, artifacts):
    """Validate old sealed paths through the explicit current prefix mapping."""
    require(record['path'] == SOURCE_EDITION + '/final_delivery_manifest.json', 'Unexpected source seal path')
    rel = moved(record['path'])
    require(artifacts.get(rel) == record['sha256'], 'Moved source seal pin conflict')
    pin(rel, record['sha256'])
    seal = load(rel)
    pins = seal['artifact_sha256']
    require(len(pins) == 951, 'Expected complete original 951-entry report seal')
    sealed, overlap = set(), 0
    for child, digest in pins.items():
        original = (PurePosixPath(SOURCE_EDITION) / child).as_posix()
        current = moved(original)
        if current in artifacts:
            require(artifacts[current] == digest, 'Moved source seal conflict: ' + original)
            sealed.add(current)
            overlap += 1
    require(overlap > 0, 'Moved source seal has no verified distributed overlap')
    return seal, sealed, overlap


def main():
    for rel, expected in ANCHORS.items():
        pin(moved(rel), expected)
    # Import only the unchanged, byte-anchored standard-library inspection
    # helpers. Its own historical verify() is deliberately NOT called, changed,
    # monkeypatched, or made to pretend retired working-tree bytes still exist.
    spec = importlib.util.spec_from_file_location('historical_attribution_inspection', safe(HELPER_REL))
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    require(prior.ROOT == ROOT, 'Inspection helpers resolve a different checkout')
    old = load(PRIOR_REL)
    older = load(OLDER_REL)
    current = load(PREVIOUS_REL)
    layout = load(MANIFEST_REL)
    artifacts = prior.sha_map(verify_layout(layout, current), 'current layout artifacts')
    require(current.get('schema_version') == 1
            and current.get('classification') == 'latest_only_final_reports_distribution'
            and current.get('base_remote_commit') == BASE, 'Unexpected maintenance identity')
    require(current.get('removed_report_directory') == OLD_EDITION
            and current.get('evidence_directory') == EVIDENCE, 'Unexpected layout')
    require(current.get('no_strategy_or_result_changes') is True
            and current.get('no_new_pdf_or_html') is True, 'Maintenance scope changed')
    require(not safe(OLD_EDITION).exists(), 'Superseded reader directory still exists')
    previous_artifacts = prior.sha_map(current['artifact_sha256'], 'preceding artifact inventory')
    require(MANIFEST_REL not in artifacts and SELF_REL in artifacts, 'Missing verifier/recursive manifest pin')
    require(not any(p.startswith(OLD_EDITION + '/') for p in artifacts), 'Old reader path in current inventory')
    for rel, expected in artifacts.items():
        pin(rel, expected)
    for rel, expected in ANCHORS.items():
        require(artifacts.get(moved(rel)) == expected, 'Anchor missing from current inventory: ' + rel)
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
        original_destination, digest = record['current_path'], record['current_sha256']
        destination = moved(original_destination)
        require(previous_artifacts.get(original_destination) == digest, 'Invalid previous disposition target: ' + original)
        current_digest = artifacts[destination]
        require(current_digest == (layout['navigation_and_custody_amendments'][original_destination]['current_sha256']
                                   if original_destination in AMENDED else digest), 'Invalid current disposition target: ' + original)
        require(artifacts.get(destination) == current_digest, 'Unpinned disposition target: ' + original)
        pin(destination, current_digest)
        if action == 'unchanged':
            require(original_destination == original and digest == expected, 'Unchanged bytes/path altered: ' + original)
        elif action == 'relocated':
            require(original.startswith(OLD_EDITION + '/') and original.endswith('.json')
                    and original_destination == EVIDENCE + '/' + original[len(OLD_EDITION) + 1:]
                    and digest == expected, 'Incorrect byte-preserving evidence relocation: ' + original)
        elif action == 'alias':
            require(original.startswith(OLD_EDITION + '/') and original.endswith('.csv')
                    and original_destination == SOURCE_EDITION + '/' + original[len(OLD_EDITION) + 1:]
                    and digest == expected, 'Incorrect latest-copy evidence alias: ' + original)
        elif action == 'navigation-amended':
            require(original in {'README.md', 'docs/FINAL_REPORTS_PUBLICATION.md', 'docs/ATTRIBUTION_PUBLICATION.md'}
                    and original_destination == original and digest != expected, 'Unexpected navigation amendment: ' + original)
    require(counts['relocated'] == 19 and counts['alias'] == 26 and counts['reader-retired'] == 7
            and counts['navigation-amended'] == 3 and counts['unchanged'] == 195, 'Disposition totals changed')
    require(set(current['retired_reader_paths']) == retired, 'Retired reader inventory incomplete')
    relocated_actual = {p.relative_to(ROOT).as_posix() for p in safe(EVIDENCE).rglob('*') if p.is_file()}
    relocated_expected = {r['current_path'] for r in dispositions.values() if r['disposition'] == 'relocated'}
    require(relocated_actual == relocated_expected, 'Provenance-only evidence contains unexpected/missing files')
    require(all(p.endswith('.json') for p in relocated_actual), 'Reader copy in provenance-only directory')
    require(current['latest_report_source_seal'] == old['report_source_seal']
            and current['diagnostic_source_seal'] == old['diagnostic_source_seal'], 'Source seals changed')
    seal, sealed, overlap = verify_moved_report_seal(old['report_source_seal'], artifacts)
    for original, record in old['report_source_aliases'].items():
        require(seal['artifact_sha256'].get(original) == record['sha256']
                and artifacts.get(moved(record['distributed_path'])) == record['sha256'], 'Sealed report alias changed')
        sealed.add(moved(record['distributed_path']))
    # This helper explicitly verifies all 38 published owned scientific files,
    # the three declared deterministic index omissions, frozen code, source
    # metadata, calendar/coin/243-coefficient slots and custody relationships.
    diagnostic, scientific_coins, scientific_coefficients = prior.verify_diagnostic(old, artifacts)
    prior.declared_scope(current)
    prior.declared_scope(layout)
    reports = layout['reports']
    require(len(reports) == 3 and {r['period'] for r in reports} == set(prior.PERIODS), 'Three report periods required')
    byperiod = {r['period']: r for r in old['reports']}
    expected_pdfs, expected_htmls = set(), set()
    original_queries_checked = 0
    csvlinks = 0
    for report in reports:
        period = report['period']
        original_report = byperiod[period]
        for field in ('title', 'period', 'pdf', 'html', 'snapshot', 'coin_export', 'coefficient_export'):
            require(report[field] == moved(original_report[field]), 'Current report identity changed: ' + period + '/' + field)
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
                    pin(moved(dispositions[oldtarget]['current_path']), dispositions[oldtarget]['current_sha256'])
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
    for original in old['required_relative_targets']:
        rel = moved(original)
        require(rel in artifacts, 'Required current export omitted')
        safe(rel).is_file() or require(False, 'Missing current export')
    return dict(status='PASS', latest_reader_reports=3, reader_pdf_html_pairs=3,
                undated_directory=EDITION, byte_identical_reader_relocations=65,
                current_navigation_and_custody_amendments=4,
                artifact_sha256_files_verified=len(artifacts),
                historical_inputs_explicitly_accounted=250, dispositions=counts,
                original_query_objects_unchanged=original_queries_checked,
                historical_csv_alias_links_verified=csvlinks, report_seal_overlap=overlap,
                retired_reader_bytes_available_only_in_git_history=True,
                strategy_results_or_scientific_outputs_changed=False,
                language_statistics_only_amendment=True, generated_html_files_excluded=7,
                executed_report_notebooks_excluded=4, excluded_report_asset_bytes_unchanged=True,
                python_sources_excluded=False, new_prices_or_trading_models=False, **diagnostic)


if __name__ == '__main__':
    try:
        print(json.dumps(main(), indent=2, sort_keys=True))
    except Exception as exc:
        print('Undated final report verification FAILED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
