#!/usr/bin/env python3
"""Portable, offline access to the byte-preserved research snapshot.

The restore/verify/inspection commands use only the standard library. Tests and
notebook execution use the invoking Python's dependencies, never editable
installs, exchange credentials, downloads, or historical host paths.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone

STUDIES = (
    "crypto_stat_arb", "crypto_stat_arb_extensions", "crypto_intraday_5m",
    "crypto_stat_arb_report_revision",
)
SUITES = {
    "original": ("crypto_stat_arb", "tests"),
    "extension": ("crypto_stat_arb_extensions", "tests"),
    "5m": ("crypto_intraday_5m", "tests"),
    "time-scale": ("crypto_stat_arb", "outputs/followups/time_scale_scan"),
}
NOTEBOOKS = {
    "original": ("crypto_stat_arb", "notebooks/crypto_stat_arb_research.ipynb"),
    "extension": ("crypto_stat_arb_extensions", "notebooks/expanded_crypto_research.ipynb"),
    "5m": ("crypto_intraday_5m", "notebooks/intraday_5m_research.ipynb"),
    "time-scale": ("crypto_stat_arb", "outputs/followups/time_scale_scan/time_scale_research.ipynb"),
}
LEGACY_SKIPS = {
    "extension": "test_results.py::test_original_project_and_bundle_still_unchanged",
    "5m": "test_results.py::test_old_projects_and_bundles_preserved",
}
LEGACY_REASON = (
    "Historical external project ZIP/folder preservation is not a portable "
    "checkout dependency; local study bytes are independently SHA-256 verified."
)
CHUNK_SIZE = 1024 * 1024


class ProjectError(RuntimeError):
    """A manifest, cache, or executable snapshot failed a safety/integrity gate."""


def safe_path(root: Path, relative: str, prefix: str | None = None) -> Path:
    """Accept canonical relative POSIX paths, never traversal or symlinks."""
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ProjectError(f"Unsafe manifest path: {relative!r}")
    parts = relative.split("/")
    if any(p in ("", ".", "..") for p in parts) or PurePosixPath(relative).is_absolute():
        raise ProjectError(f"Unsafe manifest path: {relative!r}")
    if prefix and not relative.startswith(prefix.rstrip("/") + "/"):
        raise ProjectError(f"Path must be under {prefix}/: {relative}")
    root = Path(root).resolve()
    path = root.joinpath(*parts)
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise ProjectError(f"Symlink not allowed in manifest path: {relative}")
    if not path.resolve().is_relative_to(root):
        raise ProjectError(f"Manifest path escapes repository: {relative}")
    return path


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProjectError(f"Cannot read manifest {path}: {error}") from error
    if not isinstance(value, dict):
        raise ProjectError(f"Manifest must be an object: {path}")
    return value


def validate_record(record: dict, description: str) -> None:
    if not isinstance(record, dict):
        raise ProjectError(f"Invalid hash record: {description}")
    size = record.get("bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ProjectError(f"Invalid byte count: {description}")
    if not isinstance(record.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
        raise ProjectError(f"Invalid SHA-256: {description}")


def fingerprint(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(CHUNK_SIZE):
            digest.update(block)
            size += len(block)
    return {"sha256": digest.hexdigest(), "bytes": size}


def file_problem(path: Path, record: dict) -> str | None:
    if not path.is_file():
        return "missing"
    try:
        if path.stat().st_size != record["bytes"]:
            return "byte count mismatch"
        if fingerprint(path)["sha256"] != record["sha256"]:
            return "SHA-256 mismatch"
    except OSError as error:
        return f"unreadable: {error}"
    return None


def optional_raw_cache(study: str, relative: str) -> bool:
    return (study == "crypto_intraday_5m" and relative.startswith("data/raw/")
            and (relative.endswith(".zip") or relative.endswith(".zip.CHECKSUM")))


def study_records(root: Path) -> dict:
    value = read_json(safe_path(root, "provenance/study_snapshot.json"))
    records = value.get("study_files")
    if not isinstance(records, dict) or not records:
        raise ProjectError("study_snapshot.json must contain nonempty study_files")
    if set(records) != set(STUDIES):
        raise ProjectError("study_snapshot.json must inventory all four frozen studies")
    for study, files in records.items():
        if study not in STUDIES or not isinstance(files, dict) or not files:
            raise ProjectError(f"Invalid study inventory: {study}")
        for relative, record in files.items():
            safe_path(root, f"studies/{study}/{relative}", "studies")
            validate_record(record, f"{study}/{relative}")
    return records


def part_records(root: Path) -> list:
    value = read_json(safe_path(root, "provenance/large_file_parts.json"))
    records = value.get("files")
    if not isinstance(records, list):
        raise ProjectError("large_file_parts.json must contain files list")
    targets, chunks = set(), set()
    for record in records:
        validate_record(record, "large-file target")
        target = record.get("path")
        safe_path(root, target, "studies")
        if target in targets:
            raise ProjectError(f"Duplicate restoration target: {target}")
        targets.add(target)
        parts = record.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ProjectError(f"Missing part list: {target}")
        for part in parts:
            validate_record(part, f"part of {target}")
            name = part.get("path")
            safe_path(root, name, "data_parts")
            if name in chunks:
                raise ProjectError(f"Duplicate chunk path: {name}")
            chunks.add(name)
        if sum(p["bytes"] for p in parts) != record["bytes"]:
            raise ProjectError(f"Part byte counts do not equal target: {target}")
    # Restoration may write only targets authenticated by the frozen snapshot.
    inventory = study_records(root)
    for record in records:
        target_parts = record["path"].split("/", 2)
        if len(target_parts) != 3:
            raise ProjectError(f"Invalid study restoration target: {record['path']}")
        _, study, relative = target_parts
        expected = inventory.get(study, {}).get(relative)
        if not expected or any(record[key] != expected[key] for key in ("bytes", "sha256")):
            raise ProjectError(f"Restoration target disagrees with study snapshot: {record['path']}")
    return records


def restore(root: Path, force: bool = False) -> dict:
    """Concatenate verified parts atomically, without rewriting valid targets."""
    root = Path(root).resolve()
    records = part_records(root)
    # The full-local archive ships authenticated whole files instead of
    # duplicate chunks. Only a completely absent chunk directory is optional;
    # a partial or corrupted present cache always fails closed.
    if not safe_path(root, "data_parts").exists():
        for record in records:
            problem = file_problem(safe_path(root, record["path"], "studies"), record)
            if problem:
                raise ProjectError(f"Chunk cache absent and whole target {record['path']}: {problem}")
        return {"status": "pass", "restored": [], "already_present": [r["path"] for r in records],
                "chunk_cache_status": "omitted_whole_files_verified"}
    # Fail before any writes if any part is missing or damaged, even if a target
    # already exists. This also checks the separately shipped Git chunk cache.
    for record in records:
        for part in record["parts"]:
            problem = file_problem(safe_path(root, part["path"], "data_parts"), part)
            if problem:
                raise ProjectError(f"Cannot restore: {part['path']}: {problem}")
    restored, already_present = [], []
    for record in records:
        destination = safe_path(root, record["path"], "studies")
        problem = file_problem(destination, record)
        if not problem:
            already_present.append(record["path"])
            continue
        if destination.exists() and not force:
            raise ProjectError(f"Refusing to replace damaged target {record['path']}; use restore --force")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".restore-", delete=False) as stream:
                temporary = Path(stream.name)
                whole_digest, whole_size = hashlib.sha256(), 0
                for part in record["parts"]:
                    part_digest, part_size = hashlib.sha256(), 0
                    with safe_path(root, part["path"], "data_parts").open("rb") as source:
                        while block := source.read(CHUNK_SIZE):
                            stream.write(block)
                            whole_digest.update(block)
                            whole_size += len(block)
                            part_digest.update(block)
                            part_size += len(block)
                    if part_size != part["bytes"] or part_digest.hexdigest() != part["sha256"]:
                        raise ProjectError(f"Part changed while restoring: {part['path']}")
                stream.flush()
                os.fsync(stream.fileno())
            if whole_size != record["bytes"] or whole_digest.hexdigest() != record["sha256"]:
                raise ProjectError(f"Reconstructed target mismatch: {record['path']}")
            # Recheck lexical path safety immediately before publishing.
            safe_path(root, record["path"], "studies")
            os.replace(temporary, destination)
            restored.append(record["path"])
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"status": "pass", "restored": restored, "already_present": already_present,
            "chunk_cache_status": "present_verified"}


def verify(root: Path, strict_raw_cache: bool = False) -> dict:
    """Hash every delivered study file and every lossless Git chunk."""
    root = Path(root).resolve()
    inventory = study_records(root)
    checked, optional_present, missing_optional, failures = 0, 0, [], []
    counts = {}
    for study, files in inventory.items():
        counts[study] = len(files)
        for relative, record in files.items():
            name = f"studies/{study}/{relative}"
            path = safe_path(root, name, "studies")
            problem = file_problem(path, record)
            optional = optional_raw_cache(study, relative)
            if problem == "missing" and optional:
                missing_optional.append(name)
                if strict_raw_cache:
                    failures.append({"path": name, "reason": problem})
            elif problem:
                failures.append({"path": name, "reason": problem})
            else:
                checked += 1
                optional_present += int(optional)
    chunk_count = 0
    records = part_records(root)
    if not safe_path(root, "data_parts").exists():
        whole_files_valid = all(not file_problem(safe_path(root, r["path"], "studies"), r) for r in records)
        chunk_status = "omitted_whole_files_verified" if whole_files_valid else "absent_without_verified_targets"
        if not whole_files_valid:
            failures.append({"path": "data_parts/", "reason": "chunk cache absent and whole targets not verified"})
    else:
        chunk_status = "present_verified"
        for record in records:
            for part in record["parts"]:
                problem = file_problem(safe_path(root, part["path"], "data_parts"), part)
                if problem:
                    failures.append({"path": part["path"], "reason": problem})
                    chunk_status = "present_invalid"
                else:
                    chunk_count += 1
    return {
        "status": "fail" if failures else "pass", "study_file_counts": counts,
        "verified_study_files": checked, "verified_chunks": chunk_count,
        "chunk_cache_status": chunk_status,
        "optional_raw_cache_present": optional_present,
        "optional_raw_cache_missing": missing_optional,
        "strict_raw_cache": strict_raw_cache, "failures": failures,
        "historical_external_bundles": "Not supplied or checked; paths in frozen receipts are historical provenance only.",
    }


def require_verified(root: Path) -> dict:
    result = verify(root)
    if result["failures"]:
        examples = "; ".join(f"{f['path']}: {f['reason']}" for f in result["failures"][:8])
        raise ProjectError(f"Snapshot verification failed: {examples}. Run restore if chunked targets are missing.")
    return result


def output_directory(root: Path, label: str) -> Path:
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    path = safe_path(root, f"local_outputs/{label}-{name}", "local_outputs")
    path.mkdir(parents=True)
    return path


def execution_environment(root: Path, study: str, extra_paths: list[Path] | None = None) -> dict:
    env = os.environ.copy()
    # Inherited pytest selection flags/plugins can hide test cases or import
    # unrelated global code even with entry-point plugin autoload disabled.
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    paths = [root / "studies" / study / "src", *(extra_paths or [])]
    # Replace inherited PYTHONPATH: no other project or editable install is
    # required. Independent subprocesses avoid cross-study import shadowing.
    env.update(PYTHONPATH=os.pathsep.join(map(str, paths)), PYTHONDONTWRITEBYTECODE="1",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", MPLBACKEND="Agg")
    return env


def test_suites(root: Path, suite: str = "all") -> dict:
    preflight = require_verified(root)
    names = list(SUITES) if suite == "all" else [suite]
    output = output_directory(root, "tests")
    results = []
    with tempfile.TemporaryDirectory(prefix="local-project-pytest-") as temp:
        plugin = Path(temp) / "local_project_plugin.py"
        plugin.write_text(
            "import os\nimport pytest\n"
            "def pytest_collection_modifyitems(items):\n"
            "    node = os.environ.get('LOCAL_PROJECT_LEGACY_SKIP')\n"
            "    for item in items:\n"
            "        if node and (item.nodeid == node or item.nodeid.endswith('/' + node)):\n"
            "            item.add_marker(pytest.mark.skip(reason=os.environ['LOCAL_PROJECT_SKIP_REASON']))\n",
            encoding="utf-8",
        )
        for name in names:
            study, target = SUITES[name]
            study_root = root / "studies" / study
            env = execution_environment(root, study, [Path(temp)])
            env.update(LOCAL_PROJECT_LEGACY_SKIP=LEGACY_SKIPS.get(name, ""),
                       LOCAL_PROJECT_SKIP_REASON=LEGACY_REASON,
                       MPLCONFIGDIR=str(output / "matplotlib"))
            command = [sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider",
                       "-p", "local_project_plugin", "--basetemp", str(output / f"{name}-temp"), target]
            print(f"Running {name}: {sys.executable} -m pytest ({study_root})", flush=True)
            if name in LEGACY_SKIPS:
                print(f"Explicit legacy skip: {LEGACY_SKIPS[name]} — {LEGACY_REASON}", flush=True)
            log = output / f"{name}.log"
            with log.open("w", encoding="utf-8") as stream:
                completed = subprocess.run(command, cwd=study_root, env=env, stdout=stream, stderr=subprocess.STDOUT)
            print(log.read_text(encoding="utf-8"), end="", flush=True)
            results.append({"suite": name, "returncode": completed.returncode, "log": str(log),
                            "legacy_skip": LEGACY_SKIPS.get(name), "command": command})
    postflight = verify(root)
    result = {"status": "pass" if all(r["returncode"] == 0 for r in results) and not postflight["failures"] else "fail",
              "python": sys.executable, "suites": results, "output_directory": str(output),
              "snapshot_preflight": preflight["status"], "snapshot_postflight": postflight["status"],
              "postflight_failures": postflight["failures"]}
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


WRITE_CALLS = {"write_text", "write_bytes", "to_csv", "to_parquet", "to_excel", "savefig",
               "mkdir", "unlink", "dump", "write_json"}
FORBIDDEN_CALLS = {"download", "download_and_prepare", "prepare_holdout", "prepare_history",
                   "run_research", "screen_history", "evaluate_holdout", "system", "Popen",
                   "run_cell_magic", "getoutput"}


def inspect_notebook(path: Path) -> dict:
    """Inspect executable cells before running, including IPython magics."""
    notebook = read_json(path)
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        raise ProjectError(f"Invalid notebook cells: {path}")
    writes, blocked, external_paths = [], [], []
    for number, cell in enumerate(cells, 1):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", [])
        source = "".join(source) if isinstance(source, list) else source
        if not isinstance(source, str):
            raise ProjectError(f"Invalid notebook source: {path}, cell {number}")
        lines = source.splitlines()
        for line_number, line in enumerate(lines, 1):
            if re.search(r"/(?:Users|home)/", line):
                external_paths.append({"cell": number, "line": line_number, "source": line.strip()})
            if line.lstrip().startswith(("!", "%%")):
                blocked.append({"cell": number, "line": line_number, "source": line.strip(), "reason": "shell/cell magic"})
            elif line.lstrip().startswith("%") and line.strip() != "%matplotlib inline":
                blocked.append({"cell": number, "line": line_number, "source": line.strip(), "reason": "non-plotting line magic"})
        # Retained notebooks use only the harmless matplotlib line magic.
        parseable = "\n".join("" if line.lstrip().startswith(("%", "!")) else line for line in lines)
        try:
            tree = ast.parse(parseable)
        except SyntaxError as error:
            blocked.append({"cell": number, "line": error.lineno, "reason": "unrecognized executable syntax"})
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
            item = {"cell": number, "line": node.lineno, "call": name}
            if name in WRITE_CALLS:
                writes.append(item)
            if name in FORBIDDEN_CALLS:
                blocked.append({**item, "reason": "download, rerun/reselection, or external process"})
            if name == "run_line_magic" and not (len(node.args) == 2 and
                    all(isinstance(arg, ast.Constant) for arg in node.args) and
                    [arg.value for arg in node.args] == ["matplotlib", "inline"]):
                blocked.append({**item, "reason": "non-plotting line magic"})
            if name in {"run", "call", "check_call", "check_output"} and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                blocked.append({**item, "reason": "external process"})
            if name == "open" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                if isinstance(node.args[1].value, str) and any(mode in node.args[1].value for mode in "wax+"):
                    writes.append(item)
    return {"path": str(path), "write_calls": writes, "blocked_calls": blocked,
            "external_executable_paths": external_paths, "execution_mode": "private temporary study copy"}


def copy_study(source: Path, destination: Path) -> None:
    """Use real copies, never hard links that could mutate the frozen snapshot."""
    def ignore(directory, names):
        ignored = {name for name in names if name in {"__pycache__", ".pytest_cache", ".git", "tmp"}
                   or name.endswith(".egg-info")}
        if source.name == "crypto_intraday_5m" and Path(directory).is_relative_to(source / "data" / "raw"):
            ignored.update(name for name in names if name.endswith((".zip", ".zip.CHECKSUM")))
        return ignored
    # Missing raw five-minute ZIPs are irrelevant to notebook cached reads.
    shutil.copytree(source, destination, ignore=ignore, symlinks=False)


def notebook_runner(input_path: Path, output_path: Path, cwd: Path, kernel_directory: Path, timeout: int) -> None:
    """Executed in a fresh subprocess; optional Jupyter imports stay local."""
    import nbformat
    from nbclient import NotebookClient
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpecManager

    notebook = nbformat.read(input_path, as_version=4)
    notebook.metadata["kernelspec"] = {"name": "local-project", "display_name": "Local project Python", "language": "python"}
    spec_manager = KernelSpecManager(kernel_dirs=[str(kernel_directory)])
    manager = KernelManager(kernel_name="local-project", kernel_spec_manager=spec_manager)
    client = NotebookClient(notebook, timeout=timeout, km=manager, allow_errors=False,
                            resources={"metadata": {"path": str(cwd)}})
    try:
        # An explicitly supplied manager is not owned by nbclient; request
        # cleanup so channels/kernel terminate before deleting its workspace.
        client.execute(cwd=str(cwd), cleanup_kc=True)
    finally:
        # Keep useful cell/error evidence if execution fails, but nowhere inside
        # a delivered notebook or frozen study.
        notebook.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        nbformat.write(notebook, output_path)


def notebooks(root: Path, notebook: str = "primary", execute: bool = False, timeout: int = 600) -> dict:
    names = (["original", "extension", "5m"] if notebook == "primary" else
             list(NOTEBOOKS) if notebook == "all" else [notebook])
    inspections = []
    for name in names:
        study, relative = NOTEBOOKS[name]
        report = inspect_notebook(safe_path(root, f"studies/{study}/{relative}", "studies"))
        inspections.append({"notebook": name, **report})
    if not execute:
        return {"status": "inspected", "notebooks": inspections,
                "note": "Use notebooks --execute to run verified cached analyses in private study copies; results go only to local_outputs/."}
    require_verified(root)
    if any(i["blocked_calls"] or i["external_executable_paths"] for i in inspections):
        raise ProjectError("Notebook inspection found forbidden calls or external executable paths; refusing execution. See notebooks inspection output.")
    output = output_directory(root, "notebooks")
    results = []
    for inspection in inspections:
        name = inspection["notebook"]
        study, relative = NOTEBOOKS[name]
        print(f"Running {name} in a private temporary study copy; detected {len(inspection['write_calls'])} write calls.", flush=True)
        with tempfile.TemporaryDirectory(prefix="local-project-notebook-") as temp:
            temp_root = Path(temp)
            study_copy = temp_root / "studies" / study
            copy_study(root / "studies" / study, study_copy)
            kernel_directory = temp_root / "kernels"
            spec = kernel_directory / "local-project"
            spec.mkdir(parents=True)
            env = execution_environment(temp_root, study)
            env.update(MPLCONFIGDIR=str(output / "matplotlib"), IPYTHONDIR=str(temp_root / "ipython"),
                       JUPYTER_CONFIG_DIR=str(temp_root / "jupyter-config"), JUPYTER_RUNTIME_DIR=str(temp_root / "jupyter-runtime"))
            (spec / "kernel.json").write_text(json.dumps({"argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                                                        "display_name": "Local project Python", "language": "python"}), encoding="utf-8")
            input_path = study_copy / relative
            output_path = output / f"{name}.ipynb"
            command = [sys.executable, str(Path(__file__).resolve()), "_notebook-runner", str(input_path),
                       str(output_path), str(study_copy), str(kernel_directory), str(timeout)]
            log = output / f"{name}.log"
            with log.open("w", encoding="utf-8") as stream:
                completed = subprocess.run(command, cwd=study_copy, env=env, stdout=stream, stderr=subprocess.STDOUT)
            # Time-scale notebook writes plots only in its private copy. Export
            # them without changing its computational cells or hash checks.
            if name == "time-scale":
                source_figures = study_copy / "outputs/followups/time_scale_scan/figures"
                if source_figures.exists():
                    shutil.copytree(source_figures, output / "time-scale-figures")
            results.append({"notebook": name, "returncode": completed.returncode,
                            "executed_notebook": str(output_path), "log": str(log), "inspection": inspection})
            print(f"{name}: {'pass' if completed.returncode == 0 else 'fail'}; {output_path}", flush=True)
            if completed.returncode:
                print(log.read_text(encoding="utf-8"), end="", flush=True)
    postflight = verify(root)
    result = {"status": "pass" if all(r["returncode"] == 0 for r in results) and not postflight["failures"] else "fail",
              "python": sys.executable, "notebooks": results, "output_directory": str(output),
              "snapshot_postflight": postflight["status"], "postflight_failures": postflight["failures"]}
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def display_result(result: dict, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return
    print(f"Status: {result['status']}")
    if "verified_study_files" in result:
        print(f"Verified {result['verified_study_files']} study files and {result['verified_chunks']} chunks.")
        print(f"Chunk cache: {result['chunk_cache_status']}")
        missing = result["optional_raw_cache_missing"]
        print(f"Optional 5m raw ZIP/checksum cache: {result['optional_raw_cache_present']} present, {len(missing)} missing.")
        if missing:
            print("The normalized data/results remain required. Missing optional paths (use --json for the complete inventory):")
            for name in missing[:10]:
                print(f"  {name}")
            if len(missing) > 10:
                print(f"  ... {len(missing) - 10} more explicitly inventoried in --json output.")
        for failure in result["failures"]:
            print(f"FAIL: {failure['path']}: {failure['reason']}")
        print(result["historical_external_bundles"])
    elif "restored" in result:
        for name in result["restored"]:
            print(f"Restored: {name}")
        print(f"Already valid: {len(result['already_present'])}")
        print(f"Chunk cache: {result['chunk_cache_status']}")
    elif result["status"] == "inspected":
        for report in result["notebooks"]:
            print(f"{report['notebook']}: {len(report['write_calls'])} writes, {len(report['blocked_calls'])} blocked calls; {report['execution_mode']}")
            for item in report["write_calls"] + report["blocked_calls"] + report["external_executable_paths"]:
                print("  " + json.dumps(item))
        print(result["note"])
    if "output_directory" in result:
        print(f"Local outputs: {result['output_directory']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Relocated checkout root (default: this script's repository)")
    commands = parser.add_subparsers(dest="command", required=True)
    restore_parser = commands.add_parser("restore", help="Losslessly restore large cached parquets from verified Git parts")
    restore_parser.add_argument("--force", action="store_true", help="Replace an existing corrupted large-file target only")
    verify_parser = commands.add_parser("verify", help="Verify every required snapshot hash and optional cache if present")
    verify_parser.add_argument("--strict-raw-cache", action="store_true", help="Also require excluded 5m raw ZIP/checksum archives")
    test_parser = commands.add_parser("test", help="Run four isolated local pytest suites, without editable installs")
    test_parser.add_argument("--suite", choices=["all", *SUITES], default="all")
    notebook_parser = commands.add_parser("notebooks", help="Inspect delivered notebooks; optionally execute private copies")
    notebook_parser.add_argument("--notebook", choices=["primary", "all", *NOTEBOOKS], default="primary")
    notebook_parser.add_argument("--execute", action="store_true")
    notebook_parser.add_argument("--timeout", type=int, default=600, help="Execution timeout per cell in seconds")
    for command in (restore_parser, verify_parser, test_parser, notebook_parser):
        command.add_argument("--json", action="store_true", help="Print a structured complete result")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        if args.command == "restore":
            result = restore(root, args.force)
        elif args.command == "verify":
            result = verify(root, args.strict_raw_cache)
        elif args.command == "test":
            result = test_suites(root, args.suite)
        else:
            if args.timeout < 1:
                raise ProjectError("Notebook timeout must be positive")
            result = notebooks(root, args.notebook, args.execute, args.timeout)
        display_result(result, args.json)
        return 1 if result["status"] == "fail" else 0
    except (ProjectError, OSError, ImportError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Private implementation entry point, not a trading/research command.
    if len(sys.argv) > 1 and sys.argv[1] == "_notebook-runner":
        notebook_runner(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]), int(sys.argv[6]))
    else:
        raise SystemExit(main())
