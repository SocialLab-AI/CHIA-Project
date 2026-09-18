"""Tutor request timeout, retry, and failure-provenance tests."""

from unittest.mock import patch

import pytest

from src.common.candidate import baseline_candidate
from src.common.errors import (
    ExecutionTimeout,
    RuntimeExecutionError,
    TransientRuntimeError,
)
from src.tutor.llama_cpp_runtime import call_llama_cpp
from src.tutor.runner import (
    run_software_candidate,
    software_failure,
)


def _call(**overrides):
    arguments = {
        "endpoint": "http://127.0.0.1:8081",
        "model": "fixture",
        "system_prompt": "system",
        "user_prompt": "question",
        "temperature": 0.2,
        "max_output_tokens": 128,
        "timeout": 10,
        "max_attempts": 2,
        "retry_delay_seconds": 0,
    }
    arguments.update(overrides)
    return call_llama_cpp(**arguments)


def _reply():
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": "Mass measures inertia and is harder to accelerate."
                },
            }
        ],
        "usage": {
            "prompt_tokens": 4,
            "completion_tokens": 10,
        },
        "timings": {
            "prompt_ms": 10.0,
            "predicted_ms": 100.0,
            "predicted_per_second": 100.0,
            "cache_n": 0,
        },
    }


def _evaluation():
    return {
        "dataset_id": "fixture",
        "source_url": "custom-user-provided",
        "license": "project evaluation data",
        "items": [
            {
                "question": {
                    "id": "q001",
                    "question": "What does mass measure?",
                },
                "reference": {
                    "required_concepts": [
                        ["mass measures inertia"],
                        ["harder to accelerate"],
                    ]
                },
            }
        ],
    }


def _mapping():
    return {
        "endpoint": "http://127.0.0.1:8081",
        "request": {
            "model": "fixture",
            "temperature": 0.0,
            "max_output_tokens": 384,
        },
    }


def test_normal_request_records_one_completed_attempt():
    events = []

    with patch(
        "src.tutor.llama_cpp_runtime.request_json",
        return_value={"ok": True},
    ) as request:
        result = _call(attempt_events=events)

    assert result == {"ok": True}
    assert request.call_count == 1
    assert events[0]["attempt"] == 1
    assert events[0]["status"] == "completed"
    assert events[0]["timeout_seconds"] == 10


def test_transient_failure_is_retried_and_audited():
    events = []

    with patch(
        "src.tutor.llama_cpp_runtime.request_json",
        side_effect=[
            TransientRuntimeError("temporarily unavailable"),
            {"ok": True},
        ],
    ) as request:
        result = _call(attempt_events=events)

    assert result == {"ok": True}
    assert request.call_count == 2
    assert [event["status"] for event in events] == [
        "failed",
        "completed",
    ]
    assert events[0]["retry_scheduled"] is True


def test_request_timeout_is_not_retried_on_single_slot_runtime():
    events = []

    with patch(
        "src.tutor.llama_cpp_runtime.request_json",
        side_effect=ExecutionTimeout("timed out"),
    ) as request:
        with pytest.raises(ExecutionTimeout) as caught:
            _call(attempt_events=events)

    assert request.call_count == 1
    assert caught.value.request_attempts == events
    assert events[0]["retry_scheduled"] is False


def test_transient_retry_exhaustion_preserves_every_attempt():
    with patch(
        "src.tutor.llama_cpp_runtime.request_json",
        side_effect=TransientRuntimeError("temporarily unavailable"),
    ) as request:
        with pytest.raises(TransientRuntimeError) as caught:
            _call(max_attempts=3)

    assert request.call_count == 3
    assert len(caught.value.request_attempts) == 3
    assert caught.value.request_attempts[-1]["retry_scheduled"] is False


def test_deterministic_runtime_failure_is_not_retried():
    with patch(
        "src.tutor.llama_cpp_runtime.request_json",
        side_effect=RuntimeExecutionError("invalid request"),
    ) as request:
        with pytest.raises(RuntimeExecutionError) as caught:
            _call(max_attempts=3)

    assert request.call_count == 1
    assert len(caught.value.request_attempts) == 1
    assert caught.value.request_attempts[0]["retry_scheduled"] is False


def test_runner_failure_records_question_repetition_and_attempt_provenance():
    config = baseline_candidate()
    request_error = ExecutionTimeout("timed out")
    request_error.request_attempts = [
        {
            "attempt": 1,
            "status": "failed",
            "error_type": "ExecutionTimeout",
            "message": "timed out",
            "elapsed_seconds": 60.0,
            "timeout_seconds": 60,
            "retry_scheduled": False,
        }
    ]

    with (
        patch("src.tutor.runner.map_final_tutor", return_value=_mapping()),
        patch("src.tutor.runner.preflight", return_value={"runtime": "fixture"}),
        patch("src.tutor.runner.load_evaluation_set", return_value=_evaluation()),
        patch("src.tutor.runner.call_llama_cpp", side_effect=request_error),
        patch(
            "src.tutor.runner.inspect_slots",
            return_value={
                "available": True,
                "slot_count": 1,
                "processing_count": 1,
                "slots": [{"id": 0, "is_processing": True}],
            },
        ),
    ):
        with pytest.raises(ExecutionTimeout) as caught:
            run_software_candidate(
                config,
                {
                    "candidate_timeout_seconds": 600,
                    "request_timeout_seconds": 60,
                    "request_retries": 1,
                },
            )

    error = software_failure(caught.value)
    sample = error["sample"]
    assert sample["question_id"] == "q001"
    assert sample["repetition"] == 1
    assert sample["sample_index"] == 1
    assert sample["temperature"] == 0.0
    assert sample["max_output_tokens"] == 384
    assert sample["attempt_count"] == 1
    assert sample["request_timeout_seconds"] == 60
    assert sample["slot_state_after_failure"]["processing_count"] == 1


def test_request_timeout_is_distinct_from_candidate_deadline():
    config = baseline_candidate()

    with (
        patch("src.tutor.runner.map_final_tutor", return_value=_mapping()),
        patch("src.tutor.runner.preflight", return_value={"runtime": "fixture"}),
        patch("src.tutor.runner.load_evaluation_set", return_value=_evaluation()),
        patch("src.tutor.runner.call_llama_cpp", return_value=_reply()) as call,
    ):
        run_software_candidate(
            config,
            {
                "candidate_timeout_seconds": 500,
                "request_timeout_seconds": 7,
                "request_retries": 0,
            },
        )

    assert call.call_args.kwargs["timeout"] == 7
    assert call.call_args.kwargs["max_attempts"] == 1
    assert call.call_args.kwargs["deadline"] > 0


def test_candidate_deadline_can_expire_before_next_request():
    config = baseline_candidate()

    with (
        patch("src.tutor.runner.map_final_tutor", return_value=_mapping()),
        patch("src.tutor.runner.preflight", return_value={"runtime": "fixture"}),
        patch("src.tutor.runner.load_evaluation_set", return_value=_evaluation()),
        patch(
            "src.tutor.runner.time.monotonic",
            side_effect=[100.0, 100.0, 106.0],
        ),
        patch("src.tutor.runner.call_llama_cpp") as call,
    ):
        with pytest.raises(ExecutionTimeout, match="candidate deadline"):
            run_software_candidate(
                config,
                {
                    "candidate_timeout_seconds": 5,
                    "request_timeout_seconds": 2,
                },
            )

    call.assert_not_called()
