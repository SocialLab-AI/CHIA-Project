"""Hardware-owned isolated Docker runner used by the gem5 worker and diagnostics."""

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
from src.common.candidate import Candidate, ROOT
from src.common.errors import (
    ConfigError,
    ExecutionTimeout,
    MetricsError,
    PreflightError,
    RuntimeExecutionError,
)
from src.common.process import run_process
from src.common.security import safe_id, within, finite_number
from src.hardware.attention_kernel import build_attention_kernel_args
from src.hardware.gem5 import build_gem5_command


RESOLVED_CPU_MODELS = {
    "RiscvO3CPU": {
        "type": "BaseO3CPU",
        "cxx_class": "gem5::o3::CPU",
    },
    "RiscvTimingSimpleCPU": {
        "type": "BaseTimingSimpleCPU",
        "cxx_class": "gem5::TimingSimpleCPU",
    },
}


def parse_correctness(stdout, tolerance, *, enforce_tolerance=True):
    """Parse finite numerical evidence and optionally enforce the acceptance gate."""

    if not isinstance(enforce_tolerance, bool):
        raise ConfigError("enforce_tolerance must be boolean.")
    values = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key in {
                "status",
                "max_absolute_error",
                "mean_squared_error",
                "context",
                "query_heads",
                "kv_heads",
                "head_dimension",
                "threads",
                "repetitions",
            }:
                values[key] = value.strip()
    if values.get("status") != "PASS":
        raise MetricsError("Attention workload did not report PASS.")
    for name in ("max_absolute_error", "mean_squared_error"):
        try:
            value = float(values[name])
            limit = finite_number(tolerance[name], name)
        except (KeyError, ValueError, TypeError) as exc:
            raise MetricsError(
                "Numerical correctness evidence or approved tolerance is missing."
            ) from exc
        if not math.isfinite(value) or value < 0:
            raise MetricsError("Attention workload reported invalid numerical error.")
        if enforce_tolerance and value > limit:
            raise MetricsError(
                "Attention error exceeds the configured numerical tolerance."
            )
        values[name] = value
    return values


def parse_gem5_version(output):
    """Extract a bounded version token from the banner of the executed simulator."""
    match = re.search(r"(?m)^gem5 version ([^\r\n]+)\s*$", output)
    version = match.group(1).strip() if match else ""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", version):
        raise MetricsError("gem5 execution did not report a valid version banner.")
    return version


def verify_resolved(config_json, config):
    """Inspect actual instantiated objects, not command text alone."""
    system = config_json["system"]
    cpus = system["cpu"]
    hw = config["hardware"]
    if len(cpus) != hw["cores"]:
        raise MetricsError("Resolved CPU count differs from candidate.")
    expected_cpu = RESOLVED_CPU_MODELS[hw["cpu_model"]]
    for cpu in cpus:
        if any(cpu.get(field) != value for field, value in expected_cpu.items()):
            raise MetricsError("Resolved CPU model differs from candidate.")
        if hw["cpu_model"] == "RiscvO3CPU" and cpu["issueWidth"] != hw["issue_width"]:
            raise MetricsError("Resolved issue width differs from candidate.")
        for cache, prefix in ((cpu["icache"], "l1i"), (cpu["dcache"], "l1d")):
            if (
                int(cache["size"]) != hw[prefix + "_cache_kib"] * 1024
                or cache["assoc"] != hw[prefix + "_associativity"]
            ):
                raise MetricsError("Resolved L1 cache differs from candidate.")
            for latency in ("tag_latency", "data_latency", "response_latency"):
                if cache[latency] != hw[prefix + "_latency_cycles"]:
                    raise MetricsError(
                        "Resolved L1 latency profile differs from candidate."
                    )
    l2 = system["l2cache"]
    if (
        int(l2["size"]) != hw["l2_cache_kib"] * 1024
        or l2["assoc"] != hw["l2_associativity"]
    ):
        raise MetricsError("Resolved L2 cache differs from candidate.")
    for latency in ("tag_latency", "data_latency", "response_latency"):
        if l2[latency] != hw["l2_latency_cycles"]:
            raise MetricsError("Resolved L2 latency profile differs from candidate.")
    # gem5 serializes clocks as ticks/period, with default global tick rate 1 THz.
    expected = round(1000 / hw["frequency_ghz"])
    if (
        abs(system["cpu_clk_domain"]["clock"][0] - expected) > 1
        or system["clk_domain"]["clock"][0] != 1000
    ):
        raise MetricsError("Resolved CPU/fixed system clocks differ from mapping.")
    return True


def run_gem5_candidate(config, runtime=None, context=None):
    candidate = Candidate.from_dict(config)
    config = candidate.config
    runtime = runtime or {}
    context = context or {}
    tolerance = runtime.get("correctness_tolerance")
    if not isinstance(tolerance, dict) or set(tolerance) != {
        "max_absolute_error",
        "mean_squared_error",
    }:
        raise PreflightError(
            "An explicit reviewed Q4 correctness_tolerance is required."
        )
    for key, value in tolerance.items():
        finite_number(value, key)
    enforce_tolerance = runtime.get("enforce_correctness_tolerance", True)
    if not isinstance(enforce_tolerance, bool):
        raise ConfigError("enforce_correctness_tolerance must be boolean.")
    docker = shutil.which("docker")
    if not docker:
        raise PreflightError("Docker is not installed on the hardware worker.")
    image = runtime.get("image", "ghcr.io/gem5/devcontainer:v25-1")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:-]+", image):
        raise ConfigError("Invalid operator-provided Docker image reference.")
    deadline = time.monotonic() + runtime.get("timeout_seconds", 600)

    def run(args, stage):
        try:
            return run_process(args, cwd=ROOT, timeout=deadline - time.monotonic())
        except (RuntimeExecutionError, ExecutionTimeout) as error:
            error.runtime_stage = stage
            raise

    inspected = json.loads(
        run([docker, "image", "inspect", image], "image_inspect")["stdout"]
    )
    identity = inspected[0]
    pinned = (identity.get("RepoDigests") or [identity["Id"]])[0]
    image_id = identity["Id"]
    run_id = safe_id(context.get("run_id", "local-" + candidate.candidate_id[:16]))
    base = Path(runtime.get("artifacts_root", ROOT / "results/hardware")).resolve()
    base.mkdir(parents=True, exist_ok=True)
    directory = within(base, run_id)
    directory.mkdir(exist_ok=False)
    source = ROOT / "gem5/attention_kv.c"
    config_source = ROOT / "gem5/attention-riscv.py"
    shutil.copyfile(source, directory / "attention_kv.c")
    shutil.copyfile(config_source, directory / "attention-riscv.py")
    (directory / "candidate.json").write_text(candidate.payload, encoding="utf-8")
    summaries = []

    def container(stage, command):
        name = "chia-" + run_id + "-" + str(len(summaries))
        argv = [
            docker,
            "run",
            "--name",
            name,
            "--rm",
            "--pull=never",
            "--network=none",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=128",
            "-v",
            f"{directory}:/work",
            "-w",
            "/work",
        ]
        if os.name != "nt":
            argv += ["--user", f"{os.getuid()}:{os.getgid()}"]
        argv += [image_id, *command]
        try:
            result = run(argv, stage)
            summaries.append(
                {"stdout": result["stdout_summary"], "stderr": result["stderr_summary"]}
            )
            return result["stdout"]
        finally:
            # docker client termination does not imply container termination.
            try:
                run_process([docker, "rm", "-f", name], cwd=ROOT, timeout=10)
            except Exception:
                pass  # --rm commonly already removed it; cleanup never overwrites the primary failure.

    try:
        compiler_version = container(
            "compiler_version",
            ["riscv64-linux-gnu-gcc", "-dumpfullversion"]
        ).strip()
        container(
            "compile_kernel",
            [
                "riscv64-linux-gnu-gcc",
                "-static",
                "-O2",
                "-std=c11",
                "-pthread",
                *build_attention_kernel_args(config),
                "-o",
                "attention_kv_q4",
                "attention_kv.c",
                "-lm",
            ]
        )
        output = container(
            "gem5_simulation",
            [
                "gem5",
                "--outdir=/work/m5out",
                "/work/attention-riscv.py",
                "--binary",
                "/work/attention_kv_q4",
                *build_gem5_command(config),
            ]
        )
        if "exiting with last active thread context" not in output:
            raise MetricsError(
                "gem5 did not report the expected workload completion exit."
            )
        gem5_version = parse_gem5_version(output)
        correctness = parse_correctness(
            output,
            tolerance,
            enforce_tolerance=enforce_tolerance,
        )
        expected = {
            **config["workload"],
            "context": config["workload"]["context_tokens"],
            "threads": 2,
            "repetitions": config["measurement"]["kernel_iterations"],
        }
        for key in (
            "context",
            "query_heads",
            "kv_heads",
            "head_dimension",
            "threads",
            "repetitions",
        ):
            if int(correctness.get(key, -1)) != expected[key]:
                raise MetricsError("Workload output shape differs from the candidate.")
        raw = json.loads((directory / "m5out/config.json").read_text())
        verify_resolved(raw, config)
        spec = importlib.util.spec_from_file_location(
            "chia_project_gem5_metrics", ROOT / "gem5/extract_metrics.py"
        )
        parser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        metrics = parser.build_metrics(parser.load_stats(directory / "m5out/stats.txt"))
        return {
            "candidate_id": candidate.candidate_id,
            "status": "completed",
            "hardware": config["hardware"],
            "workload": config["workload"],
            "metrics": metrics,
            "correctness": correctness,
            "measurement_scope": "whole_program_including_reference_and_setup",
            "provenance": {
                "gem5_version": gem5_version,
                "compiler_version": compiler_version,
                "container_image_digest": pinned,
                "container_image_id": image_id,
                "kernel_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "binary_sha256": hashlib.sha256(
                    (directory / "attention_kv_q4").read_bytes()
                ).hexdigest(),
                "correctness_tolerance": tolerance,
                "resolved_config_verified": True,
            },
            "artifacts": {
                "directory": str(directory),
                "stats": "m5out/stats.txt",
                "resolved_config": "m5out/config.json",
            },
            "output_summaries": summaries,
        }
    finally:
        # Keep evidence and executable; remove only known temporary compilation source copies.
        for filename in ("attention_kv.c", "attention-riscv.py"):
            (directory / filename).unlink(missing_ok=True)


def run_hardware(config, runtime=None, context=None):
    return run_gem5_candidate(config, runtime, context)
