"""Validate local YAML/JSON experiment records without executing a workload."""

import argparse
import json
from pathlib import Path
import sys

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


SCHEMA_PATH = Path(__file__).resolve().with_name("experiment.schema.json")


def unique_mapping(pairs):
    """Preserve errors that ordinary YAML/JSON parsers may silently discard."""
    result = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise ValueError("Object keys must be strings")
        if key in result:
            raise ValueError(f"Duplicate object key: {key!r}")
        result[key] = value
    return result


class StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML with explicit unique string keys; merge keys are unsupported."""


def construct_mapping(loader, node):
    return unique_mapping(
        (loader.construct_object(key, deep=True),
         loader.construct_object(value, deep=True))
        for key, value in node.value
    )


StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
)


def load_config(path):
    path = Path(path)
    raw = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(raw, object_pairs_hook=unique_mapping)
    else:
        data = yaml.load(raw, Loader=StrictSafeLoader)
    # JSON Schema operates on JSON values, not YAML dates, sets, or NaN/Infinity.
    # This also rejects circular objects; no conversion or defaults are applied.
    json.dumps(data, allow_nan=False)
    return data


def make_validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Path to an experiment YAML or JSON file")
    args = parser.parse_args(argv)
    try:
        validator = make_validator()
        config = load_config(args.config)
        errors = sorted(
            validator.iter_errors(config),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except (OSError, ValueError, TypeError, RecursionError, yaml.YAMLError, SchemaError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            location = "/" + "/".join(
                str(part).replace("~", "~0").replace("/", "~1")
                for part in error.absolute_path
            )
            print(f"INVALID {location}: {error.message}", file=sys.stderr)
        return 1
    print(f"VALID: {args.config} (schema 0.1.0; structural validation only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
