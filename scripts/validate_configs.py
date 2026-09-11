from pathlib import Path
import json

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "configs" / "schemas"
EXAMPLES = ROOT / "configs" / "examples"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    schema_files = {
        "software.schema.json": load(SCHEMAS / "software.schema.json"),
        "hardware.schema.json": load(SCHEMAS / "hardware.schema.json"),
        "experiment.schema.json": load(SCHEMAS / "experiment.schema.json"),
        "run_record.schema.json": load(SCHEMAS / "run_record.schema.json"),
    }

    registry = Registry()
    for name, schema in schema_files.items():
        registry = registry.with_resource(name, Resource.from_contents(schema))

    validator = Draft202012Validator(
        schema_files["experiment.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )

    failed = False
    for example_path in sorted(EXAMPLES.glob("*.json")):
        instance = load(example_path)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
        if errors:
            failed = True
            print(f"[FAIL] {example_path.name}")
            for error in errors:
                location = ".".join(str(x) for x in error.path) or "<root>"
                print(f"  {location}: {error.message}")
        else:
            print(f"[OK]   {example_path.name}")

    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
