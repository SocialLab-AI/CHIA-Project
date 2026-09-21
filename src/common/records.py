"""Integration-owned atomic records; one combined record per candidate attempt."""

import importlib.metadata
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import hashlib
from src.common.candidate import ROOT, validate_schema
from src.common.security import canonical, no_secrets, within
from src.common.errors import MetricsError


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical(value)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o664)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def atomic_text(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def provenance():
    def git(*args):
        try:
            return subprocess.check_output(
                [
                    "git",
                    "-c",
                    f"safe.directory={ROOT.as_posix()}",
                    "-C",
                    str(ROOT),
                    *args,
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip()
        except (OSError, subprocess.SubprocessError):
            return None

    versions = {}
    for package in ("chialoops", "ray", "google-genai", "jsonschema", "pyyaml"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    source_hashes = {}
    for directory in ("src", "scripts", "gem5", "experiment-contracts"):
        for path in (ROOT / directory).rglob("*"):
            if (
                path.is_file()
                and path.suffix in {".py", ".c", ".yaml", ".json"}
                and "results" not in path.parts
                and ".local." not in path.name
            ):
                source_hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty_worktree": bool(git("status", "--porcelain")),
        "control_hostname": socket.gethostname(),
        "runtime_versions": versions,
        "schema_version": "0.3.0",
        "source_hashes": source_hashes,
    }


def validate_record(record):
    no_secrets(record)
    validate_schema(record, "loop_record")
    if record["status"] == "completed":
        from src.orchestration.nodes.evaluation import verify_results
        from src.common.security import digest

        if digest(record["candidate"]) != record["candidate_id"]:
            raise MetricsError("Record candidate hash mismatch.")
        actual = verify_results(
            record["candidate"],
            record["candidate_id"],
            record["software_result"],
            record["hardware_result"],
            record["energy_result"],
        )
        if actual != record["evaluation"] or record["failure"] is not None:
            raise MetricsError(
                "Record evaluation is inconsistent with verified results."
            )
    elif not record["failure"]:
        raise MetricsError("Failed/rejected record requires failure evidence.")


def persist_record(record, results_root):
    validate_record(record)
    directory = within(results_root, record["campaign_id"])
    destination = within(directory / "runs", record["run_id"] + ".json")
    atomic_json(destination, record)
    atomic_json(within(directory / "events", record["run_id"] + ".json"), record["events"])
    if record.get("software_result"):
        atomic_json(within(directory / "native", record["run_id"] + ".json"), record["software_result"])
    if record.get("energy_result"):
        atomic_json(within(directory / "energy", record["run_id"] + ".json"), record["energy_result"])
    return record


def build_run_record(
    *, run_id, experiment_id, status, schema_version="0.2.0", **kwargs
):
    """Legacy record helper retained for callers; new loop uses loop_record validation."""
    return {
        "schema_version": schema_version,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "status": status,
        **kwargs,
    }
