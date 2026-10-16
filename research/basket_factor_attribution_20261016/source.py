"""Owned, read-only access to the 27 saved paths; never generate a strategy.

``export_required_pins`` reads only previously sealed JSON metadata. Actual
market/path hashing and Parquet decoding happen only in ``load_inputs`` after
the new root-owned gate records access. No completed study loader is called.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
PARENT = REPO / "research/post_oos_diagnostics_20261015"
OOS_PARENT = REPO / "research/oos_nine_partial_20261015"
PARENT_MANIFEST_SHA256 = "d81b77da5c3ff1c944d3f154b14fb38f2f7df8411610dc8d234cf581d3008264"
OOS_MANIFEST_SHA256 = "89ff9339ebe3079691e875a7500499478476fe8fe424874eb2d4df6ced230aed"
PANEL_NAMES = ("prices", "quote_volume", "tradable", "observed", "hold_allowed", "mandatory_exit", "decision_allowed")
STRATEGY_ORDER = ("A01", "A02", "A03", "A04", "B01", "B03", "B04", "B05", "B06")
PERIODS = {
    "development": ("2022-01-01", "2024-01-01"),
    "validation": ("2024-01-01", "2026-01-01"),
    "oos_partial_2026_jan_sep": ("2026-01-01", "2026-10-01"),
}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json_pinned(path, expected):
    if sha(path) != expected:
        raise ValueError("Changed sealed metadata: " + str(path))
    return json.loads(Path(path).read_text())


def _path(relative):
    result = (REPO / relative).resolve()
    if not result.is_relative_to(REPO.resolve()):
        raise ValueError("Input path escapes the repository")
    return result


def metadata_catalog():
    """Verify metadata chains, return exact 27 records and expected byte pins.

    Importantly, expected market-file hashes come from the completed manifest;
    this function never hashes or decodes those actual market/path files.
    """
    fm = PARENT / "outputs/final_delivery_manifest.json"
    manifest = _json_pinned(fm, PARENT_MANIFEST_SHA256)
    pins = {str(fm.relative_to(REPO)): PARENT_MANIFEST_SHA256}
    artifact = manifest["artifact_sha256"]

    def adopt(relative):
        expected = artifact[relative]
        full = PARENT / relative
        pins[str(full.relative_to(REPO))] = expected
        return full, expected

    path, digest = adopt("shared/input_manifest.json")
    shared = _json_pinned(path, digest)
    path, digest = adopt("attribution/manifest.json")
    attributed = _json_pinned(path, digest)
    path, digest = adopt("strategy_registry.json")
    registry = _json_pinned(path, digest)
    path, digest = adopt("outputs/diagnostic_freeze.json")
    old_freeze = _json_pinned(path, digest)
    if tuple(registry["order"]) != STRATEGY_ORDER:
        raise ValueError("The original nine strategy identities changed")
    by_key = {(r["comparison_id"], r["period"]): r for r in shared["records"]
              if r["execution_lag_h"] == 1}
    attr_by_key = {(r["comparison_id"], r["period"]): r for r in attributed["records"]}
    expected_keys = {(s, p) for s in STRATEGY_ORDER for p in PERIODS}
    if len(by_key) != 27 or set(by_key) != expected_keys or set(attr_by_key) != expected_keys:
        raise ValueError("Exactly the saved 27 lag1 paths must be retained")
    registry_by_id = {r["comparison_id"]: r for r in registry["strategies"]}
    records = []
    for sid in STRATEGY_ORDER:
        for period in PERIODS:
            rec = by_key[(sid, period)]
            attr = attr_by_key[(sid, period)]
            original = registry_by_id[sid]
            if rec["symbols"] != original["symbols"] or rec["case"] != original["case"]:
                raise ValueError("Saved path identity no longer equals the frozen registry")
            for key in ("primary_path", "base_path", "held_path", "targets_path"):
                relative = rec[key]
                if rec["artifact_sha256"][relative] != artifact[relative]:
                    raise ValueError("Nested path pin differs from the final manifest")
                adopt(relative)
            coin_relative = attr["coin_hourly_path"]
            adopt(coin_relative)
            records.append({**rec, "coin_hourly_path": coin_relative})
    for name in PANEL_NAMES:
        adopt("shared/data/" + name + ".parquet")
    for relative in ("shared/metrics.csv", "attribution/coin_contributions.csv", "attribution/summary.csv",
                     "analysis.py", "audit/attribution_audit.py", "source.py"):
        adopt(relative)
    # Pinned source-quality metadata supplies halt attributes, not a new loader.
    fm = OOS_PARENT / "outputs/final_delivery_manifest.json"
    oos_manifest = _json_pinned(fm, OOS_MANIFEST_SHA256)
    pins[str(fm.relative_to(REPO))] = OOS_MANIFEST_SHA256
    quality_relative = "outputs/source_quality.json"
    quality_path = OOS_PARENT / quality_relative
    quality_sha = oos_manifest["artifact_sha256"][quality_relative]
    pins[str(quality_path.relative_to(REPO))] = quality_sha
    quality = _json_pinned(quality_path, quality_sha)
    # The pure helper and its imports are checked against the old code freeze.
    for relative in ("research/matched_universe_rerun/engine.py", "research/matched_universe_rerun/specs.py",
                     "research/top30_dev_validation/simulator.py", "research/top30_dev_validation/metrics_extra.py",
                     "studies/crypto_stat_arb/src/crypto_stat_arb/backtest.py",
                     "studies/crypto_stat_arb/src/crypto_stat_arb/metrics.py"):
        pins[relative] = old_freeze["governing_sha256"][relative]
    return {"status": "expected_source_hashes_from_sealed_metadata_only_no_market_decode",
            "source_sha256": dict(sorted(pins.items())), "records": records,
            "registry": registry, "source_quality": quality, "periods": PERIODS,
            "strategy_order": list(STRATEGY_ORDER), "expected_paths": 27,
            "expected_coin_rows": 216, "cost_bps": 20, "execution_lag_h": 1}


def export_required_pins():
    """Root freezes this expected-input whitelist before any actual data read."""
    catalog = metadata_catalog()
    destination = ROOT / "required_source_pins.json"
    serialized = json.dumps(catalog, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if destination.exists() and destination.read_text() != serialized:
        raise ValueError("Cannot replace an existing different source whitelist")
    destination.write_text(serialized)
    return destination


def load_inputs():
    """Verify every whitelisted input before decoding any path or source panel."""
    from .gate import assert_frozen, record_access
    assert_frozen("Read saved 27 unchanged primary accounting paths for basket attribution")
    record_access("Before verification/decoding of saved path and market source bytes")
    catalog = json.loads((ROOT / "required_source_pins.json").read_text())
    for relative, expected in catalog["source_sha256"].items():
        if sha(_path(relative)) != expected:
            raise ValueError("Changed whitelisted input: " + relative)
    # Deliberately import the data runtime only after the access gate and hashes.
    import pandas as pd
    panel = {}
    for name in PANEL_NAMES:
        value = pd.read_parquet(PARENT / "shared/data" / (name + ".parquet"))
        if name == "decision_allowed":
            if value.columns.tolist() != ["allowed"]:
                raise ValueError("Unexpected decision permission schema")
            value = value["allowed"]
        value.attrs = {}
        panel[name] = value
    quality = catalog["source_quality"]
    for name in ("prices", "quote_volume"):
        panel[name].attrs = {"halt_bridges": quality["halt_bridges"],
                             "allowed_missing_endpoints": quality["allowed_missing_endpoints"]}
    prices = panel["prices"]
    expected_index = pd.date_range("2021-10-01T01:00:00Z", "2026-10-01T00:00:00Z", freq="h", name="bar_end")
    if not prices.index.equals(expected_index) or prices.columns.tolist() != quality["ordered_union_symbols"]:
        raise ValueError("The original 21-symbol union or exact calendar changed")
    for name, value in panel.items():
        if not value.index.equals(prices.index):
            raise ValueError("Unmatched common source panel calendar")
        if name != "decision_allowed" and not value.columns.equals(prices.columns):
            raise ValueError("Unmatched common source panel columns")
        if name not in ("prices", "quote_volume") and (value.isna().to_numpy().any() or
                not all(pd.api.types.is_bool_dtype(t) for t in (value.dtypes if hasattr(value, "columns") else [value.dtype]))):
            raise ValueError("Lifecycle masks must remain complete known booleans")
    saved = []
    for rec in catalog["records"]:
        frames = {key: pd.read_parquet(PARENT / rec[key]) for key in
                  ("primary_path", "base_path", "held_path", "targets_path", "coin_hourly_path")}
        saved.append({"record": rec, **frames})
    legacy = pd.read_csv(PARENT / "shared/metrics.csv")
    legacy = legacy.loc[legacy.execution_lag_h.eq(1)].copy()
    if len(legacy) != 27:
        raise ValueError("Exactly 27 legacy primary metric rows are required")
    return {"panel": panel, "saved": saved, "catalog": catalog, "legacy_metrics": legacy,
            "legacy_coin_contributions": pd.read_csv(PARENT / "attribution/coin_contributions.csv")}


if __name__ == "__main__":
    print(export_required_pins())
