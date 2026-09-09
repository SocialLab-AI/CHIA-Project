#!/usr/bin/env python3
from pathlib import Path
import json, sys
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def validate(instance_path, schema_path):
    schema = load_json(schema_path)
    instance = load_yaml(instance_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if errors:
        print(f"FAIL {instance_path.name}")
        for e in errors:
            where = ".".join(str(x) for x in e.absolute_path) or "<root>"
            print(f"  {where}: {e.message}")
        return False
    print(f"PASS {instance_path.name}")
    return True

def semantic_policy_checks(policy):
    ok = True
    total = policy["gemini"]["total_budget_usd"]
    reserve = policy["gemini"]["reserve_usd"]
    tier_sum = sum(t["gemini_budget_usd"] for t in policy["tiers"].values())
    if tier_sum + reserve > total:
        print(f"FAIL semantic policy: tier budgets ({tier_sum}) + reserve ({reserve}) exceed total ({total})")
        ok = False
    final = policy["tiers"]["final"]
    for name, tier in policy["tiers"].items():
        if name != "final" and tier["organizer_burst_allowed"]:
            print(f"FAIL semantic policy: {name} unexpectedly allows organizer burst")
            ok = False
    if not final["organizer_burst_allowed"] or "organizer_burst" not in final["allowed_backends"]:
        print("FAIL semantic policy: final tier must allow organizer_burst")
        ok = False
    if ok:
        print("PASS semantic policy checks")
    return ok

ok = True
ok &= validate(ROOT/'examples'/'experiment.dev.yaml', ROOT/'schemas'/'experiment.schema.json')
ok &= validate(ROOT/'examples'/'experiment.pilot.yaml', ROOT/'schemas'/'experiment.schema.json')
ok &= validate(ROOT/'examples'/'run-record.completed.yaml', ROOT/'schemas'/'run-record.schema.json')
ok &= validate(ROOT/'configs'/'compute-policy.yaml', ROOT/'schemas'/'compute-policy.schema.json')
ok &= semantic_policy_checks(load_yaml(ROOT/'configs'/'compute-policy.yaml'))
sys.exit(0 if ok else 1)
