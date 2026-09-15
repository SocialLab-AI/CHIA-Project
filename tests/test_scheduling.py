"""Opt-in real local CHIA/Ray scheduling test; does not claim Adam/YSF deployment."""

import os
import socket
import pytest


@pytest.mark.scheduling
def test_chia_schedules_on_explicit_resource():
    if os.getenv("CHIA_RUN_SCHEDULING_TESTS") != "1":
        pytest.skip("Set CHIA_RUN_SCHEDULING_TESTS=1 for actual local Ray processes.")
    import ray
    from chia.base.ChiaFunction import ChiaFunction
    from src.orchestration.dispatch import RESOURCES

    ray.init(
        num_cpus=2,
        resources={"control": 1, "ollama": 1, "gem5": 1},
        include_dashboard=False,
    )
    try:

        def probe():
            return {
                "hostname": socket.gethostname(),
                "resources": ray.get_runtime_context().get_assigned_resources(),
            }

        for name in ("validation", "software", "hardware"):
            node = ChiaFunction(resources=RESOURCES[name], num_cpus=1, max_retries=0)(
                probe
            )
            result = ray.get(node.chia_remote(), timeout=45)
            expected = next(iter(RESOURCES[name]))
            assert expected in result["resources"]
            assert result["hostname"] == socket.gethostname()
    finally:
        ray.shutdown()


@pytest.mark.scheduling
def test_real_chia_full_graph_with_mocked_runtimes(tmp_path):
    if os.getenv("CHIA_RUN_SCHEDULING_TESTS") != "1":
        pytest.skip("Set CHIA_RUN_SCHEDULING_TESTS=1 for actual local Ray processes.")
    import ray
    from chia.base.ChiaFunction import ChiaFunction
    from src.orchestration.dispatch import ChiaDispatcher, RESOURCES
    from src.orchestration.experiment import run_experiment
    from src.common.candidate import baseline_candidate

    ray.init(
        num_cpus=6,
        resources={"control": 1, "ollama": 1, "gem5": 1},
        include_dashboard=False,
    )
    try:
        dispatcher = ChiaDispatcher()

        def sw(mapped, runtime, context):
            from src.common.logging import invoke

            config = mapped["value"]["candidate"]
            return invoke(
                "software",
                context,
                lambda: {
                    "candidate_id": context["candidate_id"],
                    "status": "completed",
                    "software": config["software"],
                    "metrics": {
                        "latency_ms": 10.0,
                        "throughput_qps": 100.0,
                        "sample_count": 1,
                    },
                    "provenance": {"runtime_version": "mocked-on-real-Ray"},
                },
            )

        def hw(mapped, runtime, context):
            from src.common.logging import invoke

            config = mapped["value"]["candidate"]
            return invoke(
                "hardware",
                context,
                lambda: {
                    "candidate_id": context["candidate_id"],
                    "status": "completed",
                    "hardware": config["hardware"],
                    "metrics": {
                        "simulated_seconds": 0.01,
                        "sim_ticks": 10000000000,
                        "instructions": 100,
                        "cycles_per_core": [10, 10],
                        "ipc_per_core": [1.0, 1.0],
                        "l1d_miss_rate_per_core": [0.1, 0.1],
                        "l2_miss_rate": 0.1,
                    },
                    "correctness": {
                        "status": "PASS",
                        "max_absolute_error": 0.01,
                        "mean_squared_error": 0.0001,
                    },
                    "provenance": {
                        "resolved_config_verified": True,
                        "correctness_tolerance": {
                            "max_absolute_error": 0.1,
                            "mean_squared_error": 0.01,
                        },
                    },
                },
            )

        dispatcher.nodes["software"] = ChiaFunction(
            resources=RESOURCES["software"], num_cpus=4, max_retries=0
        )(sw)
        dispatcher.nodes["hardware"] = ChiaFunction(
            resources=RESOURCES["hardware"], num_cpus=1, max_retries=0
        )(hw)
        record = run_experiment(
            baseline_candidate(), dispatcher=dispatcher, results_root=tmp_path
        )
        assert record["status"] == "completed", record["failure"]
        assert {
            "validation",
            "mapping",
            "software",
            "hardware",
            "evaluation",
            "record",
        } == {e["node"] for e in record["events"]}
        assert (tmp_path / "local" / f"{record['run_id']}.json").is_file()
    finally:
        ray.shutdown()
