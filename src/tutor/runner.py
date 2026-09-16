"""Qwen Tutor candidate runner used locally and by the Adam CHIA software node."""

import hashlib
import time
from src.common.candidate import Candidate
from src.common.errors import ExecutionTimeout
from src.common.candidate import ROOT
from src.common.security import within
from src.tutor.evaluator import load_evaluation_set, evaluate_required_concepts
from src.tutor.llama_cpp_runtime import call_llama_cpp, extract_generation, preflight
from src.tutor.mapping import map_final_tutor
from src.tutor.metrics import summarize_performance


def load_system_prompt(relative_path="prompts/tutor_system.txt"):
    return within(ROOT, relative_path, exists=True).read_text(encoding="utf-8")


def run_software_candidate(config, runtime=None, context=None):
    candidate = Candidate.from_dict(config)
    config = candidate.config
    runtime = runtime or {}
    deadline = time.monotonic() + runtime.get("timeout_seconds", 120)
    mapping = map_final_tutor(config["software"], runtime)
    identity = preflight(
        mapping["endpoint"],
        mapping,
        timeout=min(15, deadline - time.monotonic()),
    )
    prompt = load_system_prompt("prompts/tutor_system.txt")
    evaluation_set = load_evaluation_set()
    samples = []
    quality_results = []
    for repetition in range(config["measurement"]["software_repetitions"]):
        for item in evaluation_set["items"]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ExecutionTimeout("Software node deadline expired.")
            start = time.perf_counter()
            result = call_llama_cpp(
                endpoint=mapping["endpoint"],
                system_prompt=prompt,
                user_prompt=item["question"]["question"],
                **mapping["request"],
                timeout=remaining,
            )
            answer, metrics = extract_generation(result)
            quality = evaluate_required_concepts(
                answer, item["reference"]["required_concepts"]
            )
            metrics.update(
                wall_latency_ms=(time.perf_counter() - start) * 1000,
                response_sha256=hashlib.sha256(answer.encode()).hexdigest(),
                question_id=item["question"]["id"],
                repetition=repetition + 1,
                quality=quality,
                generated_answer=answer,
            )
            samples.append(metrics)
            quality_results.append(quality["score"])
    summary = summarize_performance(samples)
    summary.update(
        answer_quality=sum(quality_results) / len(quality_results),
        quality_method="required_concept_coverage",
        question_count=len(evaluation_set["items"]),
        repetitions_per_question=config["measurement"]["software_repetitions"],
    )
    return {
        "candidate_id": candidate.candidate_id,
        "status": "completed",
        "software": config["software"],
        "metrics": summary,
        "samples": samples,
        "provenance": identity,
        "measurement_scope": "native_llama_cpp_http_roundtrip_per_openstax_question",
        "dataset": {
            "dataset_id": evaluation_set["dataset_id"],
            "source_url": evaluation_set["source_url"],
            "license": evaluation_set["license"],
            "reference_visible_to_model": False,
        },
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
    }


def run_tutor(config, runtime=None, context=None):
    return run_software_candidate(config, runtime, context)
