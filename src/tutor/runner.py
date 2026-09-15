"""Software-owned candidate runner; shared by local execution and the Adam CHIA node."""

import hashlib
import time
from src.common.candidate import Candidate
from src.common.errors import ExecutionTimeout
from src.tutor.ollama_runtime import (
    call_ollama,
    extract_metrics,
    load_system_prompt,
    preflight,
)
from src.tutor.metrics import summarize_performance

SMOKE_QUESTION = "Explain cache memory in one short paragraph."


def inference_mapping(software):
    """batch_size is request concurrency=1, never llama.cpp token n_batch."""
    return {
        "model": software["model"],
        "temperature": software["temperature"],
        "max_output_tokens": software["max_output_tokens"],
        "cpu_threads": software["cpu_threads"],
    }


def run_software_candidate(config, runtime=None, context=None):
    candidate = Candidate.from_dict(config)
    config = candidate.config
    runtime = runtime or {}
    endpoint = runtime.get("endpoint", "http://127.0.0.1:11434")
    deadline = time.monotonic() + runtime.get("timeout_seconds", 120)
    identity = preflight(
        endpoint,
        config["software"]["model"],
        expected_digest=runtime.get("model_digest"),
        timeout=min(10, deadline - time.monotonic()),
    )
    prompt = load_system_prompt("prompts/tutor_system.txt")
    samples = []
    for _ in range(config["measurement"]["software_repetitions"]):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ExecutionTimeout("Software node deadline expired.")
        start = time.perf_counter()
        result = call_ollama(
            endpoint=endpoint,
            system_prompt=prompt,
            user_prompt=SMOKE_QUESTION,
            **inference_mapping(config["software"]),
            timeout=remaining,
        )
        metrics = extract_metrics(result)
        metrics["wall_latency_ms"] = (time.perf_counter() - start) * 1000
        metrics["response_sha256"] = hashlib.sha256(
            result["response"].encode()
        ).hexdigest()
        samples.append(metrics)
    return {
        "candidate_id": candidate.candidate_id,
        "status": "completed",
        "software": config["software"],
        "metrics": summarize_performance(samples),
        "samples": samples,
        "provenance": identity,
        "measurement_scope": "native_generation_http_roundtrip",
        "prompt_sha256": hashlib.sha256((prompt + SMOKE_QUESTION).encode()).hexdigest(),
    }


def run_tutor(config, runtime=None, context=None):
    return run_software_candidate(config, runtime, context)
