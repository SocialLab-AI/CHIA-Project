from pathlib import Path
import json
import sys
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]

CASES = [
    (ROOT / "ai-tutor-config" / "example.ai-tutor.yaml",
     ROOT / "ai-tutor-config" / "ai-tutor.schema.json"),
    (ROOT / "attention-experiments" / "baseline.attention.yaml",
     ROOT / "attention-experiments" / "attention-experiment.schema.json"),
    (ROOT / "attention-experiments" / "example.candidate.yaml",
     ROOT / "attention-experiments" / "attention-experiment.schema.json"),
    (ROOT / "attention-experiments" / "design-space.yaml",
     ROOT / "attention-experiments" / "attention-design-space.schema.json"),
    (ROOT / "compute-policy" / "compute-policy.yaml",
     ROOT / "compute-policy" / "compute-policy.schema.json"),
    (ROOT / "run-records" / "example.completed.yaml",
     ROOT / "run-records" / "run-record.schema.json"),
]

def load_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def validate_case(data_path, schema_path):
    data = load_yaml(data_path)
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        print(f"FAIL {data_path.relative_to(ROOT)}")
        for e in errors:
            path = ".".join(str(x) for x in e.absolute_path) or "<root>"
            print(f"  {path}: {e.message}")
        return False
    print(f"PASS {data_path.relative_to(ROOT)}")
    return True

def semantic_checks():
    ok = True

    # Compute policy: organizer burst is final-only.
    policy = load_yaml(ROOT / "compute-policy" / "compute-policy.yaml")
    for tier_name, tier in policy["tiers"].items():
        has_burst = "organizer_burst" in tier["backends"]
        if tier_name != "final" and (has_burst or tier["organizer_burst_allowed"]):
            print(f"FAIL semantic: organizer burst exposed in {tier_name}")
            ok = False
        if tier_name == "final" and (not has_burst or not tier["organizer_burst_allowed"]):
            print("FAIL semantic: final tier must explicitly allow organizer burst")
            ok = False

    # Attention baseline: threads cannot exceed modeled cores.
    baseline = load_yaml(ROOT / "attention-experiments" / "baseline.attention.yaml")
    if baseline["software"]["threads"] > baseline["hardware"]["cores"]:
        print("FAIL semantic: attention threads exceed modeled cores")
        ok = False

    # Hardware: RiscvTimingSimpleCPU requires issue_width == 1
    hw = baseline["hardware"]
    if hw["cpu_model"] == "RiscvTimingSimpleCPU" and hw.get("issue_width", 1) != 1:
        print("FAIL semantic: TimingSimpleCPU requires issue_width 1")
        ok = False

    # Hardware: DDR4 must not be the active memory_type
    if hw["memory_type"] != "DDR3_1600_8x8":
        print(f"FAIL semantic: unsupported memory model {hw['memory_type']}")
        ok = False

    # Design space: current active KV formats must not include teammate-marked planned values (FP16, Q8).
    ds = load_yaml(ROOT / "attention-experiments" / "design-space.yaml")
    active_kv = set(ds["active_candidates"]["software"].get("kv_format", []))
    forbidden_now = {"FP16", "Q8"}
    if active_kv & forbidden_now:
        print("FAIL semantic: planned KV formats exposed as active before verification")
        ok = False

    # Context extended values should not be in current evaluation axis.
    if any(x > 512 for x in ds["evaluation_axes"]["context_tokens"]):
        print("FAIL semantic: context >512 exposed before runtime testing gate")
        ok = False

    if ok:
        print("PASS semantic policy checks")
    return ok

def main():
    ok = True
    for data_path, schema_path in CASES:
        ok = validate_case(data_path, schema_path) and ok
    ok = semantic_checks() and ok
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
