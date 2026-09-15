"""Hardware diagnostic only; integration owns the supported combined run_experiment CLI."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common.errors import PreflightError


def main():
    raise PreflightError(
        "Use scripts/run_experiment.py with an explicit hardware runtime/tolerance; the old unbounded baseline launcher is retired."
    )


if __name__ == "__main__":
    main()
