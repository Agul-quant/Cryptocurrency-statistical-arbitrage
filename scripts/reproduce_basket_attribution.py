#!/usr/bin/env python3
"""Recheck saved post-hoc diagnostics from compact daily inputs only.

Never downloads prices, loads hourly archives, reconstructs trading rules or
changes scientific artifacts. The unchanged independent inference oracle runs
against a temporary copy. Its three deterministic bootstrap matrices are
regenerated and hash-checked there rather than duplicated in the repository.
"""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = "research/basket_factor_attribution_20261016"
PERIOD_DAYS = {"development": 730, "validation": 731, "oos_partial_2026_jan_sep": 273}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def safe_file(root, relative):
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError("Missing or escaping diagnostic file: " + relative)
    return p


def reproduce(study):
    """Return a verified result; write only within an automatically removed tempdir."""
    study = Path(study).resolve()
    final = json.loads(safe_file(study, "outputs/final_delivery_manifest.json").read_text())
    verification = json.loads(safe_file(study, "outputs/final_manifest_verification.json").read_text())
    assert verification["status"] == "passed"
    assert sha(study / "outputs/final_delivery_manifest.json") == verification["manifest_sha256"]
    assert final["paths"] == 27 and final["coin_rows"] == 216 and final["joint_coefficient_slots"] == 243
    assert final["market_downloads"] == final["strategy_reruns"] == final["new_strategy_selections"] == 0
    pins = final["artifact_sha256"]
    omitted = {r: pin for r, pin in pins.items() if r.startswith("outputs/bootstrap_indices_") and r.endswith(".npy")}
    assert len(omitted) == 3
    for rel, pin in pins.items():
        if rel not in omitted:
            assert sha(safe_file(study, rel)) == pin, "Changed supplied diagnostic bytes: " + rel
    amendment = json.loads(safe_file(study, "audit/volatile_log_custody.json").read_text())
    receipt = json.loads(safe_file(study, "outputs/computation_receipt.json").read_text())
    assert sha(study / "outputs/computation_receipt.json") == amendment["computation_receipt_sha256"]
    assert set(amendment["stable_scientific_artifact_sha256"]) == set(receipt["artifact_sha256"]) - {"outputs/computation.log"}
    for rel, pin in amendment["stable_scientific_artifact_sha256"].items():
        assert pin == receipt["artifact_sha256"][rel] == pins[rel]
    assert len(amendment["volatile_log_repair"]) == 1
    log = amendment["volatile_log_repair"][0]
    assert log["path"] == "outputs/computation.log"
    assert log["intermediate_sha256"] == receipt["artifact_sha256"][log["path"]]
    assert sha(safe_file(study, log["path"])) == log["final_sha256"]
    oracle_path = safe_file(study, "audit/independent_inference_audit.py")
    audit = json.loads(safe_file(study, "audit/independent_inference_audit.json").read_text())
    assert audit["status"] == "PASS" and sha(oracle_path) == audit["audit_code_sha256"]
    # Import only the audited independent numerical oracle, never source.py,
    # gate.py, run.py, the production inference implementation or trading code.
    spec = importlib.util.spec_from_file_location("published_independent_basket_oracle", oracle_path)
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    import numpy as np
    with tempfile.TemporaryDirectory(prefix="basket-diagnostic-check-") as temp:
        temporary = Path(temp) / "diagnostic"
        for rel in pins:
            if rel in omitted:
                continue
            destination = temporary / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(study / rel, destination)
        destination = temporary / log["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(study / log["path"], destination)
        generated = 0
        for period, days in PERIOD_DAYS.items():
            rel = "outputs/bootstrap_indices_" + period + ".npy"
            indices = oracle.independent_indices(days)
            assert indices.shape == (4000, days)
            buffer = io.BytesIO()
            np.save(buffer, indices, allow_pickle=False)
            data = buffer.getvalue()
            assert hashlib.sha256(data).hexdigest() == omitted[rel], "Regenerated bootstrap matrix differs: " + period
            (temporary / rel).write_bytes(data)
            generated += 1
        oracle.ROOT = temporary
        oracle.AUDIT = temporary / "audit"
        # The original audit writes only its own receipt. Redirect that receipt
        # to temporary custody and retain no modified historical output.
        with contextlib.redirect_stdout(io.StringIO()):
            oracle.main()
        result = json.loads((temporary / "audit/independent_inference_audit.json").read_text())
        assert result["status"] == "PASS"
        assert result["joint_models_independently_reproduced"] == 27
        assert result["matched_BTC_models_independently_reproduced"] == 27
        assert result["legacy_BTC_models_independently_reproduced"] == 27
        assert result["joint_coefficients_and_CIs"] == 243 and result["coin_rows_and_CIs"] == 216
        assert result["all_invalid_bootstrap_counts_zero"]
    # Rehash supplied owned files after independent numerical verification.
    for rel, pin in pins.items():
        if rel not in omitted:
            assert sha(study / rel) == pin, "Supplied input changed during verification"
    return {"status": "PASS", "joint_models": 27, "matched_BTC_models": 27,
            "legacy_BTC_models": 27, "joint_coefficients_and_CIs": 243,
            "coin_attributions_and_CIs": 216, "bootstrap_draws_per_period": 4000,
            "deterministic_index_arrays_regenerated_and_hash_checked": generated,
            "source_artifacts_modified": False, "raw_hourly_data_or_strategy_reconstruction": False,
            "interpretation": "Conditional post-hoc diagnostic reproduction; not a fresh OOS or search-adjusted discovery"}


def main():
    try:
        print(json.dumps(reproduce(ROOT / DIAGNOSTIC), indent=2, sort_keys=True))
    except ImportError as exc:
        print("Optional numerical verification requires the pinned packages in requirements.lock.txt: " + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print("Diagnostic reproduction FAILED: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
