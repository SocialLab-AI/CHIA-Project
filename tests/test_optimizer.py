"""Orchestration policy tests; legacy SDK proposal code is not the default execution path."""

import pytest
from src.orchestration.chia import chia_entrypoint
from src.orchestration.nodes.optimizer import _parse_json_response


def test_legacy_parser_retained():
    assert _parse_json_response('{"hardware":{"issue_width":2}}') == {"issue_width": 2}


def test_iterations_rejected_before_execution():
    with pytest.raises(ValueError):
        chia_entrypoint({"iterations": 0})


def test_unknown_backend_rejected_before_execution():
    with pytest.raises(ValueError):
        chia_entrypoint({"backend": "unapproved"})
