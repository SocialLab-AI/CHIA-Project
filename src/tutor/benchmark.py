"""Run controlled llama-bench sweeps; Tutor owns native Qwen measurements."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import time

from src.common.errors import ConfigError, MetricsError, PreflightError, RuntimeExecutionError
from src.common.process import run_process
from src.tutor.llama_cpp_runtime import file_sha256


PERF_EVENTS = (
    "cycles",
    "instructions",
    "cache-references",
    "cache-misses",
    "branches",
    "branch-misses",
)


def parse_llama_bench_json(text, context_tokens, repetitions):
    """Validate one prompt-processing result emitted by llama-bench."""

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise MetricsError("llama-bench did not emit valid JSON.") from error
    if not isinstance(payload, list) or len(payload) != 1:
        raise MetricsError("Expected exactly one llama-bench result per context.")
    item = payload[0]
    required = {
        "build_commit",
        "cpu_info",
        "backends",
        "model_filename",
        "model_n_params",
        "n_threads",
        "n_prompt",
        "n_gen",
        "avg_ns",
        "stddev_ns",
        "avg_ts",
        "stddev_ts",
        "samples_ns",
        "samples_ts",
    }
    if not isinstance(item, dict) or not required.issubset(item):
        raise MetricsError("llama-bench result is missing required evidence.")
    if item["n_prompt"] != context_tokens or item["n_gen"] != 0:
        raise MetricsError("llama-bench executed a different prompt/generation shape.")
    if item["n_threads"] < 1:
        raise MetricsError("llama-bench did not report a valid thread count.")
    if len(item["samples_ns"]) != repetitions or len(item["samples_ts"]) != repetitions:
        raise MetricsError("llama-bench sample count differs from the requested repetitions.")
    for name in ("avg_ns", "avg_ts"):
        value = item[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise MetricsError(f"llama-bench metric {name} is invalid.")
    return {
        "context_tokens": context_tokens,
        "average_latency_ms": item["avg_ns"] / 1_000_000.0,
        "latency_stddev_ms": item["stddev_ns"] / 1_000_000.0,
        "prompt_tokens_per_second": item["avg_ts"],
        "prompt_tokens_per_second_stddev": item["stddev_ts"],
        "latency_samples_ms": [value / 1_000_000.0 for value in item["samples_ns"]],
        "throughput_samples": item["samples_ts"],
        "benchmark_provenance": {
            key: item.get(key)
            for key in (
                "build_commit",
                "build_number",
                "cpu_info",
                "gpu_info",
                "backends",
                "model_filename",
                "model_type",
                "model_size",
                "model_n_params",
                "n_batch",
                "n_ubatch",
                "n_threads",
                "n_gpu_layers",
                "flash_attn",
                "type_k",
                "type_v",
            )
        },
    }


def parse_gnu_time(text):
    """Extract process-lifetime memory and CPU evidence from GNU time -v."""

    values = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        values[key] = value
    try:
        peak_kib = int(values["Maximum resident set size (kbytes)"])
        cpu_percent = float(values["Percent of CPU this job got"].rstrip("%"))
    except (KeyError, ValueError) as error:
        raise MetricsError("GNU time did not report peak RSS and CPU utilization.") from error
    if peak_kib <= 0 or cpu_percent < 0:
        raise MetricsError("GNU time reported invalid resource measurements.")
    return {
        "peak_rss_bytes": peak_kib * 1024,
        "process_cpu_utilization_percent": cpu_percent,
        "resource_scope": "whole_llama_bench_process_including_model_load",
    }


def parse_perf_stat(text):
    """Parse the selected perf-stat CSV counters without accepting placeholders."""

    counters = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        raw, event = parts[0], parts[2]
        if event not in PERF_EVENTS or raw.startswith("<"):
            continue
        try:
            counters[event.replace("-", "_")] = float(raw)
        except ValueError:
            continue
    return counters


def _resolved_executable(value, label):
    path = Path(value).expanduser().resolve() if value else None
    if path and path.is_file():
        return str(path)
    found = shutil.which(str(value)) if value else None
    if found:
        return found
    raise PreflightError(f"{label} executable is unavailable.")


def _perf_preflight(perf, cwd):
    true = shutil.which("true")
    if not perf or not true:
        return False, "perf or true executable is unavailable"
    try:
        run_process(
            [perf, "stat", "--no-big-num", "-x", ",", "-e", "cycles", "--", true],
            cwd=cwd,
            timeout=15,
        )
        return True, None
    except RuntimeExecutionError as error:
        return False, getattr(error, "stderr_summary", str(error))


def run_native_context_sweep(
    *,
    model_path,
    expected_sha256,
    llama_bench,
    contexts,
    threads=4,
    repetitions=5,
    timeout_seconds=900,
    collect_perf=True,
):
    """Measure exact prompt lengths with CPU-only llama-bench repetitions."""

    model = Path(model_path).expanduser().resolve()
    if not model.is_file():
        raise PreflightError("The native benchmark GGUF does not exist.")
    actual_sha256 = file_sha256(model)
    if actual_sha256 != expected_sha256:
        raise PreflightError("Native benchmark GGUF SHA-256 differs from the contract.")
    bench = _resolved_executable(llama_bench, "llama-bench")
    gnu_time = _resolved_executable("/usr/bin/time", "GNU time")
    if type(threads) is not int or threads < 1:
        raise ConfigError("Native benchmark threads must be a positive integer.")
    if type(repetitions) is not int or repetitions < 2:
        raise ConfigError("Native benchmark requires at least two repetitions.")
    cwd = model.parent
    perf = shutil.which("perf") if collect_perf else None
    perf_available, perf_reason = _perf_preflight(perf, cwd)
    results = []
    deadline = time.monotonic() + timeout_seconds

    with tempfile.TemporaryDirectory(prefix="chia-proxy-native-") as temporary:
        temporary = Path(temporary)
        for context in contexts:
            if type(context) is not int or context < 1:
                raise ConfigError("Context lengths must be positive integers.")
            time_path = temporary / f"time-{context}.txt"
            perf_path = temporary / f"perf-{context}.csv"
            benchmark = [
                bench,
                "-m",
                str(model),
                "-p",
                str(context),
                "-n",
                "0",
                "-t",
                str(threads),
                "-r",
                str(repetitions),
                "-ngl",
                "0",
                "-o",
                "json",
            ]
            measured = benchmark
            if perf_available:
                measured = [
                    perf,
                    "stat",
                    "--no-big-num",
                    "-x",
                    ",",
                    "-o",
                    str(perf_path),
                    "-e",
                    ",".join(PERF_EVENTS),
                    "--",
                    *benchmark,
                ]
            command = [gnu_time, "-v", "-o", str(time_path), *measured]
            remaining = deadline - time.monotonic()
            result = run_process(command, cwd=cwd, timeout=remaining)
            parsed = parse_llama_bench_json(result["stdout"], context, repetitions)
            parsed.update(parse_gnu_time(time_path.read_text(encoding="utf-8")))
            parsed["hardware_counters"] = (
                parse_perf_stat(perf_path.read_text(encoding="utf-8"))
                if perf_available and perf_path.is_file()
                else None
            )
            results.append(parsed)

    return {
        "schema_version": "0.1.0",
        "kind": "qwen_native_context_sweep",
        "model_sha256": actual_sha256,
        "contexts": results,
        "perf_available": perf_available,
        "perf_unavailable_reason": perf_reason,
        "measurement_scope": (
            "llama-bench CPU prompt processing; benchmark latency excludes model load, "
            "tokenization and sampling; RSS/CPU/perf cover process lifetime"
        ),
    }
