from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "fetch_livecodebench_subset.py"
SPEC = importlib.util.spec_from_file_location("lcb_fetch_script", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_dataset_revision_is_pinned_to_a_commit():
    assert len(MODULE.DEFAULT_REVISION) == 40
    assert set(MODULE.DEFAULT_REVISION) <= set("0123456789abcdef")
    assert MODULE.FILES == tuple(
        f"test{suffix}.jsonl" for suffix in ("", "2", "3", "4", "5", "6")
    )
