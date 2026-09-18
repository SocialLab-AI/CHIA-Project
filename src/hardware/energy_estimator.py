"""Run Accelergy + McPAT for gem5 cache-energy estimation."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import yaml


ENERGY_SCOPE = (
    "Dynamic cache energy for two L1I caches, two L1D caches, "
    "and one shared L2 cache. Excludes processor-core logic, "
    "DRAM, interconnect, TLB, and static/leakage energy."
)


class EnergyEstimatorError(RuntimeError):
    """Raised when energy estimation cannot be completed."""


def cache_component(
    name: str,
    cache_type: str,
    configuration: dict,
) -> dict:
    return {
        "name": name,
        "class": "cache",
        "attributes": {
            "n_rd_ports": 1,
            "n_wr_ports": 1,
            "n_rdwr_ports": 1,
            "n_banks": 1,
            "cache_type": cache_type,
            "size": configuration["size_bytes"],
            "associativity": configuration["associativity"],
            "data_latency": configuration["data_latency_cycles"],
            "block_size": configuration["block_size_bytes"],
            "mshr_size": configuration["mshr_entries"],
            "tag_size": 64,
            "write_buffer_size": configuration[
                "write_buffer_entries"
            ],
        },
    }


def action_component(name: str, actions: dict) -> dict:
    return {
        "name": name,
        "action_counts": [
            {
                "name": action,
                "counts": count,
            }
            for action, count in actions.items()
        ],
    }


def build_accelergy_inputs(mapping: dict) -> tuple[dict, dict]:
    assumptions = mapping["mcpat_assumptions"]
    architecture_components = []
    action_components = []

    for core in mapping["cores"]:
        core_id = core["core_id"]

        for cache_name, cache_type in (
            ("l1i", "icache"),
            ("l1d", "dcache"),
        ):
            name = f"cpu{core_id}_{cache_name}"
            cache = core["caches"][cache_name]

            architecture_components.append(
                cache_component(
                    name,
                    cache_type,
                    cache["configuration"],
                )
            )
            action_components.append(
                action_component(
                    name,
                    cache["actions"],
                )
            )

    shared_l2 = mapping["shared_l2"]

    architecture_components.append(
        cache_component(
            "shared_l2",
            "l2cache",
            shared_l2["configuration"],
        )
    )
    action_components.append(
        action_component(
            "shared_l2",
            shared_l2["actions"],
        )
    )

    architecture = {
        "architecture": {
            "version": 0.3,
            "subtree": [
                {
                    "name": "qwen_attention_proxy",
                    "attributes": {
                        "technology": (
                            f"{assumptions['technology_nm']}nm"
                        ),
                        "datawidth": assumptions[
                            "datawidth_bits"
                        ],
                        "clockrate": assumptions[
                            "clockrate_mhz"
                        ],
                        "device_type": assumptions[
                            "device_type"
                        ],
                    },
                    "local": architecture_components,
                }
            ],
        }
    }

    action_counts = {
        "action_counts": {
            "version": 0.3,
            "subtree": [
                {
                    "name": "qwen_attention_proxy",
                    "local": action_components,
                }
            ],
        }
    }

    return architecture, action_counts


def write_yaml(path: Path, value: dict) -> None:
    path.write_text(
        yaml.safe_dump(
            value,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def run_accelergy(
    work_directory: Path,
    image: str,
) -> None:
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{work_directory.resolve()}:/work",
        "-w",
        "/work",
        image,
        "accelergy",
        "architecture.yaml",
        "action_counts.yaml",
        "--outdir",
        "output",
    ]

    completed = subprocess.run(
        command,
        check=False,
        text=True,
    )

    if completed.returncode != 0:
        raise EnergyEstimatorError(
            "Accelergy container failed with exit code "
            f"{completed.returncode}."
        )


def read_energy_uj(path: Path) -> tuple[float, list[dict]]:
    result = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    estimate = result["energy_estimation"]
    total_pj = float(estimate["Total"])

    if total_pj < 0:
        raise EnergyEstimatorError(
            "Accelergy returned negative energy."
        )

    return total_pj / 1_000_000.0, estimate["components"]


def update_metrics(
    source: Path,
    destination: Path,
    energy_uj: float,
) -> None:
    result = json.loads(
        source.read_text(encoding="utf-8")
    )

    metrics = result.get("metrics", result)
    metrics["energy_uj"] = energy_uj
    metrics["energy_scope"] = ENERGY_SCOPE

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    destination.write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mapping_json", type=Path)
    parser.add_argument("metrics_json", type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument(
        "--output-metrics",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--image",
        default="chia-energy-tools:0.2",
    )
    args = parser.parse_args()

    mapping = json.loads(
        args.mapping_json.read_text(encoding="utf-8")
    )
    architecture, action_counts = build_accelergy_inputs(
        mapping
    )

    args.workdir.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_yaml(
        args.workdir / "architecture.yaml",
        architecture,
    )
    write_yaml(
        args.workdir / "action_counts.yaml",
        action_counts,
    )

    run_accelergy(args.workdir, args.image)

    energy_path = (
        args.workdir
        / "output"
        / "energy_estimation.yaml"
    )

    if not energy_path.exists():
        raise EnergyEstimatorError(
            f"Missing Accelergy result: {energy_path}"
        )

    energy_uj, components = read_energy_uj(energy_path)

    update_metrics(
        args.metrics_json,
        args.output_metrics,
        energy_uj,
    )

    summary = {
        "energy_uj": energy_uj,
        "energy_scope": ENERGY_SCOPE,
        "components": components,
    }

    (args.workdir / "energy-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Energy: {energy_uj:.6f} uJ")
    print(f"Wrote metrics: {args.output_metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
