"""Deterministic Tutor quality scoring; references never enter model prompts."""

import json
import re

from src.common.candidate import ROOT
from src.common.errors import ConfigError
from src.common.security import within


def _normalize(value):
    """Normalize text for deterministic lexical concept matching."""
    return " ".join(
        re.findall(
            r"[a-z0-9]+",
            value.casefold(),
        )
    )


def load_evaluation_set(
    questions_path="data/questions/questions.json",
    references_path="data/references/openstax.json",
):
    """Load and cross-check questions and evaluator-only references.

    The question file is visible to the Tutor.

    The reference file is evaluator-only and contains the hidden
    required-concept groups used for deterministic quality scoring.

    The dataset must:
    - use matching dataset IDs in both files
    - provide a non-empty license/provenance string
    - contain one reference entry for every question
    - contain non-empty required-concept groups
    """

    questions = json.loads(
        within(
            ROOT,
            questions_path,
            exists=True,
        ).read_text(
            encoding="utf-8"
        )
    )

    references = json.loads(
        within(
            ROOT,
            references_path,
            exists=True,
        ).read_text(
            encoding="utf-8"
        )
    )

    if (
        not isinstance(questions, dict)
        or not isinstance(references, dict)
        or questions.get("dataset_id")
        != references.get("dataset_id")
        or not isinstance(
            questions.get("license"),
            str,
        )
        or not questions["license"].strip()
        or not isinstance(
            questions.get("questions"),
            list,
        )
        or not isinstance(
            references.get("references"),
            list,
        )
    ):
        raise ConfigError(
            "Evaluation artifacts are malformed or mismatched."
        )

    reference_by_id = {
        item.get("id"): item
        for item in references["references"]
    }

    if (
        len(reference_by_id)
        != len(references["references"])
    ):
        raise ConfigError(
            "Evaluation reference IDs must be unique."
        )

    combined = []

    for question in questions["questions"]:
        if (
            not isinstance(question, dict)
            or not isinstance(
                question.get("id"),
                str,
            )
            or not question["id"].strip()
            or not isinstance(
                question.get("question"),
                str,
            )
            or not question["question"].strip()
            or question["id"]
            not in reference_by_id
        ):
            raise ConfigError(
                "Every evaluation question needs one hidden reference."
            )

        reference = reference_by_id[
            question["id"]
        ]

        groups = reference.get(
            "required_concepts"
        )

        if (
            not isinstance(groups, list)
            or not groups
            or any(
                not isinstance(group, list)
                or not group
                or any(
                    not isinstance(term, str)
                    or not term.strip()
                    for term in group
                )
                for group in groups
            )
        ):
            raise ConfigError(
                "Each reference needs nonempty required concept groups."
            )

        combined.append(
            {
                "question": question,
                "reference": reference,
            }
        )

    if (
        len(combined)
        != len(reference_by_id)
    ):
        raise ConfigError(
            "Questions and references must have identical IDs."
        )

    source_url = questions.get(
        "source_url",
        "unspecified",
    )

    if not isinstance(source_url, str):
        raise ConfigError(
            "Evaluation source_url must be a string."
        )

    return {
        "dataset_id": questions[
            "dataset_id"
        ],
        "source_url": source_url,
        "license": questions[
            "license"
        ],
        "items": combined,
    }


def evaluate_required_concepts(
    generated_answer,
    required_concepts,
):
    """Score the fraction of required concept groups matched by one answer.

    A concept group may contain multiple acceptable lexical alternatives.

    Example:
        [
            ["gravity", "gravitational force"],
            ["mass"],
            ["earth attracts", "attracted toward earth"],
        ]

    Matching any term in one group counts that concept group as covered.
    """

    if (
        not isinstance(
            generated_answer,
            str,
        )
        or not generated_answer.strip()
    ):
        raise ConfigError(
            "Generated answer must be nonempty text."
        )

    if (
        not isinstance(
            required_concepts,
            list,
        )
        or not required_concepts
    ):
        raise ConfigError(
            "Required concepts must be a nonempty list."
        )

    normalized = _normalize(
        generated_answer
    )

    matched = []

    for alternatives in required_concepts:
        if (
            not isinstance(
                alternatives,
                list,
            )
            or not alternatives
        ):
            raise ConfigError(
                "Each required concept group must be nonempty."
            )

        padded_answer = f" {normalized} "
        group_match = any(
            f" {_normalize(term)} " in padded_answer
            for term in alternatives
        )

        matched.append(
            group_match
        )

    return {
        "score": (
            sum(matched)
            / len(matched)
        ),
        "matched_groups": sum(
            matched
        ),
        "required_groups": len(
            matched
        ),
        "method": (
            "required_concept_coverage"
        ),
        "scope": (
            "deterministic_concept_coverage_not_human_judgment"
        ),
    }


def evaluate_answer(
    generated_answer,
    reference_answer,
    method,
):
    """Optional diagnostic exact-answer evaluator.

    This is separate from the primary required-concept coverage metric.
    """

    if (
        method
        != "normalized_exact_match"
    ):
        raise ConfigError(
            "Only normalized_exact_match is implemented; "
            "semantic factual scoring needs a reviewed evaluator."
        )

    if (
        not isinstance(
            generated_answer,
            str,
        )
        or not generated_answer.strip()
    ):
        raise ConfigError(
            "Generated answer must be nonempty text."
        )

    if (
        not isinstance(
            reference_answer,
            str,
        )
        or not reference_answer.strip()
    ):
        raise ConfigError(
            "Reference answer must be nonempty text."
        )

    return {
        "score": float(
            _normalize(
                generated_answer
            )
            == _normalize(
                reference_answer
            )
        ),
        "method": method,
        "scope": (
            "exact_answer_diagnostic_not_educational_quality"
        ),
    }
