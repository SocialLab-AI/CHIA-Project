import json
from unittest.mock import patch

import yaml

from src.hardware.energy_estimator import (
    ENERGY_SCOPE,
    build_accelergy_inputs,
    read_energy_uj,
    run_accelergy,
    update_metrics,
)


def sample_cache():
    return {
        "configuration": {
            "size_bytes": 65536,
            "associativity": 4,
            "block_size_bytes": 64,
            "data_latency_cycles": 2,
            "tag_latency_cycles": 2,
            "response_latency_cycles": 2,
            "mshr_entries": 8,
            "write_buffer_entries": 8,
        },
        "actions": {
            "read_hit": 100,
            "read_miss": 10,
            "write_hit": 20,
            "write_miss": 2,
        },
    }


def sample_mapping():
    return {
        "mcpat_assumptions": {
            "technology_nm": 45,
            "device_type": "lop",
            "clockrate_mhz": 1000,
            "datawidth_bits": 64,
        },
        "cores": [
            {
                "core_id": 0,
                "caches": {
                    "l1i": sample_cache(),
                    "l1d": sample_cache(),
                },
            },
            {
                "core_id": 1,
                "caches": {
                    "l1i": sample_cache(),
                    "l1d": sample_cache(),
                },
            },
        ],
        "shared_l2": sample_cache(),
    }


def test_builds_all_five_cache_components():
    architecture, actions = build_accelergy_inputs(
        sample_mapping()
    )

    architecture_local = architecture[
        "architecture"
    ]["subtree"][0]["local"]

    action_local = actions[
        "action_counts"
    ]["subtree"][0]["local"]

    expected_names = {
        "cpu0_l1i",
        "cpu0_l1d",
        "cpu1_l1i",
        "cpu1_l1d",
        "shared_l2",
    }

    assert {
        component["name"]
        for component in architecture_local
    } == expected_names

    assert {
        component["name"]
        for component in action_local
    } == expected_names


def test_architecture_uses_mapping_assumptions():
    architecture, _ = build_accelergy_inputs(
        sample_mapping()
    )

    root = architecture["architecture"]["subtree"][0]

    assert root["attributes"] == {
        "technology": "45nm",
        "datawidth": 64,
        "clockrate": 1000,
        "device_type": "lop",
    }

    l1d = next(
        component
        for component in root["local"]
        if component["name"] == "cpu0_l1d"
    )

    assert l1d["class"] == "cache"
    assert l1d["attributes"]["cache_type"] == "dcache"
    assert l1d["attributes"]["size"] == 65536
    assert l1d["attributes"]["associativity"] == 4


def test_reads_picjoules_as_microjoules(tmp_path):
    result_path = tmp_path / "energy_estimation.yaml"

    result_path.write_text(
        yaml.safe_dump(
            {
                "energy_estimation": {
                    "version": 0.3,
                    "components": [
                        {
                            "name": "proxy.cpu0_l1d",
                            "energy": 162_304_901.617,
                        }
                    ],
                    "Total": 162_304_901.617,
                }
            }
        ),
        encoding="utf-8",
    )

    energy_uj, components = read_energy_uj(
        result_path
    )

    assert energy_uj == 162.304901617
    assert len(components) == 1


def test_updates_metrics_without_losing_existing_data(
    tmp_path,
):
    source = tmp_path / "metrics.json"
    destination = tmp_path / "with-energy.json"

    source.write_text(
        json.dumps(
            {
                "metrics": {
                    "sim_ticks": 100,
                    "energy_uj": None,
                    "energy_scope": None,
                },
                "status": {
                    "state": "completed",
                },
            }
        ),
        encoding="utf-8",
    )

    update_metrics(
        source,
        destination,
        162.304901617,
    )

    result = json.loads(
        destination.read_text(encoding="utf-8")
    )

    assert result["metrics"]["sim_ticks"] == 100
    assert result["metrics"]["energy_uj"] == (
        162.304901617
    )
    assert result["metrics"]["energy_scope"] == (
        ENERGY_SCOPE
    )
    assert result["status"]["state"] == "completed"


def test_accelergy_uses_the_pinned_v03_output_flag(tmp_path):
    inspected = json.dumps(
        [
            {
                "Id": "sha256:" + "a" * 64,
                "RepoDigests": ["chia-energy-tools@sha256:" + "b" * 64],
            }
        ]
    )
    with patch(
        "src.hardware.energy_estimator.shutil.which",
        return_value="/usr/bin/docker",
    ), patch(
        "src.hardware.energy_estimator.run_process",
        side_effect=[
            {"stdout": inspected},
            {"stdout": ""},
            {"stdout": ""},
        ],
    ) as process:
        run_accelergy(tmp_path, "chia-energy-tools:0.2")

    container_command = process.call_args_list[1].args[0]
    assert container_command[-5:] == [
        "accelergy",
        "-o",
        "output",
        "architecture.yaml",
        "action_counts.yaml",
    ]
    assert "--outdir" not in container_command

