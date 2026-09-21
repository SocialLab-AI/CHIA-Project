"""Shared failure taxonomy; owned by integration, used by every loop boundary."""


class LoopError(Exception):
    """A safe public reason, never raw runtime output or candidate contents."""

    code = "LOOP_ERROR"
    transient = False


class ConfigError(LoopError, ValueError):
    code = "INVALID_CANDIDATE"


class PreflightError(LoopError):
    code = "PREFLIGHT_FAILED"


class RuntimeExecutionError(LoopError):
    code = "RUNTIME_FAILED"


class TransientRuntimeError(RuntimeExecutionError):
    code = "RUNTIME_UNAVAILABLE"
    transient = True


class ExecutionTimeout(RuntimeExecutionError):
    code = "TIMEOUT"


class MetricsError(LoopError):
    code = "INVALID_METRICS"


class OptimizerError(LoopError):
    code = "INVALID_PROPOSAL"


def failure(error, stage):
    """Do not expose arbitrary exception strings (HTTP bodies may contain secrets)."""
    result = {
        "stage": stage,
        "error_type": type(error).__name__,
        "code": getattr(error, "code", "UNEXPECTED_ERROR"),
        "message": str(error)
        if isinstance(error, LoopError)
        else "Unexpected runtime failure; inspect restricted local artifacts.",
        "transient": bool(getattr(error, "transient", False)),
    }
    runtime_stage = getattr(error, "runtime_stage", None)
    if runtime_stage in {
        "image_inspect",
        "gem5_version",
        "compiler_version",
        "compile_kernel",
        "gem5_simulation",
        "energy_preflight",
        "energy_mapping",
        "energy_execution",
        "energy_verification",
    }:
        result["runtime_stage"] = runtime_stage
    for name in ("stdout_summary", "stderr_summary"):
        summary = getattr(error, name, None)
        if (
            isinstance(summary, dict)
            and set(summary) == {"bytes", "sha256", "content"}
            and summary.get("content") == "[omitted]"
            and isinstance(summary.get("bytes"), int)
            and isinstance(summary.get("sha256"), str)
        ):
            result[name] = summary
    return result
