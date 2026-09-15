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
    return {
        "stage": stage,
        "error_type": type(error).__name__,
        "code": getattr(error, "code", "UNEXPECTED_ERROR"),
        "message": str(error)
        if isinstance(error, LoopError)
        else "Unexpected runtime failure; inspect restricted local artifacts.",
        "transient": bool(getattr(error, "transient", False)),
    }
