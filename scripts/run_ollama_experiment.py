from __future__ import annotations

from pathlib import Path
from pprint import pprint

import yaml

from src.tutor.knobs import validate_software_candidate
from src.tutor.ollama_runtime import (
    call_ollama,
    extract_metrics,
    load_system_prompt,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = (
    PROJECT_ROOT
    / "experiment-contracts"
    / "testing"
    / "ollama-smoke.yaml"
)


def main():
    with CONFIG_PATH.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    validate_software_candidate(config)

    runtime = config["runtime"]
    software = config["software"]
    prompt = config["prompt"]

    system_prompt = load_system_prompt(
        prompt["system_prompt"]
    )

    result = call_ollama(
        endpoint=runtime["endpoint"],
        model=runtime["model"],
        system_prompt=system_prompt,
        user_prompt=prompt["user_prompt"],
        temperature=software["temperature"],
        max_output_tokens=software["max_output_tokens"],
    )

    metrics = extract_metrics(result)

    print("\nModel response:")
    print(result["response"])

    print("\nSoftware configuration:")
    pprint(software)

    print("\nMeasured metrics:")
    pprint(metrics)


if __name__ == "__main__":
    main()
