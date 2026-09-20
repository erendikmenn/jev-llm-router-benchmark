from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "materialize_swebench_pro_eval_rows.py"
SPEC = importlib.util.spec_from_file_location("pro_materializer", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_wanted_ids_rejects_duplicates():
    with pytest.raises(ValueError, match="unique"):
        MODULE.wanted_ids([{"instance_id": "x"}, {"instance_id": "x"}])


def test_wanted_ids_accepts_official_prediction_shape():
    assert MODULE.wanted_ids([{"instance_id": "x", "patch": "diff"}]) == {"x"}
