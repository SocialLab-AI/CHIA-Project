import json
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.hardware.energy_estimator import (
    ENERGY_SCOPE,
    EnergyEstimatorError,
    build_accelergy_inputs,
    read_energy_uj,
    run_accelergy,
    run_energy_candidate,
    update_metrics,
    verify_components,
)
from src.hardware.energy_mapping import build_energy_mapping
from src.common.candidate import Candidate, baseline_candidate
from src.common.errors import ExecutionTimeout, PreflightError, RuntimeExecutionError


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


def inspected_energy_image(repo_digests=None):
    return json.dumps(
        [
            {
                "Id": "sha256:" + "a" * 64,
                "RepoDigests": repo_digests or [],
                "Config": {
                    "Labels": {
                        "org.chia.accelergy.version": "0.3",
                        "org.chia.accelergy.commit": "c" * 40,
                        "org.chia.accelergy-mcpat-plugin.commit": "d" * 40,
                        "org.chia.mcpat.version": "1.3",
                        "org.chia.mcpat.commit": "e" * 40,
                    }
                },
            }
        ]
    )


def write_stats(path):
    lines = []
    for prefix in (
        "system.cpu0.icache",
        "system.cpu0.dcache",
        "system.cpu1.icache",
        "system.cpu1.dcache",
        "system.l2cache",
    ):
        lines.extend(
            [
                f"{prefix}.overallHits::total 100",
                f"{prefix}.overallMisses::total 10",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def hardware_result(config, directory):
    stats = directory / "stats.txt"
    write_stats(stats)
    return {
        "candidate_id": Candidate.from_dict(config).candidate_id,
        "status": "completed",
        "hardware": config["hardware"],
        "metrics": {"simulated_seconds": 1.0},
        "provenance": {
            "stats_sha256": hashlib.sha256(stats.read_bytes()).hexdigest(),
        },
        "artifacts": {"directory": str(directory), "stats": "stats.txt"},
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


def test_maps_exact_gem5_statistics_to_five_caches(tmp_path):
    config = baseline_candidate()
    hardware = hardware_result(config, tmp_path)
    mapping = build_energy_mapping(config, hardware, tmp_path / "stats.txt")

    assert len(mapping["cores"]) == 2
    assert mapping["cores"][0]["caches"]["l1i"]["actions"] == {
        "read_hit": 100,
        "read_miss": 10,
        "write_hit": 0,
        "write_miss": 0,
    }
    architecture, _ = build_accelergy_inputs(mapping)
    assert len(architecture["architecture"]["subtree"][0]["local"]) == 5


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
    (tmp_path / "output").mkdir()
    (tmp_path / "output/energy_estimation.yaml").write_text(
        "energy_estimation: {}\n",
        encoding="utf-8",
    )
    inspected = inspected_energy_image(
        ["chia-energy-tools@sha256:" + "b" * 64]
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
        run_accelergy(tmp_path, "chia-energy-tools:0.3")

    container_command = process.call_args_list[1].args[0]
    assert container_command[-5:] == [
        "chia-accelergy",
        "-o",
        "output",
        "architecture.yaml",
        "action_counts.yaml",
    ]
    assert "--outdir" not in container_command


def test_accelergy_rejects_success_without_estimate(tmp_path):
    inspected = inspected_energy_image()
    with patch(
        "src.hardware.energy_estimator.shutil.which",
        return_value="/usr/bin/docker",
    ), patch(
        "src.hardware.energy_estimator.run_process",
        side_effect=[
            {"stdout": inspected},
            {
                "stdout_summary": "no output generated",
                "stderr_summary": "",
            },
            {"stdout": ""},
        ],
    ):
        with pytest.raises(EnergyEstimatorError) as caught:
            run_accelergy(tmp_path, "chia-energy-tools:0.3")

    assert "without creating" in str(caught.value)
    assert caught.value.stdout_summary == "no output generated"
    assert caught.value.runtime_stage == "energy_verification"


def test_accelergy_timeout_removes_container(tmp_path):
    inspected = inspected_energy_image()
    with patch(
        "src.hardware.energy_estimator.shutil.which",
        return_value="/usr/bin/docker",
    ), patch(
        "src.hardware.energy_estimator.run_process",
        side_effect=[
            {"stdout": inspected},
            ExecutionTimeout("Subprocess exceeded its deadline."),
            {"stdout": ""},
        ],
    ) as process:
        with pytest.raises(ExecutionTimeout) as caught:
            run_accelergy(tmp_path, "chia-energy-tools:0.3", timeout_seconds=5)

    assert caught.value.runtime_stage == "energy_execution"
    assert process.call_args_list[-1].args[0][1:3] == ["rm", "-f"]


def test_missing_energy_image_is_preflight_failure(tmp_path):
    with patch(
        "src.hardware.energy_estimator.shutil.which",
        return_value="/usr/bin/docker",
    ), patch(
        "src.hardware.energy_estimator.run_process",
        side_effect=RuntimeExecutionError("image missing"),
    ):
        with pytest.raises(PreflightError) as caught:
            run_accelergy(tmp_path, "chia-energy-tools:0.3")

    assert caught.value.runtime_stage == "energy_preflight"


def test_energy_image_without_pinned_labels_is_rejected(tmp_path):
    inspected = json.dumps(
        [{"Id": "sha256:" + "a" * 64, "RepoDigests": [], "Config": {}}]
    )
    with patch(
        "src.hardware.energy_estimator.shutil.which",
        return_value="/usr/bin/docker",
    ), patch(
        "src.hardware.energy_estimator.run_process",
        return_value={"stdout": inspected},
    ):
        with pytest.raises(PreflightError, match="provenance labels") as caught:
            run_accelergy(tmp_path, "chia-energy-tools:0.3")

    assert caught.value.runtime_stage == "energy_preflight"


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_component_energy_must_be_finite_and_nonnegative(value):
    components = [
        {"name": name, "energy": 1.0}
        for name in (
            "cpu0_l1i",
            "cpu0_l1d",
            "cpu1_l1i",
            "cpu1_l1d",
            "shared_l2",
        )
    ]
    components[0]["energy"] = value
    with pytest.raises(EnergyEstimatorError):
        verify_components(components)


def test_energy_result_preserves_scope_hashes_and_versions(tmp_path):
    config = baseline_candidate()
    hardware_dir = tmp_path / "hardware" / "run-a"
    hardware_dir.mkdir(parents=True)
    hardware = hardware_result(config, hardware_dir)
    energy_root = tmp_path / "energy"

    def fake_accelergy(workdir, image, timeout_seconds, image_preflight=None):
        output = workdir / "output"
        output.mkdir()
        components = [
            {"name": name, "energy": 1_000_000.0}
            for name in (
                "qwen_attention_proxy.cpu0_l1i",
                "qwen_attention_proxy.cpu0_l1d",
                "qwen_attention_proxy.cpu1_l1i",
                "qwen_attention_proxy.cpu1_l1d",
                "qwen_attention_proxy.shared_l2",
            )
        ]
        (output / "energy_estimation.yaml").write_text(
            yaml.safe_dump(
                {
                    "energy_estimation": {
                        "Total": 5_000_000.0,
                        "components": components,
                    }
                }
            ),
            encoding="utf-8",
        )
        return {
            "container_image_digest": "sha256:" + "a" * 64,
            "container_image_id": "sha256:" + "b" * 64,
            "accelergy_version": "0.3",
            "accelergy_commit": "c" * 40,
            "mcpat_version": "1.3",
            "mcpat_commit": "d" * 40,
            "plugin_commit": "e" * 40,
            "execution_duration_seconds": 1.5,
        }

    with patch(
        "src.hardware.energy_estimator.run_accelergy",
        side_effect=fake_accelergy,
    ):
        result = run_energy_candidate(
            config,
            hardware,
            {
                "image": "chia-energy-tools:0.3",
                "timeout_seconds": 10,
                "artifacts_root": str(energy_root),
                "hardware_artifacts_root": str(tmp_path / "hardware"),
            },
            {"run_id": "run-a"},
        )

    assert result["metrics"]["estimated_cache_dynamic_energy_uj"] == 5.0
    assert result["scope"] == ENERGY_SCOPE
    assert result["provenance"]["accelergy_version"] == "0.3"
    assert result["provenance"]["mcpat_version"] == "1.3"
    for name in (
        "mapping_sha256",
        "architecture_sha256",
        "action_counts_sha256",
        "energy_result_sha256",
    ):
        assert len(result["provenance"][name]) == 64


def test_energy_image_stages_writable_ephemeral_plugin_copy():
    wrapper = (
        Path(__file__).resolve().parents[1]
        / "infra/energy/run-accelergy.sh"
    ).read_text(encoding="utf-8")

    assert "mktemp -d /tmp/chia-accelergy." in wrapper
    assert "cp -R /opt/energy-venv/share/accelergy/estimation_plug_ins/." in wrapper
    assert "export HOME=" in wrapper
    assert 'exec accelergy "$@"' in wrapper

