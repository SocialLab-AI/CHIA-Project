"""Evaluation-owned exact-answer diagnostic; reference text is never sent to inference."""

from src.common.errors import ConfigError


def evaluate_answer(generated_answer, reference_answer, method):
    if method != "normalized_exact_match":
        raise ConfigError(
            "Only normalized_exact_match is implemented; semantic factual scoring needs a reviewed evaluator."
        )
    normalize = lambda value: " ".join(value.casefold().split())
    return {
        "score": float(normalize(generated_answer) == normalize(reference_answer)),
        "method": method,
        "scope": "exact_answer_diagnostic_not_educational_quality",
    }
