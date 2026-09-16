"""Deterministic Tutor quality scoring; references never enter model prompts."""

import json
import re
from src.common.candidate import ROOT
from src.common.errors import ConfigError
from src.common.security import within


def _normalize(value):
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def load_evaluation_set(
    questions_path="data/questions/questions.json",
    references_path="data/references/openstax.json",
):
    """Load and cross-check the public questions and evaluator-only references."""
    questions = json.loads(
        within(ROOT, questions_path, exists=True).read_text(encoding="utf-8")
    )
    references = json.loads(
        within(ROOT, references_path, exists=True).read_text(encoding="utf-8")
    )
    if (
        not isinstance(questions, dict)
        or not isinstance(references, dict)
        or questions.get("dataset_id") != references.get("dataset_id")
        or questions.get("license") != "CC BY 4.0"
        or not isinstance(questions.get("questions"), list)
        or not isinstance(references.get("references"), list)
    ):
        raise ConfigError("OpenStax evaluation artifacts are malformed or mismatched.")
    reference_by_id = {item.get("id"): item for item in references["references"]}
    if len(reference_by_id) != len(references["references"]):
        raise ConfigError("Evaluation reference IDs must be unique.")
    combined = []
    for question in questions["questions"]:
        if (
            not isinstance(question, dict)
            or not isinstance(question.get("id"), str)
            or not isinstance(question.get("question"), str)
            or question["id"] not in reference_by_id
        ):
            raise ConfigError("Every evaluation question needs one hidden reference.")
        reference = reference_by_id[question["id"]]
        groups = reference.get("required_concepts")
        if (
            not isinstance(groups, list)
            or not groups
            or any(
                not isinstance(group, list)
                or not group
                or any(not isinstance(term, str) or not term.strip() for term in group)
                for group in groups
            )
        ):
            raise ConfigError("Each reference needs nonempty required concept groups.")
        combined.append({"question": question, "reference": reference})
    if len(combined) != len(reference_by_id):
        raise ConfigError("Questions and references must have identical IDs.")
    return {
        "dataset_id": questions["dataset_id"],
        "source_url": questions["source_url"],
        "license": questions["license"],
        "items": combined,
    }


def evaluate_required_concepts(generated_answer, required_concepts):
    """Score the fraction of required concept groups matched by one answer."""
    if not isinstance(generated_answer, str) or not generated_answer.strip():
        raise ConfigError("Generated answer must be nonempty text.")
    normalized = _normalize(generated_answer)
    matched = []
    for alternatives in required_concepts:
        group_match = any(_normalize(term) in normalized for term in alternatives)
        matched.append(group_match)
    return {
        "score": sum(matched) / len(matched),
        "matched_groups": sum(matched),
        "required_groups": len(matched),
        "method": "required_concept_coverage",
        "scope": "deterministic_concept_coverage_not_human_judgment",
    }


def evaluate_answer(generated_answer, reference_answer, method):
    if method != "normalized_exact_match":
        raise ConfigError(
            "Only normalized_exact_match is implemented; semantic factual scoring needs a reviewed evaluator."
        )
    return {
        "score": float(_normalize(generated_answer) == _normalize(reference_answer)),
        "method": method,
        "scope": "exact_answer_diagnostic_not_educational_quality",
    }
