"""Qwen Tutor candidate runner used locally and by the Adam CHIA software node."""

import hashlib
import time

from src.common.candidate import Candidate, ROOT
from src.common.errors import ConfigError, ExecutionTimeout
from src.common.security import finite_number, within
from src.tutor.evaluator import (
    evaluate_required_concepts,
    load_evaluation_set,
)
from src.tutor.llama_cpp_runtime import (
    call_llama_cpp,
    extract_generation,
    inspect_slots,
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


def software_failure(error):
    """Serialize safe Tutor failure provenance for campaign records."""

    result = {
        "type": type(error).__name__,
        "message": str(error),
    }

    sample = getattr(
        error,
        "sample_failure",
        None,
    )

    if isinstance(sample, dict):
        result["sample"] = sample

    return result


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

    request_retries = runtime.get(
        "request_retries",
        1,
    )

    request_retry_delay_seconds = runtime.get(
        "request_retry_delay_seconds",
        2.0,
    )

    finite_number(
        candidate_timeout_seconds,
        "software candidate timeout",
        positive=True,
    )
    finite_number(
        request_timeout_seconds,
        "software request timeout",
        positive=True,
    )
    finite_number(
        request_retry_delay_seconds,
        "software request retry delay",
    )

    if (
        type(request_retries) is not int
        or not 0 <= request_retries <= 2
    ):
        raise ConfigError(
            "Software request retries must be an integer between zero and two."
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
                error = ExecutionTimeout(
                    (
                        "Software candidate deadline expired "
                        f"after {completed_samples}/"
                        f"{expected_sample_count} samples."
                    )
                )
                error.timeout_scope = "candidate"
                error.sample_failure = {
                    "question_id": question_id,
                    "repetition": repetition + 1,
                    "sample_index": completed_samples + 1,
                    "expected_sample_count": expected_sample_count,
                    "completed_sample_count": completed_samples,
                    "temperature": config["software"]["temperature"],
                    "max_output_tokens": config["software"][
                        "max_output_tokens"
                    ],
                    "elapsed_seconds": candidate_timeout_seconds,
                    "request_timeout_seconds": None,
                    "attempt_count": 0,
                    "attempts": [],
                    "timeout_scope": "candidate",
                }
                raise error

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
            attempt_events = []

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
                    max_attempts=request_retries + 1,
                    retry_delay_seconds=(
                        request_retry_delay_seconds
                    ),
                    deadline=candidate_deadline,
                    attempt_events=attempt_events,
                )

            except Exception as exc:
                elapsed_seconds = (
                    time.perf_counter()
                    - start
                )

                slot_state = inspect_slots(
                    mapping["endpoint"],
                    timeout=min(
                        2,
                        max(
                            0.001,
                            candidate_deadline
                            - time.monotonic(),
                        ),
                    ),
                )

                attempts = getattr(
                    exc,
                    "request_attempts",
                    attempt_events,
                )

                sample_failure = {
                    "question_id": question_id,
                    "repetition": repetition + 1,
                    "sample_index": sample_number,
                    "expected_sample_count": expected_sample_count,
                    "completed_sample_count": completed_samples,
                    "temperature": config["software"]["temperature"],
                    "max_output_tokens": config["software"][
                        "max_output_tokens"
                    ],
                    "elapsed_seconds": round(
                        elapsed_seconds,
                        6,
                    ),
                    "request_timeout_seconds": per_request_timeout,
                    "attempt_count": len(attempts),
                    "attempts": attempts,
                    "timeout_scope": getattr(
                        exc,
                        "timeout_scope",
                        None,
                    ),
                    "slot_state_after_failure": slot_state,
                }

                exc.sample_failure = sample_failure
                exc.args = (
                    f"{exc} "
                    f"(question_id={question_id}, "
                    f"repetition={repetition + 1}, "
                    f"sample_index={sample_number}, "
                    f"attempts={len(attempts)}, "
                    f"elapsed_seconds={elapsed_seconds:.3f}, "
                    f"timeout_seconds={per_request_timeout:.3f})",
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
                request_attempt_count=(
                    len(attempt_events)
                ),
                request_retry_count=(
                    max(
                        0,
                        len(attempt_events) - 1,
                    )
                ),
                request_attempts=(
                    attempt_events
                ),
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
        retried_sample_count=sum(
            sample["request_retry_count"] > 0
            for sample in samples
        ),
        request_retry_count=sum(
            sample["request_retry_count"]
            for sample in samples
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
