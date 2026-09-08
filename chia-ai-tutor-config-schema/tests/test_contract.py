"""Contract regressions: reject ambiguous input and unusable result records."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validate_config import load_config, make_validator  # noqa: E402


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = make_validator()
        cls.example = load_config(ROOT / "example-experiment.yaml")

    def test_example_and_optional_batch(self):
        self.validator.validate(self.example)
        config = deepcopy(self.example)
        del config["software"]["batch_size"]
        self.validator.validate(config)
        self.assertNotIn("batch_size", config["software"])

    def test_reject_wrong_version_unknown_knobs_and_bad_values(self):
        cases = [
            ("schema_version", "0.2.0"),
            ("software.quantization", "fp32"),
            ("software.retrieval_top_k", 0),
            ("software.max_new_tokens", 1025),
            ("software.batch_size", 9),
            ("software.model", "   "),
            ("hardware.l1_cache_kb", 48),
            ("hardware.l2_cache_kb", 0),
            ("hardware.cores", True),
            ("hardware.cores", 9),
            ("hardware.issue_width", "2"),
            ("hardware.frequency_ghz", 2),
            ("workload.seed", -1),
            ("workload.num_questions", 0),
            ("metrics.answer_quality", 83),
            ("metrics.latency_ms", -1),
            ("status.state", "done"),
        ]
        for dotted, value in cases:
            with self.subTest(field=dotted, value=value):
                config = deepcopy(self.example)
                parts = dotted.split(".")
                parent = config
                for part in parts[:-1]:
                    parent = parent[part]
                parent[parts[-1]] = value
                self.assertFalse(self.validator.is_valid(config))

    def test_required_sections_and_metric_keys(self):
        for section in self.example:
            config = deepcopy(self.example)
            del config[section]
            self.assertFalse(self.validator.is_valid(config), section)
        for metric in self.example["metrics"]:
            config = deepcopy(self.example)
            del config["metrics"][metric]
            self.assertFalse(self.validator.is_valid(config), metric)

    def test_planned_cannot_contain_measured_results(self):
        config = deepcopy(self.example)
        config["metrics"]["latency_ms"] = 0
        self.assertFalse(self.validator.is_valid(config))

    def test_completed_needs_evidence_and_some_measurement(self):
        config = deepcopy(self.example)
        config["status"] = {"state": "completed", "message": "Only quality available."}
        self.assertFalse(self.validator.is_valid(config))
        config["metadata"]["artifact_manifest"] = "artifacts/run.json"
        self.assertFalse(self.validator.is_valid(config))
        config["metrics"]["answer_quality"] = 0.83
        self.validator.validate(config)
        for quality in (0, 1):
            config["metrics"]["answer_quality"] = quality
            self.validator.validate(config)
        for metric in config["metrics"]:
            config["metrics"][metric] = 0
        self.validator.validate(config)

    def test_failure_requires_reason_and_can_keep_partial_metrics(self):
        config = deepcopy(self.example)
        config["status"] = {"state": "failed", "message": None}
        self.assertFalse(self.validator.is_valid(config))
        config["status"]["message"] = "Simulation failed after software evaluation."
        config["metrics"]["answer_quality"] = 0.8
        self.validator.validate(config)

    def test_loader_rejects_ambiguous_or_non_json_data(self):
        invalid = [
            (".yaml", "software:\n  quantization: int4\n  quantization: int8\n"),
            (".yaml", "1: value\n"),
            (".yaml", "value: .nan\n"),
            (".yaml", "value: .inf\n"),
            (".yaml", "value: 2026-09-08\n"),
            (".json", '{"value": 1, "value": 2}'),
            (".json", '{"value": NaN}'),
            (".json", '{"value": 1e999}'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for suffix, raw in invalid:
                with self.subTest(raw=raw):
                    path = Path(directory) / ("config" + suffix)
                    path.write_text(raw, encoding="utf-8")
                    with self.assertRaises((ValueError, TypeError)):
                        load_config(path)

    def test_cli_exit_codes_and_other_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.yaml"
            invalid.write_text("schema_version: wrong\n", encoding="utf-8")
            for path, code in [
                (ROOT / "example-experiment.yaml", 0),
                (invalid, 1),
                (Path(directory) / "missing.yaml", 2),
            ]:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "validate_config.py"), str(path)],
                    cwd=directory, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, code, result.stderr)


if __name__ == "__main__":
    unittest.main()
