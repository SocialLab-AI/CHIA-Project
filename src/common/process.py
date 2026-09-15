"""Bounded argv execution; runtime owners use this helper, never a shell."""

import os
import signal
import subprocess
import tempfile
from src.common.errors import ExecutionTimeout, RuntimeExecutionError
from src.common.security import safe_output


def run_process(argv, *, cwd, timeout, env=None):
    if timeout <= 0:
        raise ExecutionTimeout("Runtime deadline expired.")
    # File-backed capture bounds RAM even when a compiler prints large output.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(
            [str(x) for x in argv],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            shell=False,
            start_new_session=os.name != "nt",
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ExecutionTimeout("Subprocess exceeded its deadline.") from exc

        def tail(stream):
            size = stream.tell()
            stream.seek(max(0, size - 65536))
            return stream.read().decode("utf-8", errors="replace")

        stdout, stderr = tail(out), tail(err)
        if process.returncode:
            error = RuntimeExecutionError(
                f"Subprocess failed with exit code {process.returncode}."
            )
            error.stdout_summary, error.stderr_summary = (
                safe_output(stdout),
                safe_output(stderr),
            )
            raise error
        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": process.returncode,
            "stdout_summary": safe_output(stdout),
            "stderr_summary": safe_output(stderr),
        }
