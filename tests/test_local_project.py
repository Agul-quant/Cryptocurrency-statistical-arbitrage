"""Portable wrapper regressions; all fixtures are small isolated snapshots."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/local_project.py"
SPEC = importlib.util.spec_from_file_location("portable_local_project", SCRIPT)
project = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(project)


def put(root: Path, name: str, content: bytes) -> dict:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return project.fingerprint(target)


def save(root: Path, name: str, value: dict) -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value))


@pytest.fixture
def snapshot(tmp_path):
    inventory = {}
    for study in project.STUDIES:
        inventory[study] = {"README.md": put(tmp_path, f"studies/{study}/README.md", study.encode())}
    content = b"\x00preserved parquet bytes\xff\x01\x02" * 9
    name = "studies/crypto_intraday_5m/data/processed/bars.parquet"
    record = {"path": name, "sha256": project.hashlib.sha256(content).hexdigest(), "bytes": len(content), "parts": []}
    inventory["crypto_intraday_5m"]["data/processed/bars.parquet"] = {k: record[k] for k in ("sha256", "bytes")}
    for number, block in enumerate((content[:17], content[17:99], content[99:])):
        part_path = f"data_parts/bars.part-{number:03}"
        record["parts"].append({"path": part_path, **put(tmp_path, part_path, block)})
    save(tmp_path, "provenance/study_snapshot.json", {"schema_version": 1, "study_files": inventory})
    save(tmp_path, "provenance/large_file_parts.json", {"schema_version": 1, "files": [record]})
    return tmp_path, content


def add_file(root: Path, study: str, relative: str, content: bytes) -> None:
    record = put(root, f"studies/{study}/{relative}", content)
    manifest = json.loads((root / "provenance/study_snapshot.json").read_text())
    manifest["study_files"][study][relative] = record
    save(root, "provenance/study_snapshot.json", manifest)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "data_parts/../outside", "data_parts//part", "data_parts/./part",
                                  "C:/part", "data_parts\\part", "", None])
def test_reject_unsafe_paths(tmp_path, name):
    with pytest.raises(project.ProjectError, match="Unsafe manifest path"):
        project.safe_path(tmp_path, name)


def test_reject_chunk_outside_parts_prefix(tmp_path):
    with pytest.raises(project.ProjectError, match="under data_parts"):
        project.safe_path(tmp_path, "studies/original/cache", "data_parts")


def test_reject_symlinked_paths(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "data_parts").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(project.ProjectError, match="Symlink"):
        project.safe_path(tmp_path, "data_parts/part", "data_parts")


def test_lossless_restore_is_idempotent_and_relocation_safe(snapshot, tmp_path):
    root, content = snapshot
    relocated = tmp_path / "relocated checkout with spaces"
    # No files in this fixture depend on the original repository's host path.
    shutil.copytree(root, relocated, ignore=shutil.ignore_patterns(relocated.name))
    result = project.restore(relocated)
    target = relocated / result["restored"][0]
    assert target.read_bytes() == content
    previous = target.stat().st_mtime_ns
    assert project.restore(relocated)["already_present"] == [str(target.relative_to(relocated))]
    assert target.stat().st_mtime_ns == previous
    assert project.verify(relocated)["status"] == "pass"


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_missing_or_corrupt_parts_fail_before_writing(snapshot, damage):
    root, _ = snapshot
    part = root / "data_parts/bars.part-001"
    if damage == "missing":
        part.unlink()
    else:
        part.write_bytes(b"x" * part.stat().st_size)
    with pytest.raises(project.ProjectError, match="Cannot restore"):
        project.restore(root)
    assert not (root / "studies/crypto_intraday_5m/data/processed/bars.parquet").exists()
    assert not list(root.rglob(".restore-*"))


def test_damaged_part_fails_even_when_restored_target_exists(snapshot):
    root, _ = snapshot
    project.restore(root)
    (root / "data_parts/bars.part-000").unlink()
    assert project.verify(root)["status"] == "fail"
    with pytest.raises(project.ProjectError, match="missing"):
        project.restore(root)


def test_full_local_archive_may_omit_all_parts_after_whole_file_verification(snapshot):
    root, content = snapshot
    project.restore(root)
    shutil.rmtree(root / "data_parts")
    result = project.verify(root)
    assert result["status"] == "pass" and result["verified_chunks"] == 0
    assert result["chunk_cache_status"] == "omitted_whole_files_verified"
    result = project.restore(root)
    assert result["status"] == "pass" and not result["restored"]
    assert result["chunk_cache_status"] == "omitted_whole_files_verified"
    assert (root / "studies/crypto_intraday_5m/data/processed/bars.parquet").read_bytes() == content


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_missing_cache_never_permits_missing_or_corrupt_whole_targets(snapshot, damage):
    root, _ = snapshot
    project.restore(root)
    shutil.rmtree(root / "data_parts")
    target = root / "studies/crypto_intraday_5m/data/processed/bars.parquet"
    if damage == "missing":
        target.unlink()
    else:
        target.write_bytes(b"x" * target.stat().st_size)
    result = project.verify(root)
    assert result["status"] == "fail"
    assert result["chunk_cache_status"] == "absent_without_verified_targets"
    with pytest.raises(project.ProjectError, match="Chunk cache absent and whole target"):
        project.restore(root, force=True)


def test_empty_present_cache_is_not_silently_treated_as_absent(snapshot):
    root, _ = snapshot
    project.restore(root)
    shutil.rmtree(root / "data_parts")
    (root / "data_parts").mkdir()
    assert project.verify(root)["status"] == "fail"
    with pytest.raises(project.ProjectError, match="Cannot restore"):
        project.restore(root)


def test_corrupt_target_needs_explicit_force(snapshot):
    root, content = snapshot
    project.restore(root)
    target = root / "studies/crypto_intraday_5m/data/processed/bars.parquet"
    target.write_bytes(b"not the frozen target")
    with pytest.raises(project.ProjectError, match="--force"):
        project.restore(root)
    assert target.read_bytes() == b"not the frozen target"
    project.restore(root, force=True)
    assert target.read_bytes() == content


def test_restoration_manifest_must_agree_with_snapshot(snapshot):
    root, _ = snapshot
    parts = json.loads((root / "provenance/large_file_parts.json").read_text())
    parts["files"][0]["sha256"] = "0" * 64
    save(root, "provenance/large_file_parts.json", parts)
    with pytest.raises(project.ProjectError, match="disagrees with study snapshot"):
        project.restore(root)


def test_restore_rejects_part_traversal_in_manifest(snapshot):
    root, _ = snapshot
    parts = json.loads((root / "provenance/large_file_parts.json").read_text())
    parts["files"][0]["parts"][0]["path"] = "data_parts/../../outside"
    save(root, "provenance/large_file_parts.json", parts)
    with pytest.raises(project.ProjectError, match="Unsafe manifest path"):
        project.restore(root)


def test_part_order_is_verified_by_final_file_hash(snapshot):
    root, _ = snapshot
    parts = json.loads((root / "provenance/large_file_parts.json").read_text())
    parts["files"][0]["parts"].reverse()
    save(root, "provenance/large_file_parts.json", parts)
    with pytest.raises(project.ProjectError, match="Reconstructed target mismatch"):
        project.restore(root)
    assert not list(root.rglob(".restore-*"))
    assert not (root / "studies/crypto_intraday_5m/data/processed/bars.parquet").exists()


def test_verify_detects_missing_and_same_size_tampering(snapshot):
    root, _ = snapshot
    result = project.verify(root)
    assert result["status"] == "fail"
    assert result["failures"][0]["reason"] == "missing"
    project.restore(root)
    target = root / "studies/crypto_stat_arb/README.md"
    target.write_bytes(b"x" * target.stat().st_size)
    result = project.verify(root)
    assert result["status"] == "fail"
    assert {"path": "studies/crypto_stat_arb/README.md", "reason": "SHA-256 mismatch"} in result["failures"]


@pytest.mark.parametrize("extension", [".zip", ".zip.CHECKSUM"])
def test_optional_5m_cache_is_explicit_but_strict_mode_requires_it(snapshot, extension):
    root, _ = snapshot
    project.restore(root)
    relative = "data/raw/BTCUSDT/BTCUSDT-5m-2024-01" + extension
    add_file(root, "crypto_intraday_5m", relative, b"frozen optional archive")
    archive = root / "studies/crypto_intraday_5m" / relative
    assert project.verify(root)["optional_raw_cache_present"] == 1
    archive.unlink()
    result = project.verify(root)
    assert result["status"] == "pass"
    assert result["optional_raw_cache_missing"] == [f"studies/crypto_intraday_5m/{relative}"]
    strict = project.verify(root, strict_raw_cache=True)
    assert strict["status"] == "fail"
    assert strict["optional_raw_cache_missing"] == result["optional_raw_cache_missing"]
    assert strict["failures"] == [{"path": f"studies/crypto_intraday_5m/{relative}", "reason": "missing"}]


def test_present_optional_5m_cache_must_not_be_corrupted(snapshot):
    root, _ = snapshot
    project.restore(root)
    relative = "data/raw/BTCUSDT/optional.zip"
    add_file(root, "crypto_intraday_5m", relative, b"abc")
    (root / "studies/crypto_intraday_5m" / relative).write_bytes(b"bad")
    assert project.verify(root)["status"] == "fail"


def test_hourly_raw_and_5m_manifests_are_always_required(snapshot):
    root, _ = snapshot
    project.restore(root)
    add_file(root, "crypto_stat_arb", "data/raw/BTCUSDT/required.zip", b"hourly")
    add_file(root, "crypto_intraday_5m", "data/raw/manifest.json", b"{}")
    (root / "studies/crypto_stat_arb/data/raw/BTCUSDT/required.zip").unlink()
    (root / "studies/crypto_intraday_5m/data/raw/manifest.json").unlink()
    result = project.verify(root)
    assert result["status"] == "fail" and len(result["failures"]) == 2
    assert result["optional_raw_cache_missing"] == []


def test_noninteger_sizes_rejected(snapshot):
    root, _ = snapshot
    parts = json.loads((root / "provenance/large_file_parts.json").read_text())
    parts["files"][0]["bytes"] = True
    save(root, "provenance/large_file_parts.json", parts)
    with pytest.raises(project.ProjectError, match="Invalid byte count"):
        project.restore(root)


def test_suites_use_invoking_python_isolated_paths_and_exact_skips(snapshot, monkeypatch):
    root, _ = snapshot
    project.restore(root)
    calls = []
    monkeypatch.setenv("PYTHONPATH", "/old/host/global/path")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k nothing")
    monkeypatch.setenv("PYTEST_PLUGINS", "unrelated_plugin")

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        kwargs["stdout"].write("fake suite: all local tests passed\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(project.subprocess, "run", fake_run)
    result = project.test_suites(root)
    assert result["status"] == "pass"
    assert len(calls) == 4
    for (command, kwargs), name in zip(calls, project.SUITES):
        study, target = project.SUITES[name]
        assert command[:3] == [sys.executable, "-m", "pytest"]
        assert "no:cacheprovider" in command and command[-1] == target
        assert kwargs["cwd"] == root / "studies" / study
        assert kwargs["env"]["PYTHONPATH"].split(project.os.pathsep)[0] == str(root / "studies" / study / "src")
        assert "/old/host" not in kwargs["env"]["PYTHONPATH"]
        assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        assert kwargs["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
        assert "PYTEST_ADDOPTS" not in kwargs["env"] and "PYTEST_PLUGINS" not in kwargs["env"]
        assert kwargs["env"]["LOCAL_PROJECT_LEGACY_SKIP"] == project.LEGACY_SKIPS.get(name, "")
        assert Path(command[command.index("--basetemp") + 1]).is_relative_to(root / "local_outputs")
    assert Path(result["output_directory"], "summary.json").is_file()


def test_suite_failure_is_not_reported_as_success(snapshot, monkeypatch):
    root, _ = snapshot
    project.restore(root)
    monkeypatch.setattr(project.subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 2))
    assert project.test_suites(root, "original")["status"] == "fail"


def make_notebook(sources):
    return {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
        {"cell_type": "code", "metadata": {}, "source": source, "outputs": [], "execution_count": None} for source in sources
    ]}


def test_notebook_inspection_identifies_writes_shell_and_reselection(tmp_path):
    notebook = tmp_path / "test.ipynb"
    save(tmp_path, "test.ipynb", make_notebook(["%matplotlib inline\nfigure.savefig(ROOT/'figure.png')", "!curl example.invalid", "run_research(ROOT)"]))
    result = project.inspect_notebook(notebook)
    assert result["write_calls"] == [{"cell": 1, "line": 2, "call": "savefig"}]
    assert len(result["blocked_calls"]) == 2
    assert result["execution_mode"] == "private temporary study copy"


def test_notebook_execution_uses_private_copy_and_temporary_invoking_kernel(snapshot, monkeypatch):
    root, _ = snapshot
    project.restore(root)
    relative = project.NOTEBOOKS["original"][1]
    raw = json.dumps(make_notebook(["from pathlib import Path\nPath('private.txt').write_text('ok')"])) .encode()
    add_file(root, "crypto_stat_arb", relative, raw)
    original = root / "studies/crypto_stat_arb" / relative
    seen = []

    def fake_run(command, **kwargs):
        input_path, output_path, cwd, kernel_dir = map(Path, command[3:7])
        assert kwargs["cwd"] == cwd and cwd != root / "studies/crypto_stat_arb"
        assert input_path.is_relative_to(cwd)
        assert input_path.read_bytes() == original.read_bytes()
        assert output_path.is_relative_to(root / "local_outputs")
        spec = json.loads((kernel_dir / "local-project/kernel.json").read_text())
        assert spec["argv"][0] == sys.executable
        assert spec["argv"][1:3] == ["-m", "ipykernel_launcher"]
        assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        (cwd / "private.txt").write_text("local temporary write")
        output_path.write_text("executed output")
        seen.append(cwd)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(project.subprocess, "run", fake_run)
    result = project.notebooks(root, "original", execute=True)
    assert result["status"] == "pass" and len(seen) == 1
    assert not seen[0].exists()
    assert original.read_bytes() == raw
    assert not (root / "studies/crypto_stat_arb/private.txt").exists()


def test_private_copy_uses_real_copies_and_omits_only_optional_cache(tmp_path):
    source, target = tmp_path / "crypto_intraday_5m", tmp_path / "copy"
    put(source, "data/raw/month.zip", b"optional cache")
    put(source, "data/raw/manifest.json", b"required receipt")
    put(source, "datasets/history/data/raw/hourly.zip", b"frozen required extension cache")
    put(source, "outputs/selection.json", b"immutable")
    project.copy_study(source, target)
    assert not (target / "data/raw/month.zip").exists()
    assert (target / "data/raw/manifest.json").exists()
    assert (target / "datasets/history/data/raw/hourly.zip").exists()
    (target / "outputs/selection.json").write_bytes(b"changed private copy")
    assert (source / "outputs/selection.json").read_bytes() == b"immutable"


@pytest.mark.parametrize("study", ["crypto_stat_arb", "crypto_stat_arb_extensions"])
def test_private_hourly_copy_keeps_all_raw_freeze_evidence(tmp_path, study):
    source, target = tmp_path / study, tmp_path / "copy"
    put(source, "data/raw/month.zip", b"hourly raw")
    put(source, "data/raw/month.zip.CHECKSUM", b"hourly checksum")
    project.copy_study(source, target)
    assert (target / "data/raw/month.zip").read_bytes() == b"hourly raw"
    assert (target / "data/raw/month.zip.CHECKSUM").read_bytes() == b"hourly checksum"


@pytest.mark.parametrize("source", ["%run /some/path.py", "%pip install unrelated", "get_ipython().run_line_magic('run', 'unrelated.py')"])
def test_notebook_inspection_rejects_nonplotting_line_magics(tmp_path, source):
    save(tmp_path, "unsafe.ipynb", make_notebook([source]))
    assert project.inspect_notebook(tmp_path / "unsafe.ipynb")["blocked_calls"]


def test_notebook_runner_explicitly_cleans_up_supplied_kernel(tmp_path, monkeypatch):
    from types import SimpleNamespace
    seen = {}
    notebook = SimpleNamespace(metadata={})
    monkeypatch.setitem(sys.modules, "nbformat", SimpleNamespace(read=lambda *a, **k: notebook, write=lambda *a: None))

    def client_factory(*args, **kwargs):
        return SimpleNamespace(execute=lambda **options: seen.update(options))

    monkeypatch.setitem(sys.modules, "nbclient", SimpleNamespace(NotebookClient=client_factory))
    monkeypatch.setitem(sys.modules, "jupyter_client", SimpleNamespace(KernelManager=lambda **k: None))
    monkeypatch.setitem(sys.modules, "jupyter_client.kernelspec", SimpleNamespace(KernelSpecManager=lambda **k: None))
    project.notebook_runner(tmp_path / "in.ipynb", tmp_path / "out.ipynb", tmp_path, tmp_path, 60)
    assert seen == {"cwd": str(tmp_path), "cleanup_kc": True}


def test_cli_verification_exit_codes_and_json(snapshot, capsys):
    root, _ = snapshot
    assert project.main(["--root", str(root), "verify", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "fail"
    assert project.main(["--root", str(root), "restore"]) == 0
    capsys.readouterr()
    assert project.main(["--root", str(root), "verify", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pass"
