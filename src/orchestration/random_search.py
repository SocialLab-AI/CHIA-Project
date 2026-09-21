"""Seeded random proposer over the same reviewed space as Gemini."""

import itertools
import random

from src.common.candidate import Candidate, baseline_candidate
from src.orchestration.gemini_api import _active_spaces


class RandomProposer:
    def __init__(self, seed=20260921):
        self.seed = seed
        hardware, software = _active_spaces()
        keys = [("hardware", k, v) for k, v in hardware.items()] + [
            ("software", k, v) for k, v in software.items()
        ]
        self._keys = keys
        self._choices = list(itertools.product(*(item[2] for item in keys)))
        random.Random(seed).shuffle(self._choices)
        self._index = 0

    def propose(self, history, seen):
        while self._index < len(self._choices):
            values = self._choices[self._index]
            self._index += 1
            candidate = baseline_candidate()
            for (section, name, _), value in zip(self._keys, values):
                candidate[section][name] = value
            try:
                snapshot = Candidate.from_dict(candidate)
            except Exception:
                continue
            candidate_id = snapshot.candidate_id
            if candidate_id not in seen:
                return snapshot.config, {"seed": self.seed, "request_count": 0}
        raise RuntimeError("Random design space exhausted.")
