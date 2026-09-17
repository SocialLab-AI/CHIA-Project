"""Deployment-owned checks for project imports on CHIA head and worker processes."""

from pathlib import Path

import yaml

from scripts.render_cluster_config import render


ROOT = Path(__file__).resolve().parents[1]


def test_chia_nodes_receive_synchronized_project_on_pythonpath():
    config = yaml.safe_load((ROOT / "infra/chia/cluster.yaml").read_text())
    project_path = "/tmp/chia-project"

    assert f"export PYTHONPATH={project_path}" in config["head_env_commands"]
    worker = config["available_node_types"]["gem5_worker"]
    assert f"export PYTHONPATH={project_path}" in worker["worker_env_commands"]
    assert project_path + "/" in config["file_mounts"]


def test_head_advertises_llama_cpp_and_no_ollama_resource():
    config = yaml.safe_load((ROOT / "infra/chia/cluster.yaml").read_text())
    command = " ".join(config["head_start_ray_commands"])
    assert '"llama_cpp":1' in command
    assert '"ollama":1' not in command


def test_generated_cluster_overlay_preserves_project_pythonpath():
    config = render(
        {
            "CHIA_HEAD_IP": "192.0.2.10",
            "CHIA_GEM5_IP": "192.0.2.11",
            "CHIA_HEAD_USER": "control_user",
            "CHIA_WORKER_USER": "simulation_user",
            "CHIA_PROJECT_PATH": "/srv/chia-project",
            "CHIA_SSH_KEY": "/home/chia/.ssh/id_ed25519",
            "CHIA_HEAD_ENV": "/opt/chia/.venv/bin/activate",
            "CHIA_WORKER_ENV": "/opt/chia/.venv/bin/activate",
        }
    )

    assert "export PYTHONPATH=/tmp/chia-project" in config["head_env_commands"]
    worker = config["available_node_types"]["gem5_worker"]
    assert "export PYTHONPATH=/tmp/chia-project" in worker["worker_env_commands"]
    assert config["auth"]["ssh_user"] == "control_user"
    assert config["auth"]["overrides"]["192.0.2.11"]["ssh_user"] == "simulation_user"
