#!/usr/bin/env python3
"""Canonical configuration and schema validator for CHIA co-design experiments.

Validates all contracts, schemas, YAML configurations, semantic policies,
and cross-document consistency under experiment-contracts/ and docs/.
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "experiment-contracts"
SCHEMAS_DIR = CONTRACTS / "schemas"
AI_TUTOR_DIR = CONTRACTS / "ai-tutor-config"
ATTN_DIR = CONTRACTS / "attention-experiments"
COMPUTE_DIR = CONTRACTS / "compute-policy"
RUN_RECORDS_DIR = CONTRACTS / "run-records"
DOCS_DIR = ROOT / "docs"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_registry() -> tuple[Registry, dict[str, dict]]:
    """Build referencing.Registry with all contracts schemas preloaded."""
    schema_files = {
        "shared.schema.json": SCHEMAS_DIR / "shared.schema.json",
        "attention-experiment.schema.json": ATTN_DIR / "attention-experiment.schema.json",
        "attention-design-space.schema.json": ATTN_DIR / "attention-design-space.schema.json",
        "ai-tutor.schema.json": AI_TUTOR_DIR / "ai-tutor.schema.json",
        "ai-tutor-design-space.schema.json": AI_TUTOR_DIR / "ai-tutor-design-space.schema.json",
        "compute-policy.schema.json": COMPUTE_DIR / "compute-policy.schema.json",
        "run-record.schema.json": RUN_RECORDS_DIR / "run-record.schema.json",
    }

    schemas = {}
    reg = Registry()

    for name, path in schema_files.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing required schema: {path}")
        content = load_json(path)
        try:
            Draft202012Validator.check_schema(content)
        except SchemaError as e:
            raise ValueError(f"Schema {name} is structurally invalid: {e.message}") from e

        schemas[name] = content
        res = Resource.from_contents(content)
        reg = reg.with_resource(name, res)
        reg = reg.with_resource(path.as_uri(), res)
        if "$id" in content:
            reg = reg.with_resource(content["$id"], res)

    return reg, schemas


def validate_document(
    data_path: Path,
    schema_path: Path,
    registry: Registry,
    verbose: bool = True,
) -> bool:
    data = load_yaml(data_path)
    schema = load_json(schema_path)
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))

    if errors:
        if verbose:
            print(f"[FAIL] {data_path.relative_to(ROOT)}")
            for e in errors:
                loc = ".".join(str(x) for x in e.absolute_path) or "<root>"
                print(f"       {loc}: {e.message}")
        return False

    if verbose:
        print(f"[PASS] {data_path.relative_to(ROOT)} conforms to {schema_path.name}")
    return True


def run_semantic_checks(verbose: bool = True) -> bool:
    ok = True

    # 1. Compute Policy Checks
    policy = load_yaml(COMPUTE_DIR / "compute-policy.yaml")
    tiers = policy.get("tiers", {})
    for tier_name, tier in tiers.items():
        has_burst = "organizer_burst" in tier.get("backends", [])
        burst_allowed = tier.get("organizer_burst_allowed", False)
        if tier_name != "final":
            if has_burst or burst_allowed:
                if verbose:
                    print(f"[FAIL] Compute policy exposes organizer burst in non-final tier '{tier_name}'")
                ok = False
        else:
            if not has_burst or not burst_allowed:
                if verbose:
                    print("[FAIL] Compute policy final tier must explicitly allow organizer burst")
                ok = False

    # 2. Hardware / Attention Baseline Checks
    baseline_attn = load_yaml(ATTN_DIR / "baseline.attention.yaml")
    hw = baseline_attn["hardware"]
    sw = baseline_attn["software"]
    meas = baseline_attn["measurement"]

    # Q4 campaign restrictions
    if hw["cores"] != 2:
        if verbose:
            print(f"[FAIL] Baseline attention simulated cores must be 2, got {hw['cores']}")
        ok = False
    if sw["threads"] != 2:
        if verbose:
            print(f"[FAIL] Baseline attention proxy threads must be 2, got {sw['threads']}")
        ok = False
    if sw["kv_format"] != "Q4":
        if verbose:
            print(f"[FAIL] Baseline attention proxy KV format must be Q4, got {sw['kv_format']}")
        ok = False
    if sw["threads"] > hw["cores"]:
        if verbose:
            print("[FAIL] Baseline attention proxy threads cannot exceed simulated cores")
        ok = False
    if hw["memory_type"] != "DDR3_1600_8x8":
        if verbose:
            print(f"[FAIL] Baseline attention memory must be DDR3_1600_8x8, got {hw['memory_type']}")
        ok = False
    if hw["memory_size_mib"] != 16:
        if verbose:
            print(f"[FAIL] Baseline attention memory size must be 16 MiB, got {hw['memory_size_mib']}")
        ok = False
    if hw["simulation_mode"] != "SE":
        if verbose:
            print(f"[FAIL] Baseline attention mode must be SE, got {hw['simulation_mode']}")
        ok = False
    if meas["repetitions"] != 10:
        if verbose:
            print(f"[FAIL] Baseline attention repetitions must be 10, got {meas['repetitions']}")
        ok = False
    if meas["warmup_runs"] != 0:
        if verbose:
            print(f"[FAIL] Baseline attention warmup runs must be 0, got {meas['warmup_runs']}")
        ok = False

    # TimingSimpleCPU requires issue_width == 1
    if hw["cpu_model"] == "RiscvTimingSimpleCPU" and hw.get("issue_width", 1) != 1:
        if verbose:
            print("[FAIL] TimingSimpleCPU requires issue_width == 1")
        ok = False

    # Emitted metrics checks
    metrics = baseline_attn.get("metrics", {})
    required_metrics = [
        "sim_ticks", "simulated_seconds", "latency_ms", "host_seconds",
        "instructions", "cycles_per_core", "cpi_per_core", "ipc_per_core",
        "aggregate_ipc", "l1i_miss_rate_per_core", "l1d_miss_rate_per_core",
        "l2_miss_rate", "dram_bytes_read", "dram_bandwidth_bytes_per_second",
        "average_dram_access_latency_ns"
    ]
    for m in required_metrics:
        if m not in metrics:
            if verbose:
                print(f"[FAIL] Missing emitted hardware metric in baseline: {m}")
            ok = False

    # 3. Hardware Design Space Checks
    ds_attn = load_yaml(ATTN_DIR / "design-space.yaml")
    active_hw = ds_attn["active_candidates"]["hardware"]
    if "cpu_model" not in active_hw or "frequency_ghz" not in active_hw:
        if verbose:
            print("[FAIL] Active hardware candidates missing required knobs")
        ok = False
    # Ensure active_candidates does NOT contain software (software exploration deferred in Q4 campaign)
    if "software" in ds_attn.get("active_candidates", {}):
        if verbose:
            print("[FAIL] Active candidates should not contain software search in Q4 campaign")
        ok = False
    # Evaluation axes
    if any(x > 512 for x in ds_attn["evaluation_axes"]["context_tokens"]):
        if verbose:
            print("[FAIL] Context tokens >512 exposed in evaluation_axes before runtime validation")
        ok = False

    # 4. AI Tutor Software Baseline Checks
    tutor_cfg = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")
    tutor_sw = tutor_cfg["software"]
    tutor_eval = tutor_cfg["evaluation"]

    if tutor_sw["model"] != "Llama 3.2 1B Instruct":
        if verbose:
            print(f"[FAIL] Tutor model must be 'Llama 3.2 1B Instruct', got {tutor_sw['model']}")
        ok = False
    if tutor_sw["quantization"] != "Q4_K_M":
        if verbose:
            print(f"[FAIL] Tutor quantization must be 'Q4_K_M', got {tutor_sw['quantization']}")
        ok = False
    if tutor_sw["backend"] != "llama.cpp / CPU":
        if verbose:
            print(f"[FAIL] Tutor backend must be 'llama.cpp / CPU', got {tutor_sw['backend']}")
        ok = False
    if tutor_sw["cpu_threads"] != 4:
        if verbose:
            print(f"[FAIL] Tutor CPU threads must be 4, got {tutor_sw['cpu_threads']}")
        ok = False
    if tutor_sw["batch_size"] != 1:
        if verbose:
            print(f"[FAIL] Tutor batch size must be 1, got {tutor_sw['batch_size']}")
        ok = False
    if tutor_sw["temperature"] != 0.0:
        if verbose:
            print(f"[FAIL] Tutor temperature must be 0.0, got {tutor_sw['temperature']}")
        ok = False
    if tutor_sw["max_output_tokens"] != 384:
        if verbose:
            print(f"[FAIL] Tutor max_output_tokens must be 384, got {tutor_sw['max_output_tokens']}")
        ok = False
    if tutor_sw["embedding_model"] != "MiniLM-L6-dot-v1":
        if verbose:
            print(f"[FAIL] Tutor embedding model must be 'MiniLM-L6-dot-v1', got {tutor_sw['embedding_model']}")
        ok = False
    if tutor_sw["embedding_dimension"] != 384:
        if verbose:
            print(f"[FAIL] Tutor embedding dimension must be 384, got {tutor_sw['embedding_dimension']}")
        ok = False
    if tutor_sw["retrieval_method"] != "Semantic similarity":
        if verbose:
            print(f"[FAIL] Tutor retrieval method must be 'Semantic similarity', got {tutor_sw['retrieval_method']}")
        ok = False
    if tutor_sw["top_k"] != 2:
        if verbose:
            print(f"[FAIL] Tutor top_k must be 2, got {tutor_sw['top_k']}")
        ok = False
    if tutor_sw["chunk_size"] != 1500:
        if verbose:
            print(f"[FAIL] Tutor chunk_size must be 1500 characters, got {tutor_sw['chunk_size']}")
        ok = False
    if tutor_sw["chunk_overlap"] != 200:
        if verbose:
            print(f"[FAIL] Tutor chunk_overlap must be 200 characters, got {tutor_sw['chunk_overlap']}")
        ok = False
    if tutor_sw.get("chunk_unit") != "characters":
        if verbose:
            print(f"[FAIL] Tutor chunk_unit must be 'characters', got {tutor_sw.get('chunk_unit')}")
        ok = False
    if tutor_sw["chunk_overlap"] >= tutor_sw["chunk_size"]:
        if verbose:
            print("[FAIL] Chunk overlap must be strictly less than chunk size")
        ok = False
    if tutor_sw["runtime_ready"] is not False:
        if verbose:
            print("[FAIL] Tutor baseline runtime_ready must be False pending artifact resolution")
        ok = False

    # Evaluation isolation guardrail
    if tutor_eval.get("reference_source") != "openstax":
        if verbose:
            print(f"[FAIL] Evaluation reference source must be 'openstax', got {tutor_eval.get('reference_source')}")
        ok = False
    if tutor_eval.get("reference_visible_to_model") is not False:
        if verbose:
            print("[FAIL] Evaluation references must NOT be visible to model (guardrail violation)")
        ok = False

    if ok and verbose:
        print("[PASS] Semantic policy and baseline checks passed")

    return ok


def run_negative_tests(registry: Registry, schemas: dict[str, dict], verbose: bool = True) -> bool:
    """Verify that illegal values and invalid types are rejected."""
    ok = True

    # 1. Reject TimingSimpleCPU with issue_width=2 in attention experiment
    attn_schema = schemas["attention-experiment.schema.json"]
    val = Draft202012Validator(attn_schema, registry=registry, format_checker=FormatChecker())
    base_data = load_yaml(ATTN_DIR / "example.candidate.yaml")

    bad_candidate = json.loads(json.dumps(base_data))
    bad_candidate["hardware"]["cpu_model"] = "RiscvTimingSimpleCPU"
    bad_candidate["hardware"]["issue_width"] = 2
    errors = list(val.iter_errors(bad_candidate))
    if not errors:
        if verbose:
            print("[FAIL] Negative test: TimingSimpleCPU with issue_width=2 was improperly accepted")
        ok = False
    elif verbose:
        print("[PASS] Negative test: TimingSimpleCPU with issue_width=2 was correctly rejected")

    # 2. Reject illegal hardware core count (3 cores)
    bad_candidate = json.loads(json.dumps(base_data))
    bad_candidate["hardware"]["cores"] = 3
    errors = list(val.iter_errors(bad_candidate))
    if not errors:
        if verbose:
            print("[FAIL] Negative test: cores=3 was improperly accepted")
        ok = False
    elif verbose:
        print("[PASS] Negative test: cores=3 was correctly rejected")

    # 3. Reject unknown property in attention experiment (additionalProperties: false)
    bad_candidate = json.loads(json.dumps(base_data))
    bad_candidate["illegal_property"] = True
    errors = list(val.iter_errors(bad_candidate))
    if not errors:
        if verbose:
            print("[FAIL] Negative test: unknown top-level property was improperly accepted")
        ok = False
    elif verbose:
        print("[PASS] Negative test: unknown top-level property was correctly rejected")

    # 4. Reject chunk_unit != 'characters' in ai-tutor
    tutor_schema = schemas["ai-tutor.schema.json"]
    tutor_val = Draft202012Validator(tutor_schema, registry=registry, format_checker=FormatChecker())
    tutor_data = load_yaml(AI_TUTOR_DIR / "example.ai-tutor.yaml")

    bad_tutor = json.loads(json.dumps(tutor_data))
    bad_tutor["software"]["chunk_unit"] = "tokens"
    errors = list(tutor_val.iter_errors(bad_tutor))
    if not errors:
        if verbose:
            print("[FAIL] Negative test: chunk_unit='tokens' was improperly accepted")
        ok = False
    elif verbose:
        print("[PASS] Negative test: chunk_unit='tokens' was correctly rejected")

    # 5. Reject reference_visible_to_model=True in evaluation guardrails
    bad_tutor = json.loads(json.dumps(tutor_data))
    bad_tutor["evaluation"]["reference_visible_to_model"] = True
    errors = list(tutor_val.iter_errors(bad_tutor))
    if not errors:
        if verbose:
            print("[FAIL] Negative test: reference_visible_to_model=True was improperly accepted")
        ok = False
    elif verbose:
        print("[PASS] Negative test: reference_visible_to_model=True was correctly rejected")

    return ok


def run_manifest_consistency_checks(verbose: bool = True) -> bool:
    """Verify that docs/knob-mapping.manifest.json matches active schemas and baseline."""
    manifest_path = DOCS_DIR / "knob-mapping.manifest.json"
    if not manifest_path.exists():
        if verbose:
            print(f"[FAIL] Missing manifest file: {manifest_path}")
        return False

    manifest = load_json(manifest_path)
    fields = manifest.get("fields", [])
    if not fields:
        if verbose:
            print("[FAIL] Manifest contains no fields")
        return False

    field_map = {f["field"]: f for f in fields}
    ok = True

    # Required fields in manifest
    required_in_manifest = [
        "hardware.cpu_model", "hardware.cores", "hardware.frequency_ghz", "hardware.issue_width",
        "hardware.l1i_cache_kib", "hardware.l1d_cache_kib", "hardware.l2_cache_kib",
        "hardware.memory_type", "software.implementation", "software.kv_format", "software.threads",
        "software.model", "software.quantization", "software.backend", "software.cpu_threads",
        "software.batch_size", "software.temperature", "software.max_output_tokens",
        "software.embedding_model", "software.embedding_dimension", "software.retrieval_method",
        "software.top_k", "software.chunk_size", "software.chunk_overlap", "software.runtime_ready"
    ]

    for req in required_in_manifest:
        if req not in field_map:
            if verbose:
                print(f"[FAIL] Manifest missing field entry: {req}")
            ok = False
        else:
            entry = field_map[req]
            if entry.get("status") != "PLANNED":
                if verbose:
                    print(f"[FAIL] Manifest field '{req}' status must be 'PLANNED', got '{entry.get('status')}'")
                ok = False

    # Check units for chunk size and overlap
    if field_map.get("software.chunk_size", {}).get("unit") != "characters":
        if verbose:
            print("[FAIL] Manifest software.chunk_size unit must be 'characters'")
        ok = False
    if field_map.get("software.chunk_overlap", {}).get("unit") != "characters":
        if verbose:
            print("[FAIL] Manifest software.chunk_overlap unit must be 'characters'")
        ok = False

    if ok and verbose:
        print("[PASS] Manifest consistency checks passed")

    return ok


def main() -> None:
    print("=" * 60)
    print("CHIA Experiment Contracts Canonical Validator")
    print("=" * 60)

    try:
        registry, schemas = build_registry()
    except Exception as e:
        print(f"[FATAL] Schema loading failed: {e}")
        sys.exit(1)

    cases = [
        (AI_TUTOR_DIR / "example.ai-tutor.yaml", AI_TUTOR_DIR / "ai-tutor.schema.json"),
        (AI_TUTOR_DIR / "design-space.yaml", AI_TUTOR_DIR / "ai-tutor-design-space.schema.json"),
        (ATTN_DIR / "baseline.attention.yaml", ATTN_DIR / "attention-experiment.schema.json"),
        (ATTN_DIR / "example.candidate.yaml", ATTN_DIR / "attention-experiment.schema.json"),
        (ATTN_DIR / "design-space.yaml", ATTN_DIR / "attention-design-space.schema.json"),
        (COMPUTE_DIR / "compute-policy.yaml", COMPUTE_DIR / "compute-policy.schema.json"),
        (RUN_RECORDS_DIR / "example.completed.yaml", RUN_RECORDS_DIR / "run-record.schema.json"),
    ]

    all_passed = True

    print("\n--- Structural YAML Schema Validation ---")
    for data_path, schema_path in cases:
        if not validate_document(data_path, schema_path, registry):
            all_passed = False

    print("\n--- Semantic & Domain Policy Checks ---")
    if not run_semantic_checks():
        all_passed = False

    print("\n--- Negative / Rejection Tests ---")
    if not run_negative_tests(registry, schemas):
        all_passed = False

    print("\n--- Manifest & Documentation Agreement ---")
    if not run_manifest_consistency_checks():
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("[SUCCESS] All contract validations and checks passed!")
        sys.exit(0)
    else:
        print("[FAILURE] One or more validations failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
