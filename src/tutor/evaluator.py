"""Deterministic Tutor quality scoring; references never enter model prompts."""

import hashlib
import json
import re
import unicodedata

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


def _normalize_exact(value):
    """Normalize presentation differences while preserving mathematical symbols."""
    return " ".join(
        unicodedata.normalize("NFKC", value).casefold().split()
    )


def load_evaluation_set(
    questions_path="data/questions/questions.json",
    references_path="data/references/answer_key.json",
):
    """Load and cross-check questions and evaluator-only references.

    The question file is visible to the Tutor.

    The reference file is evaluator-only and contains the hidden material used
    by the configured deterministic quality scorer.

    The dataset must:
    - use matching dataset IDs in both files
    - provide a non-empty license/provenance string
    - contain one reference entry for every question
    - contain valid evidence for the declared evaluation method
    """

    questions_file = within(ROOT, questions_path, exists=True)
    references_file = within(ROOT, references_path, exists=True)
    questions_bytes = questions_file.read_bytes()
    references_bytes = references_file.read_bytes()
    questions = json.loads(questions_bytes.decode("utf-8"))
    references = json.loads(references_bytes.decode("utf-8"))

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

    method = references.get("method")
    if method not in {
        "required_concept_coverage",
        "exact_option_text_accuracy",
    }:
        raise ConfigError("Evaluation method is unsupported.")

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

        if method == "required_concept_coverage":
            groups = reference.get("required_concepts")
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
        else:
            options = question.get("options")
            correct_answer = reference.get("correct_answer")
            subject = question.get("subject")
            if (
                not isinstance(options, list)
                or len(options) != 4
                or any(not isinstance(option, str) or not option.strip() for option in options)
                or len({_normalize_exact(option) for option in options}) != 4
                or not isinstance(correct_answer, str)
                or not correct_answer.strip()
                or sum(
                    _normalize_exact(option) == _normalize_exact(correct_answer)
                    for option in options
                )
                != 1
                or not isinstance(subject, str)
                or not subject.strip()
            ):
                raise ConfigError(
                    "Each multiple-choice item needs four unique unlabeled options, "
                    "one exact answer and a subject."
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
        "source_description": questions.get("source_description", "unspecified"),
        "method": method,
        "questions_sha256": hashlib.sha256(questions_bytes).hexdigest(),
        "references_sha256": hashlib.sha256(references_bytes).hexdigest(),
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


def evaluate_exact_option_text(generated_answer, options, correct_answer):
    """Score one unlabeled multiple-choice response by exact option text.

    The model is asked to return one complete option. A leading ``Answer:`` is
    tolerated, but explanations, partial strings and ambiguous responses do not
    receive credit.
    """
    if not isinstance(generated_answer, str) or not generated_answer.strip():
        raise ConfigError("Generated answer must be nonempty text.")
    if (
        not isinstance(options, list)
        or len(options) != 4
        or any(not isinstance(option, str) or not option.strip() for option in options)
        or len({_normalize_exact(option) for option in options}) != 4
    ):
        raise ConfigError("Options must contain four unique nonempty strings.")
    if (
        not isinstance(correct_answer, str)
        or sum(
            _normalize_exact(option) == _normalize_exact(correct_answer)
            for option in options
        )
        != 1
    ):
        raise ConfigError("Correct answer must match exactly one option.")

    response = generated_answer.strip()
    response = re.sub(r"^answer\s*:\s*", "", response, flags=re.IGNORECASE)
    response = response.strip().strip('"').strip("'")
    normalized_response = _normalize_exact(response)
    matches = [
        (index, option)
        for index, option in enumerate(options)
        if _normalize_exact(option) == normalized_response
    ]
    selected_position = matches[0][0] + 1 if len(matches) == 1 else None
    selected_answer = matches[0][1] if len(matches) == 1 else None
    correct = (
        len(matches) == 1
        and _normalize_exact(selected_answer) == _normalize_exact(correct_answer)
    )
    return {
        "score": float(correct),
        "selected_answer": selected_answer,
        "selected_position": selected_position,
        "parse_status": "matched_option" if len(matches) == 1 else "invalid_response",
        "method": "exact_option_text_accuracy",
        "scope": "deterministic_multiple_choice_accuracy",
    }
