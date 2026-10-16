#!/usr/bin/env python3
"""Read-only checksum/inspection verification; no prices or strategy execution."""
from pathlib import Path
from urllib.parse import unquote, urlparse
import hashlib, json, re, sys
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "provenance/final_reports_20261016_distribution.json"
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()
def resolve(rel):
    p = (ROOT / rel).resolve()
    if not p.is_relative_to(ROOT.resolve()): raise ValueError("Path escapes checkout")
    if not p.is_file(): raise FileNotFoundError(rel)
    return p
def verify():
    d = json.loads(MANIFEST.read_text())
    assert d["classification"] == "bounded_presentation_only_distribution"
    for rel, pin in d["artifact_sha256"].items():
        p = resolve(rel)
        assert p.stat().st_size < 100 * 1024 * 1024, ("GitHub size limit", rel)
        assert sha(p) == pin, ("Changed publication bytes", rel)
    seal = resolve(d["original_final_seal"]["path"])
    assert sha(seal) == d["original_final_seal"]["sha256"]
    historical = json.loads(seal.read_text())
    for rel, pin in d["sealed_subset_sha256"].items():
        assert historical["artifact_sha256"][rel] == pin
        assert sha(resolve("final_reports_20261015/" + rel)) == pin
    for original, record in d["source_aliases"].items():
        assert original.startswith("research/")
        assert sha(resolve(record["distributed_path"])) == record["sha256"]
    pdfs = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "final_reports_20261015").rglob("*.pdf"))
    assert pdfs == sorted(x["pdf"] for x in d["reports"]), "Exactly three reader PDFs required"
    for r in d["reports"]:
        assert resolve(r["pdf"]).read_bytes().startswith(b"%PDF-")
        html = resolve(r["html"]).read_text()
        assert "file://" not in html
        # Source code and inline data are self-contained; relative export downloads are delivered beside the HTML.
        assert not re.search(r"<(?:script|link)\b[^>]*(?:src|href)=[\"']https?://", html, re.I)
    for rel in d["required_relative_targets"]: resolve(rel)
    for rel in ["README.md", "docs/FINAL_REPORTS_PUBLICATION.md"]:
        p = resolve(rel)
        for target in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", p.read_text()):
            target = unquote(target.split("#")[0])
            if not target or urlparse(target).scheme or target.startswith("//"): continue
            q = (p.parent / target).resolve()
            assert q.is_relative_to(ROOT.resolve()) and q.exists(), ("Broken relative link", rel, target)
    # High-confidence credential formats only; historical local paths are documented, not credentials.
    secret = re.compile(rb"(?:\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
    for rel in d["artifact_sha256"]:
        if rel == "scripts/verify_final_reports_publication.py": continue
        assert not secret.search(resolve(rel).read_bytes()), ("Credential pattern", rel)
    return {"status": "PASS", "distributed_artifacts": len(d["artifact_sha256"]), "reader_reports": len(pdfs), "saved_source_identities": len(d["source_aliases"]), "full_backtest_reproduction_claimed": False, "new_prices_or_models": False}
if __name__ == "__main__":
    try: print(json.dumps(verify(), indent=2, sort_keys=True))
    except Exception as exc:
        print("Publication verification FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
