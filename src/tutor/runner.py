"""Qwen Tutor candidate runner used locally and by the Adam CHIA software node."""

import hashlib
import time

from src.common.candidate import Candidate, ROOT
from src.common.errors import ExecutionTimeout
from src.common.security import within
from src.tutor.evaluator import (
    evaluate_required_concepts,
    load_evaluation_set,
)
from src.tutor.llama_cpp_runtime import (
    call_llama_cpp,
    extract_generation,
    preflight,
)
from src.tutor.mapping import map_final_tutor
from src.tutor.metrics import summarize_performance


def load_system_prompt(relative_path="prompts/tutor_system.txt"):
    """Load the deterministic Tutor system prompt."""

    return within(
        ROOT,
        relative_path,
        exists=True,
    ).read_text(
        encoding="utf-8",
    )


def run_software_candidate(config, runtime=None, context=None):
    """Run one software candidate against the complete evaluation set.

    Timeout behavior:

    - candidate_timeout_seconds:
        Maximum wall-clock time for the ENTIRE candidate evaluation.

    - request_timeout_seconds:
        Maximum time allowed for one llama.cpp inference request.

    This separation is necessary for large evaluation sets such as:

        100 questions × 2 repetitions = 200 inference requests

    A single short timeout must not be used as the deadline for the
    complete candidate.
    """

    candidate = Candidate.from_dict(config)
    config = candidate.config

    runtime = runtime or {}

    # ---------------------------------------------------------
    # Timeout configuration
    # ---------------------------------------------------------

    candidate_timeout_seconds = runtime.get(
        "candidate_timeout_seconds",
        1800,
    )

    request_timeout_seconds = runtime.get(
        "request_timeout_seconds",
        120,
    )

    candidate_deadline = (
        time.monotonic()
        + candidate_timeout_seconds
    )

    # ---------------------------------------------------------
    # Convert the canonical software config into llama.cpp
    # runtime/request settings.
    # ---------------------------------------------------------

    mapping = map_final_tutor(
        config["software"],
        runtime,
    )

    # ---------------------------------------------------------
    # Runtime preflight
    # ---------------------------------------------------------

    remaining = (
        candidate_deadline
        - time.monotonic()
    )

    if remaining <= 0:
        raise ExecutionTimeout(
            "Software candidate deadline expired before preflight."
        )

    identity = preflight(
        mapping["endpoint"],
        mapping,
        timeout=min(
            15,
            remaining,
        ),
    )

    # ---------------------------------------------------------
    # Evaluation assets
    # ---------------------------------------------------------

    prompt = load_system_prompt(
        "prompts/tutor_system.txt"
    )

    evaluation_set = load_evaluation_set()

    repetitions = config[
        "measurement"
    ][
        "software_repetitions"
    ]

    question_count = len(
        evaluation_set["items"]
    )

    expected_sample_count = (
        question_count
        * repetitions
    )

    samples = []
    quality_results = []

    completed_samples = 0

    print(
        (
            f"Tutor evaluation: "
            f"{question_count} questions × "
            f"{repetitions} repetitions = "
            f"{expected_sample_count} samples"
        ),
        flush=True,
    )

    # ---------------------------------------------------------
    # Main evaluation loop
    # ---------------------------------------------------------

    for repetition in range(
        repetitions
    ):
        for item in evaluation_set[
            "items"
        ]:
            question = item[
                "question"
            ]

            reference = item[
                "reference"
            ]

            question_id = question[
                "id"
            ]

            remaining = (
                candidate_deadline
                - time.monotonic()
            )

            if remaining <= 0:
                raise ExecutionTimeout(
                    (
                        "Software candidate deadline expired "
                        f"after {completed_samples}/"
                        f"{expected_sample_count} samples."
                    )
                )

            # One individual request gets its own bounded timeout.
            # It should never be allowed to consume the entire
            # remaining candidate deadline.
            per_request_timeout = min(
                request_timeout_seconds,
                remaining,
            )

            sample_number = (
                completed_samples
                + 1
            )

            print(
                (
                    f"[{sample_number}/"
                    f"{expected_sample_count}] "
                    f"{question_id} "
                    f"rep={repetition + 1}/"
                    f"{repetitions} "
                    f"starting..."
                ),
                flush=True,
            )

            start = time.perf_counter()

            try:
                result = call_llama_cpp(
                    endpoint=mapping[
                        "endpoint"
                    ],
                    system_prompt=prompt,
                    user_prompt=question[
                        "question"
                    ],
                    **mapping["request"],
                    timeout=per_request_timeout,
                )

            except Exception as exc:
                elapsed_seconds = (
                    time.perf_counter()
                    - start
                )

                print(
                    (
                        f"[FAILED] "
                        f"{question_id} "
                        f"rep={repetition + 1}/"
                        f"{repetitions} "
                        f"after "
                        f"{elapsed_seconds:.2f}s "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                    flush=True,
                )

                raise

            # -------------------------------------------------
            # llama.cpp response metrics
            # -------------------------------------------------

            answer, metrics = (
                extract_generation(
                    result
                )
            )

            # -------------------------------------------------
            # Deterministic quality evaluation
            # -------------------------------------------------

            quality = (
                evaluate_required_concepts(
                    answer,
                    reference[
                        "required_concepts"
                    ],
                )
            )

            wall_latency_ms = (
                (
                    time.perf_counter()
                    - start
                )
                * 1000
            )

            metrics.update(
                wall_latency_ms=(
                    wall_latency_ms
                ),
                response_sha256=(
                    hashlib.sha256(
                        answer.encode()
                    ).hexdigest()
                ),
                question_id=(
                    question_id
                ),
                repetition=(
                    repetition + 1
                ),
                quality=quality,
                generated_answer=answer,
            )

            samples.append(
                metrics
            )

            quality_results.append(
                quality["score"]
            )

            completed_samples += 1

            print(
                (
                    f"[{completed_samples}/"
                    f"{expected_sample_count}] "
                    f"{question_id} "
                    f"completed "
                    f"quality="
                    f"{quality['score']:.4f} "
                    f"latency="
                    f"{wall_latency_ms:.1f}ms"
                ),
                flush=True,
            )

    # ---------------------------------------------------------
    # Aggregate performance metrics
    # ---------------------------------------------------------

    if not samples:
        raise RuntimeError(
            "Software candidate produced no evaluation samples."
        )

    summary = summarize_performance(
        samples
    )

    summary.update(
        answer_quality=(
            sum(quality_results)
            / len(quality_results)
        ),
        quality_method=(
            "required_concept_coverage"
        ),
        question_count=(
            question_count
        ),
        repetitions_per_question=(
            repetitions
        ),
        sample_count=(
            len(samples)
        ),
    )

    # ---------------------------------------------------------
    # Final result
    # ---------------------------------------------------------

    return {
        "candidate_id": (
            candidate.candidate_id
        ),
        "status": "completed",
        "software": config[
            "software"
        ],
        "metrics": summary,
        "samples": samples,
        "provenance": identity,
        "measurement_scope": (
            "native_llama_cpp_http_roundtrip_"
            "per_mixed_qa_question"
        ),
        "dataset": {
            "dataset_id": (
                evaluation_set[
                    "dataset_id"
                ]
            ),
            "source_url": (
                evaluation_set[
                    "source_url"
                ]
            ),
            "license": (
                evaluation_set[
                    "license"
                ]
            ),
            "reference_visible_to_model": (
                False
            ),
        },
        "prompt_sha256": (
            hashlib.sha256(
                prompt.encode()
            ).hexdigest()
        ),
    }


def run_tutor(
    config,
    runtime=None,
    context=None,
):
    """Compatibility wrapper for the Tutor software node."""

    return run_software_candidate(
        config,
        runtime,
        context,
    )
