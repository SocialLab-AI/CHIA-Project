#!/usr/bin/env python3
"""Canonical configuration and schema validator for CHIA co-design experiments.

Validates all contracts against the master YAML schema (Draft 2020-12)
under experiment-contracts/ and verifies semantic policies and cross-document
consistency with docs/.
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "experiment-contracts"
SCHEMAS_DIR = CONTRACTS / "schemas"
BASELINES_DIR = CONTRACTS / "baselines"
DESIGN_SPACES_DIR = CONTRACTS / "design-spaces"
POLICIES_DIR = CONTRACTS / "policies"
EXAMPLES_DIR = CONTRACTS / "examples"
DOCS_DIR = ROOT / "docs"

MASTER_SCHEMA_PATH = SCHEMAS_DIR / "chia-experiment.schema.yaml"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_master_schema() -> dict:
    """Load and verify the authoritative JSON Schema Draft 2020-12 YAML master schema."""
    if not MASTER_SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Missing master schema: {MASTER_SCHEMA_PATH}")

    schema = load_yaml(MASTER_SCHEMA_PATH)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as e:
        raise ValueError(f"Master schema is structurally invalid: {e.message}") from e

    return schema


def get_validator_for_definition(
    master_schema: dict, def_name: str
) -> Draft202012Validator:
    """Create a validator for a specific $defs subschema with fully resolved local references."""
    if def_name not in master_schema.get("$defs", {}):
        raise KeyError(f"Definition '#/$defs/{def_name}' not found in master schema")

    subschema = {
        "$schema": master_schema.get(
            "$schema", "https://json-schema.org/draft/2020-12/schema"
        ),
        "$ref": f"#/$defs/{def_name}",
        "$defs": master_schema.get("$defs", {}),
    }
    return Draft202012Validator(subschema, format_checker=FormatChecker())


def validate_document(
    data_path: Path,
    def_name: str,
    master_schema: dict,
    verbose: bool = True,
) -> bool:
    data = load_yaml(data_path)
    validator = get_validator_for_definition(master_schema, def_name)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))

    if errors:
        if verbose:
            print(
                f"[FAIL] {data_path.relative_to(ROOT)} (validating against #/$defs/{def_name})"
            )
            for e in errors:
                loc = ".".join(str(x) for x in e.absolute_path) or "<root>"
                print(f"       {loc}: {e.message}")
        return False

    if verbose:
        print(f"[PASS] {data_path.relative_to(ROOT)} conforms to #/$defs/{def_name}")
    return True


def run_semantic_checks(verbose: bool = True) -> bool:
    ok = True

    # 1. Compute Policy Checks
    policy = load_yaml(POLICIES_DIR / "compute-policy.yaml")
    tiers = policy.get("tiers", {})
    for tier_name, tier in tiers.items():
        has_burst = "organizer_burst" in tier.get("backends", [])
        burst_allowed = tier.get("organizer_burst_allowed", False)
        if tier_name != "final":
            if has_burst or burst_allowed:
                if verbose:
                    print(
                        f"[FAIL] Compute policy exposes organizer burst in non-final tier '{tier_name}'"
                    )
                ok = False
        else:
            if not has_burst or not burst_allowed:
                if verbose:
                    print(
                        "[FAIL] Compute policy final tier must explicitly allow organizer burst"
                    )
                ok = False

    # 2. Hardware / Attention Baseline Checks
    baseline_attn = load_yaml(BASELINES_DIR / "attention.yaml")
    hw = baseline_attn["hardware"]
    sw = baseline_attn["software"]
    meas = baseline_attn["measurement"]

    # Q4 campaign restrictions
    if hw["cores"] != 2:
        if verbose:
            print(
                f"[FAIL] Baseline attention simulated cores must be 2, got {hw['cores']}"
            )
        ok = False
    if sw["threads"] != 2:
        if verbose:
            print(
                f"[FAIL] Baseline attention proxy threads must be 2, got {sw['threads']}"
            )
        ok = False
    if sw["kv_format"] != "Q4":
        if verbose:
            print(
                f"[FAIL] Baseline attention proxy KV format must be Q4, got {sw['kv_format']}"
            )
        ok = False
    if sw["threads"] > hw["cores"]:
        if verbose:
            print(
                "[FAIL] Baseline attention proxy threads cannot exceed simulated cores"
            )
        ok = False
    if hw["memory_type"] != "DDR3_1600_8x8":
        if verbose:
            print(
                f"[FAIL] Baseline attention memory must be DDR3_1600_8x8, got {hw['memory_type']}"
            )
        ok = False
    if hw["memory_size_mib"] != 16:
        if verbose:
            print(
                f"[FAIL] Baseline attention memory size must be 16 MiB, got {hw['memory_size_mib']}"
            )
        ok = False
    if hw["simulation_mode"] != "SE":
        if verbose:
            print(
                f"[FAIL] Baseline attention mode must be SE, got {hw['simulation_mode']}"
            )
        ok = False
    if meas["repetitions"] != 10:
        if verbose:
            print(
                f"[FAIL] Baseline attention repetitions must be 10, got {meas['repetitions']}"
            )
        ok = False
    if meas["warmup_runs"] != 0:
        if verbose:
            print(
                f"[FAIL] Baseline attention warmup runs must be 0, got {meas['warmup_runs']}"
            )
        ok = False

    # TimingSimpleCPU requires issue_width == 1
    if hw["cpu_model"] == "RiscvTimingSimpleCPU" and hw.get("issue_width", 1) != 1:
        if verbose:
            print("[FAIL] TimingSimpleCPU requires issue_width == 1")
        ok = False

    # Emitted metrics checks
    metrics = baseline_attn.get("metrics", {})
    required_metrics = [
        "sim_ticks",
        "simulated_seconds",
        "latency_ms",
        "host_seconds",
        "instructions",
        "cycles_per_core",
        "cpi_per_core",
        "ipc_per_core",
        "aggregate_ipc",
        "l1i_miss_rate_per_core",
        "l1d_miss_rate_per_core",
        "l2_miss_rate",
        "dram_bytes_read",
        "dram_bandwidth_bytes_per_second",
        "average_dram_access_latency_ns",
    ]
    for m in required_metrics:
        if m not in metrics:
            if verbose:
                print(f"[FAIL] Missing emitted hardware metric in baseline: {m}")
            ok = False

    # 3. Hardware Design Space Checks
    ds_attn = load_yaml(DESIGN_SPACES_DIR / "hardware.yaml")
    active_hw = ds_attn["active_candidates"]["hardware"]
    if "cpu_model" not in active_hw or "frequency_ghz" not in active_hw:
        if verbose:
            print("[FAIL] Active hardware candidates missing required knobs")
        ok = False
    # Ensure active_candidates does NOT contain software (software exploration deferred in Q4 campaign)
    if "software" in ds_attn.get("active_candidates", {}):
        if verbose:
            print(
                "[FAIL] Active candidates should not contain software search in Q4 campaign"
            )
        ok = False
    # Issue #60 uses the same compiled kernel shape at five reviewed contexts.
    # This remains an evaluation axis and is never exposed as an optimizer knob.
    expected_context_axis = [128, 256, 512, 1024, 2048]
    if ds_attn["evaluation_axes"]["context_tokens"] != expected_context_axis:
        if verbose:
            print(
                "[FAIL] Proxy calibration context axis differs from the reviewed protocol"
            )
        ok = False

    # 4. AI Tutor Software Baseline Checks
    tutor_cfg = load_yaml(BASELINES_DIR / "tutor.yaml")
    tutor_sw = tutor_cfg["software"]
    tutor_eval = tutor_cfg["evaluation"]

    if tutor_sw["model"] != "Qwen2.5 0.5B Instruct":
        if verbose:
            print(
                f"[FAIL] Tutor model must be 'Qwen2.5 0.5B Instruct', got {tutor_sw['model']}"
            )
        ok = False
    if tutor_sw["quantization"] != "Q5_K_M":
        if verbose:
            print(
                f"[FAIL] Tutor quantization must be 'Q5_K_M', got {tutor_sw['quantization']}"
            )
        ok = False
    if tutor_sw["backend"] != "llama.cpp / CPU":
        if verbose:
            print(
                f"[FAIL] Tutor backend must be 'llama.cpp / CPU', got {tutor_sw['backend']}"
            )
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
            print(
                f"[FAIL] Tutor temperature must be 0.0, got {tutor_sw['temperature']}"
            )
        ok = False
    if tutor_sw["max_output_tokens"] != 384:
        if verbose:
            print(
                f"[FAIL] Tutor max_output_tokens must be 384, got {tutor_sw['max_output_tokens']}"
            )
        ok = False
    if tutor_sw["runtime_ready"] is not True:
        if verbose:
            print(
                "[FAIL] Tutor baseline runtime_ready must be True after artifact verification"
            )
        ok = False

    # Evaluation isolation guardrail
    if tutor_eval.get("reference_source") != "Team-authored 250-question assessment aligned to OpenStax topic scope":
        if verbose:
            print(
                "[FAIL] Evaluation reference source must be "
                "the final team-authored OpenStax-aligned source, got "
                f"{tutor_eval.get('reference_source')}"
            )
        ok = False
    if tutor_eval.get("reference_visible_to_model") is not False:
        if verbose:
            print(
                "[FAIL] Evaluation references must NOT be visible to model (guardrail violation)"
            )
        ok = False

    if ok and verbose:
        print("[PASS] Semantic policy and baseline checks passed")

    return ok


def run_negative_tests(master_schema: dict, verbose: bool = True) -> bool:
    """Verify that illegal values and invalid types are rejected by the master schema definitions."""
    ok = True

    # 1. Reject TimingSimpleCPU with issue_width=2 in attention experiment
    val_attn = get_validator_for_definition(master_schema, "attention_experiment")
    base_attn = load_yaml(EXAMPLES_DIR / "attention-candidate.yaml")

    bad_candidate = json.loads(json.dumps(base_attn))
    bad_candidate["hardware"]["cpu_model"] = "RiscvTimingSimpleCPU"
    bad_candidate["hardware"]["issue_width"] = 2
    errors = list(val_attn.iter_errors(bad_candidate))
    if not errors:
        if verbose:
            print(
                "[FAIL] Negative test: TimingSimpleCPU with issue_width=2 was improperly accepted"
            )
        ok = False
    elif verbose:
        print(
            "[PASS] Negative test: TimingSimpleCPU with issue_width=2 was correctly rejected"
        )

    # 2. Reject illegal hardware core count (3 cores)
    bad_candidate = json.loads(json.dumps(base_attn))
    bad_candidate["hardware"]["cores"] = 3
    errors = list(val_attn.iter_errors(bad_candidate))
    if not errors:
        if verbose:
            print("[FAIL] Negative test: cores=3 was improperly accepted")
        ok = False
    elif verbose:
        print("[PASS] Negative test: cores=3 was correctly rejected")

    # 3. Reject unknown property in attention experiment (additionalProperties: false)
    bad_candidate = json.loads(json.dumps(base_attn))
    bad_candidate["illegal_property"] = True
    errors = list(val_attn.iter_errors(bad_candidate))
    if not errors:
        if verbose:
            print(
                "[FAIL] Negative test: unknown top-level property was improperly accepted"
            )
        ok = False
    elif verbose:
        print("[PASS] Negative test: unknown top-level property was correctly rejected")

    # 4. Reject retired retrieval field in tutor_config
    val_tutor = get_validator_for_definition(master_schema, "tutor_config")
    tutor_data = load_yaml(BASELINES_DIR / "tutor.yaml")

    bad_tutor = json.loads(json.dumps(tutor_data))
    bad_tutor["software"]["chunk_unit"] = "tokens"
    errors = list(val_tutor.iter_errors(bad_tutor))
    if not errors:
        if verbose:
            print(
                "[FAIL] Negative test: retired software field was improperly accepted"
            )
        ok = False
    elif verbose:
        print("[PASS] Negative test: retired software field was correctly rejected")

    # 5. Reject reference_visible_to_model=True in evaluation guardrails
    bad_tutor = json.loads(json.dumps(tutor_data))
    bad_tutor["evaluation"]["reference_visible_to_model"] = True
    errors = list(val_tutor.iter_errors(bad_tutor))
    if not errors:
        if verbose:
            print(
                "[FAIL] Negative test: reference_visible_to_model=True was improperly accepted"
            )
        ok = False
    elif verbose:
        print(
            "[PASS] Negative test: reference_visible_to_model=True was correctly rejected"
        )

    return ok


def run_manifest_consistency_checks(verbose: bool = True) -> bool:
    """Verify agreement among the final campaign, baselines, and design spaces."""
    campaign = load_yaml(CONTRACTS / "campaigns" / "final-burst.yaml")
    tutor = load_yaml(BASELINES_DIR / "tutor.yaml")
    attention = load_yaml(BASELINES_DIR / "attention.yaml")
    hardware = load_yaml(DESIGN_SPACES_DIR / "hardware.yaml")
    shared = campaign["study"]["shared_contracts"]
    questions = load_json(ROOT / "data/questions/questions.json")
    answers = load_json(ROOT / "data/references/answer_key.json")
    answer_by_id = {item["id"]: item for item in answers["references"]}
    correct_positions = [
        question["options"].index(answer_by_id[question["id"]]["correct_answer"])
        for question in questions["questions"]
    ]
    reviewed_model_sha256 = (
        "041474553fcabfc2a2d67903f9d2c2e50bd92528e670da4f33b5d0ce6e59fd55"
    )
    ok = (
        tutor["software"]["model"] == "Qwen2.5 0.5B Instruct"
        and tutor["software"]["quantization"] == "Q5_K_M"
        and tutor["workload"]["dataset_id"] == "openstax-aligned-team-assessment-250-v1"
        and tutor["workload"]["num_questions"] == 250
        and tutor["evaluation"]["license"] == "Team-authored evaluation material; repository use authorized by contributor"
        and attention["workload"]["query_heads"] == hardware["fixed"]["query_heads"] == 14
        and attention["workload"]["kv_heads"] == hardware["fixed"]["kv_heads"] == 2
        and attention["workload"]["head_dimension"] == hardware["fixed"]["head_dimension"] == 64
        and shared["dataset"] == "data/questions/questions.json"
        and shared["dataset_reference"] == "data/references/answer_key.json"
        and campaign["runtime"]["software"]["quality_method"] == "exact_option_text_accuracy"
        and questions["dataset_id"] == answers["dataset_id"] == tutor["workload"]["dataset_id"]
        and len(questions["questions"]) == len(answers["references"]) == 250
        and len(answer_by_id) == 250
        and [correct_positions.count(index) for index in range(4)] == [63, 63, 62, 62]
        and all(
            isinstance(question["options"], list)
            and len(question["options"]) == 4
            and "correct_answer" not in question
            for question in questions["questions"]
        )
        and len(shared["objectives"]) == 4
        and "energy" in campaign["runtime"]
        and campaign["runtime"]["software"]["assets_root"] == "/opt/chia/models"
        and campaign["runtime"]["software"]["model_sha256"]
        == reviewed_model_sha256
    )
    if verbose:
        print("[PASS] Final campaign and contract agreement passed" if ok else "[FAIL] Final campaign and contract agreement failed")
    return ok


def main() -> None:
    print("=" * 60)
    print("CHIA Experiment Contracts Canonical Validator")
    print("=" * 60)

    try:
        master_schema = load_master_schema()
    except Exception as e:
        print(f"[FATAL] Master schema loading failed: {e}")
        sys.exit(1)

    cases = [
        (BASELINES_DIR / "tutor.yaml", "tutor_config"),
        (BASELINES_DIR / "attention.yaml", "attention_experiment"),
        (DESIGN_SPACES_DIR / "software.yaml", "software_design_space"),
        (DESIGN_SPACES_DIR / "hardware.yaml", "hardware_design_space"),
        (POLICIES_DIR / "compute-policy.yaml", "compute_policy"),
        (EXAMPLES_DIR / "attention-candidate.yaml", "attention_experiment"),
        (EXAMPLES_DIR / "completed-run.yaml", "run_record"),
    ]

    all_passed = True

    print("\n--- Structural YAML Schema Validation ---")
    for data_path, def_name in cases:
        if not validate_document(data_path, def_name, master_schema):
            all_passed = False

    print("\n--- Semantic & Domain Policy Checks ---")
    if not run_semantic_checks():
        all_passed = False

    print("\n--- Negative / Rejection Tests ---")
    if not run_negative_tests(master_schema):
        all_passed = False

    print("\n--- Final Campaign Agreement ---")
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
