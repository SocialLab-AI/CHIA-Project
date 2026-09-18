import copy

from src.common.candidate import Candidate
from src.orchestration.policies import (
    deterministic_software_candidates,
)


def test_software_only_grid_has_exactly_nine_candidates():
    candidates = deterministic_software_candidates()

    assert len(candidates) == 9


def test_software_only_grid_matches_reviewed_values():
    candidates = deterministic_software_candidates()

    combinations = {
        (
            candidate["software"]["temperature"],
            candidate["software"]["max_output_tokens"],
        )
        for candidate in candidates
    }

    assert combinations == {
        (0.0, 128),
        (0.0, 256),
        (0.0, 384),
        (0.2, 128),
        (0.2, 256),
        (0.2, 384),
        (0.5, 128),
        (0.5, 256),
        (0.5, 384),
    }


def test_every_software_candidate_passes_canonical_validation():
    candidates = deterministic_software_candidates()

    for candidate in candidates:
        Candidate.from_dict(candidate)


def test_hardware_is_identical_across_software_only_grid():
    candidates = deterministic_software_candidates()

    expected = copy.deepcopy(candidates[0]["hardware"])

    for candidate in candidates:
        assert candidate["hardware"] == expected


def test_workload_is_identical_across_software_only_grid():
    candidates = deterministic_software_candidates()

    expected = copy.deepcopy(candidates[0]["workload"])

    for candidate in candidates:
        assert candidate["workload"] == expected


def test_only_active_software_knobs_change():
    candidates = deterministic_software_candidates()

    fixed_fields = (
        "model",
        "quantization",
        "backend",
        "cpu_threads",
        "batch_size",
    )

    first = candidates[0]["software"]

    for candidate in candidates:
        software = candidate["software"]

        for field in fixed_fields:
            assert software[field] == first[field]


def test_candidate_ids_are_unique():
    ids = {
        Candidate.from_dict(candidate).candidate_id
        for candidate in deterministic_software_candidates()
    }

    assert len(ids) == 9
