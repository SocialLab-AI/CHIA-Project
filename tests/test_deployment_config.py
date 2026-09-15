"""Deployment-owned checks for project imports on CHIA head and worker processes."""

from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_chia_nodes_receive_synchronized_project_on_pythonpath():
    config = yaml.safe_load((ROOT / "infra/chia/cluster.yaml").read_text())
    project_path = "/tmp/chia-project"

    assert f"export PYTHONPATH={project_path}" in config["head_env_commands"]
    worker = config["available_node_types"]["gem5_worker"]
    assert f"export PYTHONPATH={project_path}" in worker["worker_env_commands"]
    assert project_path + "/" in config["file_mounts"]


def test_standalone_ollama_script_bootstraps_project_imports():
    script = ROOT / "scripts/run_ollama_experiment.py"
    command = (
        "import runpy; "
        f"runpy.run_path({str(script)!r}, run_name='deployment_import_probe')"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", command],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
