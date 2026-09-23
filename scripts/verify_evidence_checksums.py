#!/usr/bin/env python3
"""Verify committed experiment evidence checksums without raw server artifacts."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "experiments" / "evidence"

# These files are intentionally deployment-local. Their recorded hashes remain
# useful for checking a separately retained copy, but absence from Git is not an
# integrity failure. Any other missing checksum target fails the audit.
EXPECTED_EXTERNAL = {
    EVIDENCE
    / "final-burst-gemini-20260921"
    / "final-burst-gemini-evidence.tgz",
    EVIDENCE
    / "final-burst-250q-gemini-vs-random-20260922"
    / "20260922T100532Z-gemini-vs-random-audit.zip",
    EVIDENCE
    / "qwen-proxy-comparison-20260918-01"
    / "checkpoint.json",
    EVIDENCE
    / "qwen-proxy-comparison-20260918-01"
    / "proxy-comparison.json",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_manifest(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            expected, relative = line.split(None, 1)
            yield relative.strip().lstrip("*"), expected


def _json_manifest(path: Path):
    yield from json.loads(path.read_text(encoding="utf-8")).items()


def audit_evidence() -> dict:
    checks = []
    manifests = sorted(EVIDENCE.rglob("SHA256SUMS"))
    manifests += sorted(EVIDENCE.rglob("SHA256SUMS.json"))
    manifests += sorted(EVIDENCE.rglob("raw-evidence.sha256"))

    for manifest in manifests:
        entries = (
            _json_manifest(manifest)
            if manifest.name.endswith(".json")
            else _text_manifest(manifest)
        )
        for relative, expected in entries:
            target = manifest.parent / relative
            if not target.exists():
                status = "external" if target in EXPECTED_EXTERNAL else "missing"
                checks.append(
                    {
                        "manifest": str(manifest.relative_to(ROOT)),
                        "target": str(target.relative_to(ROOT)),
                        "status": status,
                    }
                )
                continue
            actual = _digest(target)
            checks.append(
                {
                    "manifest": str(manifest.relative_to(ROOT)),
                    "target": str(target.relative_to(ROOT)),
                    "status": "passed" if actual == expected else "mismatch",
                    "expected": expected,
                    "actual": actual,
                }
            )

    failures = [
        item for item in checks if item["status"] in {"missing", "mismatch"}
    ]
    observed_external = {
        ROOT / item["target"]
        for item in checks
        if item["status"] == "external"
    }
    for path in sorted(EXPECTED_EXTERNAL - observed_external):
        failures.append(
            {
                "target": str(path.relative_to(ROOT)),
                "status": "external_allowlist_not_referenced",
            }
        )

    return {
        "status": "passed" if not failures else "failed",
        "verified_files": sum(item["status"] == "passed" for item in checks),
        "external_files": sum(item["status"] == "external" for item in checks),
        "failures": failures,
    }


def main() -> int:
    result = audit_evidence()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
