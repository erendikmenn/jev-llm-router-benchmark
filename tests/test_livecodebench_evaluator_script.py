from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "evaluate_livecodebench_subset.py"
SPEC = importlib.util.spec_from_file_location("lcb_eval_script", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_candidate_pass_requires_every_official_test_to_pass():
    assert MODULE._candidate_passed({0: [[True, True]]}, 0)
    assert not MODULE._candidate_passed({0: [[True, False]]}, 0)
    assert not MODULE._candidate_passed({0: [[]]}, 0)
