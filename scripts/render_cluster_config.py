"""Infrastructure-owned Adam/YSF overlay generator; never reads key contents or changes servers."""

import argparse
import ipaddress
import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def render(values):
    config = yaml.safe_load((ROOT / "infra/chia/cluster.yaml").read_text())
    head = str(ipaddress.ip_address(values["CHIA_HEAD_IP"]))
    worker = str(ipaddress.ip_address(values["CHIA_GEM5_IP"]))
    if head == worker:
        raise ValueError("Head and gem5 host must be distinct.")
    for name in (
        "CHIA_PROJECT_PATH",
        "CHIA_SSH_KEY",
        "CHIA_HEAD_ENV",
        "CHIA_WORKER_ENV",
    ):
        if not values[name].startswith("/") or any(
            c in values[name] for c in "\n\r\"'`$;|& "
        ):
            raise ValueError(
                f"{name} must be an absolute Linux path without shell metacharacters or spaces."
            )
    config["provider"]["head_ip"] = head
    config["auth"]["ssh_private_key"] = values["CHIA_SSH_KEY"]
    config["auth"]["overrides"] = {
        worker: {"ssh_user": "ysf", "ssh_private_key": values["CHIA_SSH_KEY"]}
    }
    config["available_node_types"]["gem5_worker"]["compatible_ips"] = [worker]
    config["file_mounts"] = {"/tmp/chia-project/": values["CHIA_PROJECT_PATH"]}
    project_pythonpath = "export PYTHONPATH=/tmp/chia-project"
    config["head_env_commands"] = [
        "source " + values["CHIA_HEAD_ENV"],
        project_pythonpath,
    ]
    config["available_node_types"]["gem5_worker"]["worker_env_commands"] = [
        "source " + values["CHIA_WORKER_ENV"],
        project_pythonpath,
    ]
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "infra/chia/cluster.local.yaml"
    )
    args = parser.parse_args()
    names = (
        "CHIA_HEAD_IP",
        "CHIA_GEM5_IP",
        "CHIA_PROJECT_PATH",
        "CHIA_SSH_KEY",
        "CHIA_HEAD_ENV",
        "CHIA_WORKER_ENV",
    )
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        parser.error("Required environment variable names: " + ", ".join(missing))
    if not args.output.name.endswith(".local.yaml"):
        parser.error("Output must be ignored *.local.yaml")
    args.output.write_text(
        yaml.safe_dump(
            render({name: os.environ[name] for name in names}), sort_keys=False
        )
    )
    print("Wrote cluster overlay; no server was contacted.")


if __name__ == "__main__":
    main()
