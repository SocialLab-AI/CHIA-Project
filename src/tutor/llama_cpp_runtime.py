"""llama.cpp server adapter; Tutor owns local inference transport and provenance."""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path

from src.common.errors import (
    ExecutionTimeout,
    MetricsError,
    PreflightError,
    RuntimeExecutionError,
    TransientRuntimeError,
)
from src.common.security import local_endpoint, strict_json


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeExecutionError("Runtime HTTP redirects are forbidden.")


def request_json(
    endpoint,
    route,
    payload=None,
    *,
    timeout=120,
    expected_type=dict,
):
    """Exchange one bounded JSON object with a loopback llama.cpp server."""

    endpoint = local_endpoint(endpoint)

    request = urllib.request.Request(
        endpoint + route,
        data=(
            None
            if payload is None
            else json.dumps(
                payload,
                allow_nan=False,
            ).encode()
        ),
        headers={
            "Content-Type": "application/json"
        },
        method="GET" if payload is None else "POST",
    )

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        NoRedirect(),
    )

    try:
        with opener.open(
            request,
            timeout=timeout,
        ) as response:
            data = response.read(1048577)

            if len(data) > 1048576:
                raise RuntimeExecutionError(
                    "Runtime response exceeds the limit."
                )

            result = strict_json(
                data.decode("utf-8")
            )

            if (
                not isinstance(result, expected_type)
                or (
                    isinstance(result, dict)
                    and "error" in result
                )
            ):
                raise RuntimeExecutionError(
                    "llama.cpp returned an error "
                    "or malformed object."
                )

            return result

    except urllib.error.HTTPError as exc:
        if exc.code in {
            429,
            502,
            503,
            504,
        }:
            raise TransientRuntimeError(
                "Local llama.cpp runtime is "
                "temporarily unavailable."
            ) from exc

        raise RuntimeExecutionError(
            f"llama.cpp request failed "
            f"with status {exc.code}."
        ) from exc

    except TimeoutError:
        raise ExecutionTimeout(
            "Local llama.cpp request timed out."
        ) from None

    except urllib.error.URLError as exc:
        if isinstance(
            exc.reason,
            TimeoutError,
        ):
            raise ExecutionTimeout(
                "Local llama.cpp request timed out."
            ) from None

        raise TransientRuntimeError(
            "Cannot connect to the local "
            "llama.cpp runtime."
        ) from exc


def inspect_slots(endpoint, *, timeout=2):
    """Return a safe slot-activity snapshot for failure diagnostics.

    The llama.cpp slot response can contain request parameters, so this
    adapter deliberately retains only identifiers and processing state.
    """

    try:
        slots = request_json(
            endpoint,
            "/slots",
            timeout=timeout,
            expected_type=list,
        )
    except Exception as error:
        return {
            "available": False,
            "error_type": type(error).__name__,
        }

    safe_slots = []

    for slot in slots:
        if not isinstance(slot, dict):
            continue

        safe_slot = {
            "is_processing": bool(
                slot.get("is_processing", False)
            ),
        }

        for field in ("id", "id_task"):
            value = slot.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                safe_slot[field] = value

        safe_slots.append(safe_slot)

    return {
        "available": True,
        "slot_count": len(safe_slots),
        "processing_count": sum(
            slot["is_processing"]
            for slot in safe_slots
        ),
        "slots": safe_slots,
    }


def file_sha256(path):
    value = hashlib.sha256()

    with Path(path).open("rb") as stream:
        for block in iter(
            lambda: stream.read(
                1024 * 1024
            ),
            b"",
        ):
            value.update(block)

    return value.hexdigest()


def preflight(endpoint, mapping, *, timeout=10):
    """Verify server health and exact model/config identity."""

    health = request_json(
        endpoint,
        "/health",
        timeout=timeout,
    )

    props = request_json(
        endpoint,
        "/props",
        timeout=timeout,
    )

    if health.get("status") != "ok":
        raise PreflightError(
            "llama.cpp server is not ready."
        )

    assertions = mapping[
        "artifact_assertions"
    ]

    model_path = Path(
        assertions["model_path"]
    ).resolve()

    served_path = Path(
        props.get("model_path", "")
    ).resolve()

    if served_path != model_path:
        raise PreflightError(
            "llama.cpp serves a different GGUF artifact."
        )

    actual_sha256 = file_sha256(
        model_path
    )

    if (
        actual_sha256
        != assertions["model_sha256"]
    ):
        raise PreflightError(
            "GGUF SHA-256 differs from "
            "the reviewed artifact."
        )

    defaults = props.get(
        "default_generation_settings",
        {},
    )

    if (
        defaults.get("n_ctx")
        != mapping["context_tokens"]
    ):
        raise PreflightError(
            "llama.cpp context size differs "
            "from campaign config."
        )

    if (
        props.get("total_slots")
        != mapping["parallel_slots"]
    ):
        raise PreflightError(
            "llama.cpp parallel slot count "
            "differs from campaign config."
        )

    build_info = props.get(
        "build_info"
    )

    if (
        not isinstance(build_info, str)
        or not build_info.strip()
    ):
        raise PreflightError(
            "llama.cpp build information "
            "is unavailable."
        )

    return {
        "runtime": "llama.cpp-server",
        "runtime_build": build_info,
        "model_id": assertions["model"],
        "model_path": str(model_path),
        "model_sha256": actual_sha256,
        "weight_quantization": assertions[
            "weight_quantization"
        ],
        "context_tokens": mapping[
            "context_tokens"
        ],
        "parallel_slots": mapping[
            "parallel_slots"
        ],
        "cpu_threads_operator_assertion": mapping[
            "cpu_threads"
        ],
    }


def call_llama_cpp(
    *,
    endpoint,
    model,
    system_prompt,
    user_prompt,
    temperature,
    max_output_tokens,
    timeout=120,
    max_attempts=2,
    retry_delay_seconds=2.0,
    deadline=None,
    attempt_events=None,
):
    """Call the local llama.cpp chat endpoint.

    Only transient availability failures are retried. A client-side timeout
    is not retried because it does not prove that llama.cpp cancelled the
    original generation; with one server slot, an immediate retry can queue
    behind the still-running request.

    Runtime/model errors and malformed responses are not retried,
    because those indicate deterministic configuration/runtime failures.
    """

    if (
        isinstance(max_attempts, bool)
        or not isinstance(
            max_attempts,
            int,
        )
        or max_attempts < 1
    ):
        raise ValueError(
            "max_attempts must be "
            "a positive integer."
        )

    if (
        isinstance(
            retry_delay_seconds,
            bool,
        )
        or not isinstance(
            retry_delay_seconds,
            (int, float),
        )
        or retry_delay_seconds < 0
    ):
        raise ValueError(
            "retry_delay_seconds must "
            "be nonnegative."
        )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "temperature": temperature,
        "max_tokens": max_output_tokens,
        "stream": False,
        "cache_prompt": False,
    }

    events = (
        attempt_events
        if attempt_events is not None
        else []
    )

    for attempt in range(
        1,
        max_attempts + 1,
    ):
        remaining = None

        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                error = ExecutionTimeout(
                    "Software candidate deadline expired before request attempt."
                )
                error.timeout_scope = "candidate"
                error.request_attempts = list(events)
                raise error

        attempt_timeout = (
            timeout
            if remaining is None
            else min(timeout, remaining)
        )
        started = time.monotonic()

        try:
            result = request_json(
                endpoint,
                "/v1/chat/completions",
                payload,
                timeout=attempt_timeout,
            )

            events.append(
                {
                    "attempt": attempt,
                    "status": "completed",
                    "elapsed_seconds": round(
                        time.monotonic() - started,
                        6,
                    ),
                    "timeout_seconds": attempt_timeout,
                }
            )

            return result

        except ExecutionTimeout as error:
            error.timeout_scope = getattr(
                error,
                "timeout_scope",
                "request",
            )
            events.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "elapsed_seconds": round(
                        time.monotonic() - started,
                        6,
                    ),
                    "timeout_seconds": attempt_timeout,
                    "retry_scheduled": False,
                }
            )
            error.request_attempts = list(events)
            raise

        except TransientRuntimeError as error:
            retry_scheduled = attempt < max_attempts
            events.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "elapsed_seconds": round(
                        time.monotonic() - started,
                        6,
                    ),
                    "timeout_seconds": attempt_timeout,
                    "retry_scheduled": retry_scheduled,
                }
            )

            if attempt >= max_attempts:
                error.request_attempts = list(events)
                raise

            delay = (
                retry_delay_seconds
                * (2 ** (attempt - 1))
            )

            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= delay:
                    deadline_error = ExecutionTimeout(
                        "Software candidate deadline expired before request retry."
                    )
                    deadline_error.timeout_scope = "candidate"
                    deadline_error.request_attempts = list(events)
                    raise deadline_error from error

            time.sleep(delay)

        except Exception as error:
            events.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "elapsed_seconds": round(
                        time.monotonic() - started,
                        6,
                    ),
                    "timeout_seconds": attempt_timeout,
                    "retry_scheduled": False,
                }
            )
            error.request_attempts = list(events)
            raise

    raise RuntimeExecutionError(
        "llama.cpp generation exhausted "
        "all attempts unexpectedly."
    )


def extract_generation(result):
    """Validate response and normalize llama.cpp timing fields."""

    choices = result.get(
        "choices"
    )

    timings = result.get(
        "timings"
    )

    usage = result.get(
        "usage"
    )

    if (
        not isinstance(
            choices,
            list,
        )
        or len(choices) != 1
        or not isinstance(
            timings,
            dict,
        )
        or not isinstance(
            usage,
            dict,
        )
    ):
        raise MetricsError(
            "llama.cpp response is missing "
            "choices, usage or timings."
        )

    choice = choices[0]

    message = choice.get(
        "message",
        {},
    )

    answer = message.get(
        "content"
    )

    if (
        choice.get("finish_reason")
        not in {
            "stop",
            "length",
        }
        or not isinstance(
            answer,
            str,
        )
        or not answer.strip()
    ):
        raise MetricsError(
            "llama.cpp did not return "
            "a completed nonempty answer."
        )

    def positive_number(
        container,
        name,
    ):
        value = container.get(
            name
        )

        if (
            isinstance(value, bool)
            or not isinstance(
                value,
                (int, float),
            )
            or not math.isfinite(
                value
            )
            or value <= 0
        ):
            raise MetricsError(
                f"llama.cpp metric {name} "
                "is missing or invalid."
            )

        return value

    prompt_tokens = positive_number(
        usage,
        "prompt_tokens",
    )

    completion_tokens = positive_number(
        usage,
        "completion_tokens",
    )

    prompt_ms = positive_number(
        timings,
        "prompt_ms",
    )

    generation_ms = positive_number(
        timings,
        "predicted_ms",
    )

    generation_tps = positive_number(
        timings,
        "predicted_per_second",
    )

    return answer, {
        "total_latency_ms": (
            prompt_ms
            + generation_ms
        ),
        "prompt_eval_latency_ms": (
            prompt_ms
        ),
        "generation_latency_ms": (
            generation_ms
        ),
        "prompt_tokens": (
            prompt_tokens
        ),
        "completion_tokens": (
            completion_tokens
        ),
        "generation_tokens_per_second": (
            generation_tps
        ),
        "cached_prompt_tokens": (
            timings.get(
                "cache_n",
                0,
            )
        ),
        "finish_reason": choice[
            "finish_reason"
        ],
        "system_fingerprint": (
            result.get(
                "system_fingerprint"
            )
        ),
    }
