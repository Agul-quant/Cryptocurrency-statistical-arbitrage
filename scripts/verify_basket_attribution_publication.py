#!/usr/bin/env python3
"""Read-only, standard-library inspection of the bounded attribution publication.

Run from any directory after installation in the checkout's scripts directory.
This verifies saved bytes and metadata, not statistical results, historical market
inputs, omitted bootstrap-index bytes, prices, or a strategy/backtest reproduction.
No files are written and no scientific modules, subprocesses or network are used.
"""

import base64
import csv
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import unquote, unquote_to_bytes, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_REL = "provenance/basket_attribution_publication_20261016.json"
SELF_REL = "scripts/verify_basket_attribution_publication.py"
DIAGNOSTIC_REL = "research/basket_factor_attribution_20261016"
EDITION = "final_reports_20261016"
OLD_EDITION = "final_reports_20261015"
LIMIT = 100 * 1024 * 1024
PERIODS = ("development", "validation", "oos_partial_2026_jan_sep")
IDS = ("A01", "A02", "A03", "A04", "B01", "B03", "B04", "B05", "B06")
CODE_FILES = {"accounting.py", "gate.py", "inference.py", "run.py", "source.py",
              "tests/test_accounting.py", "tests/test_inference.py"}
NEW_QUERIES = {"basket_attribution_summary", "basket_attribution_coins",
               "basket_attribution_diagnostics", "basket_attribution_coefficients",
               "basket_attribution_methods"}
HEX = re.compile(r"[0-9a-f]{64}\Z")
MD_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|(?:\\.|[^\s)])+)(?:\s+[\"'][^\n]*?[\"'])?\s*\)")
MD_REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)", re.M)
NETWORK_IMPORT = re.compile(r"(?:\bimport\s*\(|\bimportScripts\s*\(|\bfrom\s*)\s*[\"'](?:https?:)?//", re.I)
CSS_IMPORT = re.compile(r"@import\s+(?:url\s*\()?\s*[\"']?(?:https?:)?//", re.I)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative(value):
    """Reject noncanonical manifest paths before touching the filesystem."""
    require(isinstance(value, str) and value and "\\" not in value
            and not any(ord(c) < 32 for c in value), "Invalid relative path: %r" % value)
    p = PurePosixPath(value)
    require(not p.is_absolute() and not urlsplit(value).scheme
            and all(part not in ("", ".", "..") for part in value.split("/"))
            and p.as_posix() == value, "Unsafe/noncanonical path: %r" % value)
    return value


def inside(path):
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        raise ValueError("Path escapes checkout: %s" % path)
    return path


def resolve(rel, exists=True):
    rel = relative(rel)
    path = inside((ROOT / rel).resolve())
    # Symlinks cannot silently stand in for manifest-owned bytes.
    cursor = ROOT
    for part in PurePosixPath(rel).parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), "Symlink in declared path: %s" % rel)
    if exists:
        require(path.is_file(), "Missing regular file: %s" % rel)
    return path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha_map(value, label):
    require(isinstance(value, dict) and bool(value), "Empty/non-object hash map: " + label)
    for rel, pin in value.items():
        relative(rel)
        require(isinstance(pin, str) and HEX.fullmatch(pin), "Invalid SHA256: " + label + "/" + rel)
    return value


def checked(rel, pin):
    require(isinstance(pin, str) and HEX.fullmatch(pin), "Invalid SHA256 for " + str(rel))
    path = resolve(rel)
    require(path.stat().st_size < LIMIT, "Artifact is not below 100 MiB: " + rel)
    require(digest(path) == pin, "Changed bytes: " + rel)
    return path


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(rel):
    return json.loads(resolve(rel).read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys)


def csv_rows(rel):
    with resolve(rel).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)),
                "Missing/duplicate CSV columns: " + rel)
        result = list(reader)
    require(all(None not in row and None not in row.values() for row in result),
            "Malformed CSV row: " + rel)
    return result


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def markdown_targets(text):
    for match in MD_LINK.finditer(text):
        yield match.group(1).strip("<>").replace(r"\(", "(").replace(r"\)", ")")
    for match in MD_REFERENCE.finditer(text):
        yield match.group(1).strip("<>")


def link_target(base, target, label, csv_only=False):
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        require(parts.scheme.lower() != "file", "file URI in " + label)
        return
    path_text = unquote(parts.path)
    if not path_text or (csv_only and not path_text.lower().endswith(".csv")):
        return
    require(not path_text.startswith(("/", "\\")) and "\\" not in path_text,
            "Absolute/unsafe relative link in " + label + ": " + target)
    path = inside((base / path_text).resolve())
    require(path.exists(), "Broken relative link in " + label + ": " + target)


class InlineHTML(HTMLParser):
    def __init__(self, base, label):
        super().__init__(convert_charrefs=True)
        self.base, self.label = base, label

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script":
            src = values.get("src", "")
            require(not src or src.lower().startswith("data:"), "Non-inline script in " + self.label)
            if src:
                self.inspect_data_resource(src)
        if tag == "link" and "stylesheet" in values.get("rel", "").lower().split():
            href = values.get("href", "")
            require(not href or href.lower().startswith("data:"), "Non-inline stylesheet in " + self.label)
            if href:
                self.inspect_data_resource(href)
        if tag == "link" and (values.get("as") in ("script", "style")
                              or "modulepreload" in values.get("rel", "").lower().split()):
            href = values.get("href", "")
            require(not href or href.lower().startswith("data:"), "External JS/CSS preload in " + self.label)
        if tag == "a" and values.get("href"):
            link_target(self.base, values["href"], self.label, csv_only=True)

    handle_startendtag = handle_starttag

    def inspect_data_resource(self, url):
        header, content = url.split(",", 1)
        raw = base64.b64decode(content, validate=True) if ";base64" in header.lower() else unquote_to_bytes(content)
        text = raw.decode("utf-8")
        require("file://" not in text.lower() and not NETWORK_IMPORT.search(text)
                and not CSS_IMPORT.search(text), "External/local import in embedded JS/CSS: " + self.label)


def verify_html(rel):
    path = resolve(rel)
    text = path.read_text(encoding="utf-8")
    require("file://" not in text.lower(), "Local file URI in " + rel)
    # Importing CSS from an inline style block is still an external dependency.
    require(not CSS_IMPORT.search(text) and not NETWORK_IMPORT.search(text), "Network JS/CSS import in " + rel)
    parser = InlineHTML(path.parent, rel)
    parser.feed(text)
    parser.close()


def verify_seal(record, artifacts, label, require_all=False, omitted=None, scope=None):
    require(isinstance(record, dict), "Missing " + label)
    rel = relative(record["path"])
    require(rel in artifacts and artifacts[rel] == record["sha256"],
            label + " must itself be pinned in artifact_sha256")
    checked(rel, record["sha256"])
    data = read_json(rel)
    pins = sha_map(data["artifact_sha256"], label)
    parent = PurePosixPath(scope) if scope else PurePosixPath(rel).parent
    count = 0
    for child, pin in pins.items():
        full = (parent / child).as_posix()
        if omitted and child in omitted:
            require(omitted[child] == pin and full not in artifacts, "Incorrect omission: " + full)
        elif full in artifacts:
            require(artifacts[full] == pin, label + " pin conflict: " + full)
            count += 1
        elif require_all:
            raise ValueError(label + " is missing distributed owned file: " + full)
    require(count > 0, label + " has no verified distributed artifact overlap")
    return data, count


def slots(rows, period, coefficients=False):
    require(len(rows) == (81 if coefficients else 72), "Incorrect row count for " + period)
    field = "term" if coefficients else "symbol"
    grouped = {identity: set() for identity in IDS}
    for row in rows:
        identity = row.get("strategy_id")
        require(row.get("period") == period and identity in grouped,
                "Unexpected period/strategy row: " + period)
        term = row.get(field)
        require(isinstance(term, str) and term and term not in grouped[identity],
                "Duplicate/invalid slot for " + identity + "/" + period)
        grouped[identity].add(term)
        if coefficients:
            require(str(row.get("multiplicity_family_size")) == "243",
                    "Coefficient correction must retain global 243-slot family")
            require("not_search_adjusted" in row.get("ci_scope", "")
                    and "not_search_adjusted" in row.get("simultaneous_ci_scope", ""),
                    "Conditional inference limitation lost")
    for identity, terms in grouped.items():
        require(len(terms) == (9 if coefficients else 8), "Missing slots: " + identity + "/" + period)
        if coefficients:
            require("alpha_annual" in terms, "Missing intercept: " + identity + "/" + period)
    return grouped


def snapshot_matches_csv(snapshot_rows, export_rows, key_fields, label):
    """Compare saved values only, allowing JSON's numeric representation of CSV."""
    def key(row):
        return tuple(row[field] for field in key_fields)
    expected = {key(row): row for row in export_rows}
    require(len(expected) == len(export_rows), "Duplicate CSV keys: " + label)
    require({key(row) for row in snapshot_rows} == set(expected), "Snapshot/CSV key mismatch: " + label)
    for row in snapshot_rows:
        for field, value in expected[key(row)].items():
            require(field in row, "Snapshot lost CSV field: " + label + "/" + field)
            actual = row[field]
            if isinstance(actual, (int, float)) and not isinstance(actual, bool):
                require(math.isfinite(actual) and float(value) == actual,
                        "Snapshot/CSV numeric mismatch: " + label + "/" + field)
            elif actual is None:
                require(value in ("", "NaN", "nan"), "Snapshot/CSV null mismatch: " + label)
            else:
                require(actual == value, "Snapshot/CSV value mismatch: " + label + "/" + field)


def verify_diagnostic(data, artifacts):
    prefix = data["diagnostic_dir"]
    require(prefix == DIAGNOSTIC_REL, "Unexpected diagnostic directory")
    local = lambda rel: prefix + "/" + relative(rel)
    omitted = sha_map(data["omitted_bootstrap_indices"], "omitted bootstrap indices")
    expected_omissions = {"outputs/bootstrap_indices_" + period + ".npy" for period in PERIODS}
    require(set(omitted) == expected_omissions, "Exactly three diagnostic-relative index omissions required")
    require(all(local(rel) not in artifacts for rel in omitted), "Omitted arrays cannot be distributed artifacts")

    seal, included_count = verify_seal(data["diagnostic_source_seal"], artifacts,
                                      "diagnostic_source_seal", require_all=True,
                                      omitted=omitted, scope=prefix)
    require(data["diagnostic_source_seal"]["path"] == local("outputs/final_delivery_manifest.json"),
            "Unexpected diagnostic seal location")
    require(included_count == 38, "Expected 38 distributed non-index diagnostic seal entries")
    return verify_diagnostic_contents(data, artifacts, omitted, seal)


def verify_diagnostic_contents(data, artifacts, omitted, seal):
    prefix = data["diagnostic_dir"]
    local = lambda rel: prefix + "/" + relative(rel)
    frozen = sha_map(seal["artifact_sha256"], "diagnostic frozen source")
    require(len(frozen) == 41, "Expected complete 41-entry diagnostic source seal")
    for rel, pin in frozen.items():
        if rel in omitted:
            require(omitted[rel] == pin, "Omitted index seal conflict: " + rel)
        else:
            require(artifacts.get(local(rel)) == pin, "Unpinned sealed diagnostic source: " + rel)
    for field, count in (("paths", 27), ("coin_rows", 216), ("joint_coefficient_slots", 243)):
        require(seal.get(field) == count, "Diagnostic seal count mismatch: " + field)

    load = lambda rel: read_json(local(rel))
    receipt = load("outputs/computation_receipt.json")
    custody = load("audit/volatile_log_custody.json")
    freeze = load("outputs/access_freeze.json")
    access = load("outputs/source_access_receipt.json")
    protocol = load("protocol.json")
    source = load("required_source_pins.json")
    account = load("audit/independent_accounting.json")
    inference = load("audit/independent_inference_audit.json")

    require(custody["computation_receipt_sha256"] == artifacts[local("outputs/computation_receipt.json")],
            "Custody receipt hash mismatch")
    receipt_pins = sha_map(receipt["artifact_sha256"], "computation receipt")
    stable = sha_map(custody["stable_scientific_artifact_sha256"], "stable scientific custody")
    require(len(receipt_pins) == 20 and len(stable) == 19
            and stable == {k: v for k, v in receipt_pins.items() if k != "outputs/computation.log"},
            "Stable custody must be exactly receipt's 20 entries minus volatile stdout")
    included_stable = 0
    for rel, pin in stable.items():
        if rel in omitted:
            require(omitted[rel] == pin, "Omitted index receipt/custody mismatch: " + rel)
        else:
            require(artifacts.get(local(rel)) == pin, "Stable scientific pin conflict: " + rel)
            included_stable += 1
    require(included_stable == 16, "Expected 16 byte-verified included stable scientific files")
    repairs = custody["volatile_log_repair"]
    require(isinstance(repairs, list) and len(repairs) == 1, "Exactly one stdout custody amendment required")
    repair = repairs[0]
    require(repair["path"] == "outputs/computation.log"
            and repair["intermediate_sha256"] == receipt_pins[repair["path"]]
            and repair["final_sha256"] != repair["intermediate_sha256"]
            and artifacts.get(local(repair["path"])) == repair["final_sha256"],
            "Only exact computation.log intermediate-to-final pin amendment is permitted")

    protocol_pin = artifacts[local("protocol.json")]
    freeze_pin = artifacts[local("outputs/access_freeze.json")]
    for label, record in (("receipt", receipt), ("freeze", freeze), ("first access", access)):
        require(record.get("protocol_sha256") == protocol_pin, label + " protocol pin mismatch")
    for record in (receipt, access):
        require(record.get("access_freeze_sha256") == freeze_pin, "Owned access-freeze pin mismatch")
    require(freeze["source_pins_sha256"] == artifacts[local("required_source_pins.json")],
            "Owned source metadata pin mismatch")
    code = sha_map(freeze["code_sha256"], "owned code freeze")
    require(set(code) == CODE_FILES, "Exactly seven pre-access frozen code/test files required")
    for rel, pin in code.items():
        require(artifacts.get(local(rel)) == pin == frozen[rel], "Owned frozen code/test mismatch: " + rel)
    require(freeze.get("authorized") is True and freeze.get("no_new_strategy_selection") is True
            and access.get("no_new_prices_no_strategy_rerun_no_reselection") is True
            and receipt.get("no_new_prices_or_strategy_execution_or_reselection") is True,
            "Frozen diagnostic scope declarations changed")
    require(freeze["created_at_utc"] < access["created_at_utc"] < receipt["created_at_utc"],
            "Additional access chronology does not follow owned freeze")
    for record in (freeze, protocol):
        require(record.get("expected_paths") == 27 and record.get("expected_coin_rows") == 216
                and record.get("expected_joint_coefficients") == 243, "Frozen design counts changed")
    require(protocol["comparison_ids"] == list(IDS) and source["strategy_order"] == list(IDS),
            "Frozen nine identities changed")
    require(protocol["joint_multiplicity"]["family_size"] == 243
            and "not correction for original" in protocol["joint_multiplicity"]["limitations"],
            "243-slot correction must not claim adjustment for original strategy search")
    source_pins = sha_map(source["source_sha256"], "historical source metadata")
    require(len(source_pins) == 143, "Expected 143 historical source metadata pins (not byte-verified here)")
    require(protocol["source_policy"]["parent_final_manifest_sha256"] == source_pins[
        protocol["source_policy"]["parent"] + "/outputs/final_delivery_manifest.json"],
        "Parent diagnostic lineage metadata conflict")
    require(len(source["records"]) == 27, "Expected 27 frozen source path records")
    for record in source["records"]:
        for rel, pin in sha_map(record["artifact_sha256"], "path source metadata").items():
            require(source_pins.get(protocol["source_policy"]["parent"] + "/" + rel) == pin,
                    "Per-path and global source metadata mismatch: " + rel)

    require(account.get("status", "").startswith("PASS_")
            and account.get("all_27_frozen_paths_unchanged") is True
            and account.get("all_216_coin_point_rows_reconciled") is True
            and account.get("technical_stdout_intermediate_pin_amendment_verified") is True,
            "Independent accounting audit is not PASS")
    require(inference.get("status") == "PASS" and inference.get("joint_models_independently_reproduced") == 27
            and inference.get("coin_rows_and_CIs") == 216 and inference.get("joint_coefficients_and_CIs") == 243
            and inference.get("multiple_testing_family") == 243
            and inference.get("verified_stable_scientific_files") == 19,
            "Independent inference audit PASS/count declarations changed")
    require(account["auditor_code_sha256"] == artifacts[local("audit/independent_accounting.py")]
            and inference["audit_code_sha256"] == artifacts[local("audit/independent_inference_audit.py")]
            and inference["computation_receipt_sha256"] == artifacts[local("outputs/computation_receipt.json")]
            and inference["technical_log_custody_amendment_sha256"] == artifacts[local("audit/volatile_log_custody.json")],
            "Independent audit code/custody linkage mismatch")

    coins = csv_rows(local("outputs/coin_attribution.csv"))
    coefficients = csv_rows(local("outputs/joint_coefficients.csv"))
    require(len(coins) == 216 and len(coefficients) == 243, "Scientific CSV row counts changed")
    baskets = {row["comparison_id"]: set(row["symbols"]) for row in source["registry"]["strategies"]}
    for period in PERIODS:
        coin_slots = slots([r for r in coins if r["period"] == period], period)
        coefficient_slots = slots([r for r in coefficients if r["period"] == period], period, True)
        require(coin_slots == baskets, "Coin slots differ from frozen baskets")
        require(coefficient_slots == {k: v | {"alpha_annual"} for k, v in baskets.items()},
                "Coefficient slots differ from frozen baskets plus intercept")
    return {"stable_scientific_files_byte_verified": included_stable,
            "sealed_diagnostic_files_byte_verified": len(frozen) - len(omitted),
            "frozen_code_and_test_files": len(code), "historical_source_metadata_pins": len(source_pins),
            "omitted_bootstrap_index_pins_cross_checked": len(omitted)}, coins, coefficients


def declared_scope(value):
    forbidden_true = {"full_backtest_reproduction_claimed", "historical_raw_inputs_byte_verified",
                      "omitted_bootstrap_indices_byte_verified", "original_strategy_search_adjusted",
                      "original_search_adjusted", "new_prices_or_trading_models", "prior_research_search_adjusted",
                      "raw_hourly_source_reconstruction_included", "strategy_rules_rerun",
                      "all143_original_source_bytes_reverified_by_published_checker",
                      "full_trading_engine_reproduction_claimed"}
    if isinstance(value, dict):
        for key, item in value.items():
            if key in forbidden_true:
                require(item is False, "Unsupported verification/research claim: " + key)
            declared_scope(item)
    elif isinstance(value, list):
        for item in value:
            declared_scope(item)


def verify():
    data = read_json(MANIFEST_REL)
    require(data.get("classification") == "bounded_posthoc_attribution_report_distribution",
            "Incorrect publication classification")
    declared_scope(data)
    if "lineage" in data:
        for field, expected in (("fixed_strategy_period_paths", 27), ("coin_rows", 216),
                                ("joint_coefficient_slots", 243), ("joint_multiplicity_family", 243)):
            require(data["lineage"].get(field) == expected, "Incorrect declared lineage: " + field)
        require(data["lineage"].get("conditional_posthoc_not_fresh_OOS") is True,
                "Lineage must preserve conditional post-hoc interpretation")
    artifacts = sha_map(data["artifact_sha256"], "publication artifacts")
    require(MANIFEST_REL not in artifacts and SELF_REL in artifacts,
            "Manifest excludes only its own recursive pin, not the verifier")
    for rel, pin in artifacts.items():
        checked(rel, pin)
    baseline = sha_map(data["baseline_preserved_sha256"], "preserved baseline")
    for rel, pin in baseline.items():
        checked(rel, pin)
        if rel in artifacts:
            require(artifacts[rel] == pin, "Baseline/artifact pin conflict: " + rel)
    require(any(rel.startswith(OLD_EDITION + "/") for rel in baseline), "Old report edition is not preserved")
    report_seal, report_overlap = verify_seal(data["report_source_seal"], artifacts, "report_source_seal")
    sealed_report_targets = set()
    report_root = PurePosixPath(data["report_source_seal"]["path"]).parent
    for child, pin in report_seal["artifact_sha256"].items():
        full = (report_root / child).as_posix()
        if artifacts.get(full) == pin:
            sealed_report_targets.add(full)
    aliases = data.get("report_source_aliases", {})
    require(isinstance(aliases, dict), "report_source_aliases must be an object")
    for original, record in aliases.items():
        relative(original)
        destination = relative(record["distributed_path"])
        require(report_seal["artifact_sha256"].get(original) == record["sha256"]
                and artifacts.get(destination) == record["sha256"],
                "Report source alias does not preserve exact sealed bytes: " + original)
        sealed_report_targets.add(destination)
    diagnostic, scientific_coins, scientific_coefficients = verify_diagnostic(data, artifacts)

    reports = data["reports"]
    require(isinstance(reports, list) and len(reports) == 3
            and {r["period"] for r in reports} == set(PERIODS), "Exactly three distinct report periods required")
    expected_pdfs = {r["pdf"] for r in reports}
    require(len(expected_pdfs) == 3 and all(p.startswith(EDITION + "/") for p in expected_pdfs),
            "Exactly three new-edition reader PDFs required")
    require({p for p in artifacts if p.lower().endswith(".pdf")} == expected_pdfs,
            "New distribution includes an extra PDF outside the three reader reports")
    actual_pdfs = {p.relative_to(ROOT).as_posix() for p in inside((ROOT / EDITION).resolve()).rglob("*")
                   if p.is_file() and p.suffix.lower() == ".pdf"}
    require(actual_pdfs == expected_pdfs, "New report edition contains missing/extra PDFs")
    original_queries_checked = 0
    csv_link_checks = 0
    for report in reports:
        period = report["period"]
        require(isinstance(report["title"], str) and report["title"], "Missing report title")
        for field in ("pdf", "html", "snapshot", "coin_export", "coefficient_export"):
            require(report[field] in artifacts, "Unpinned report " + field)
            require(report[field] in sealed_report_targets, "Report artifact not backed by source seal: " + report[field])
            suffix = {"pdf": ".pdf", "html": ".html", "snapshot": ".json",
                      "coin_export": ".csv", "coefficient_export": ".csv"}[field]
            require(report[field].startswith(EDITION + "/") and report[field].endswith(suffix),
                    "Incorrect report artifact edition/extension: " + field)
        pdf = resolve(report["pdf"])
        with pdf.open("rb") as handle:
            require(handle.read(5) == b"%PDF-", "Invalid PDF header: " + report["pdf"])
        snapshot = read_json(report["snapshot"])
        require(snapshot.get("buildStatus") == "complete", "Incomplete reviewed snapshot: " + period)
        queries = snapshot["queries"]
        require(NEW_QUERIES <= set(queries), "Missing attribution snapshot queries: " + period)
        for query, count in (("basket_attribution_summary", 9), ("basket_attribution_diagnostics", 9),
                             ("basket_attribution_methods", 1)):
            rows = queries[query]["rows"]
            require(len(rows) == count and all(row.get("period") == period for row in rows),
                    "Incorrect saved query period/count: " + query)
        methods = queries["basket_attribution_methods"]["rows"][0]
        require(methods.get("protocol_sha256") == artifacts[DIAGNOSTIC_REL + "/protocol.json"]
                and methods.get("payload_sha256") == artifacts[DIAGNOSTIC_REL + "/outputs/report_payload.json"],
                "Snapshot method source-pin mismatch")
        coins = csv_rows(report["coin_export"])
        coefficients = csv_rows(report["coefficient_export"])
        require(coins == [r for r in scientific_coins if r["period"] == period], "Coin CSV is not exact saved period projection")
        require(coefficients == [r for r in scientific_coefficients if r["period"] == period],
                "Coefficient CSV is not exact saved period projection")
        slots(coins, period)
        slots(coefficients, period, True)
        coin_rows = queries["basket_attribution_coins"]["rows"]
        coefficient_rows = queries["basket_attribution_coefficients"]["rows"]
        slots(coin_rows, period)
        slots(coefficient_rows, period, True)
        snapshot_matches_csv(coin_rows, coins, ("strategy_id", "period", "symbol"), period + "/coins")
        snapshot_matches_csv(coefficient_rows, coefficients, ("strategy_id", "period", "term"), period + "/coefficients")
        folder = resolve(report["html"]).parent
        pins_rel = (PurePosixPath(report["html"]).parent / "attribution_source_pins.json").as_posix()
        require(pins_rel in artifacts, "Missing report attribution source pins: " + period)
        pins = read_json(pins_rel)
        require(pins["period"] == period and pins["frozen_identities"] == list(IDS)
                and pins["snapshot_sha256"] == artifacts[report["snapshot"]], "Report period/snapshot source pin mismatch")
        for rel, pin in sha_map(pins["input_sha256"], "report scientific source pins").items():
            require(artifacts.get(DIAGNOSTIC_REL + "/" + rel) == pin, "Report scientific input hash conflict: " + rel)
        if "prior_snapshot" in report:
            prior_rel = relative(report["prior_snapshot"])
            require(prior_rel.startswith(OLD_EDITION + "/") and prior_rel in baseline,
                    "Prior reviewed snapshot must be baseline-preserved")
            prior = read_json(prior_rel)
            require({k: v for k, v in queries.items() if k not in NEW_QUERIES} == prior["queries"],
                    "Original reviewed query objects changed: " + period)
            original_queries_checked += len(prior["queries"])
            prior_folder = ROOT.joinpath(*PurePosixPath(prior_rel).parts[:2])
            for text in strings(prior):
                for target in markdown_targets(text):
                    link_target(prior_folder, target, prior_rel, csv_only=True)
                    csv_link_checks += int(urlsplit(target).path.lower().endswith(".csv"))
        for text in strings(snapshot):
            for target in markdown_targets(text):
                link_target(folder, target, report["snapshot"], csv_only=True)
                csv_link_checks += int(urlsplit(target).path.lower().endswith(".csv"))
    for rel in artifacts:
        if rel.lower().endswith((".html", ".htm")):
            verify_html(rel)
    for rel in data["required_relative_targets"]:
        resolve(rel)
    for rel in ("README.md", "docs/ATTRIBUTION_PUBLICATION.md"):
        require(rel in artifacts, "Missing pinned publication documentation: " + rel)
        path = resolve(rel)
        for target in markdown_targets(path.read_text(encoding="utf-8")):
            link_target(path.parent, target, rel)

    # High-confidence credentials only; exclude this literal-bearing scanner itself.
    secret = re.compile(rb"(?:\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
    for rel in artifacts:
        if rel != SELF_REL:
            require(not secret.search(resolve(rel).read_bytes()), "High-confidence credential pattern: " + rel)
    return dict(status="PASS", distributed_artifacts=len(artifacts), reader_reports=3,
                baseline_files_preserved=len(baseline), included_report_seal_pins=report_overlap,
                original_query_objects_unchanged=original_queries_checked,
                report_csv_link_targets_inspected=csv_link_checks,
                omitted_bootstrap_index_bytes_verified=False,
                historical_raw_input_bytes_verified=False, full_backtest_reproduction_claimed=False,
                original_strategy_search_adjusted=False, new_prices_or_trading_models=False, diagnostics_fitted=True, **diagnostic)


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        print("Publication verification FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
