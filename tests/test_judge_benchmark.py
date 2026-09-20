from __future__ import annotations

import json

from jev_router.config import load_config
from jev_router.judge_benchmark import run_judge_benchmark
from jev_router.judge_dataset import load_judge_cases
from jev_router.providers.fixture import FixtureReviewJudge


def test_synthetic_judge_dataset_is_balanced_and_split():
    cases = load_judge_cases("data/code_judge_synthetic_v1.jsonl")
    assert len(cases) == 40
    assert sum(case.split == "dev" for case in cases) == 12
    assert sum(case.split == "test" for case in cases) == 28
    for action in ("accept", "revise", "escalate", "block"):
        assert sum(case.expected_action == action for case in cases) == 10


def test_fixture_judge_benchmark_exercises_policy_without_false_passes(tmp_path):
    config = load_config("configs/default.toml")
    cases = load_judge_cases("data/code_judge_synthetic_v1.jsonl")
    rows, summary = run_judge_benchmark(
        cases,
        FixtureReviewJudge(config, cases),
        config,
        tmp_path,
        mode="fixture",
        max_budget_usd=None,
    )
    assert len(rows) == 40
    assert summary["accuracy"] == 1.0
    assert summary["unsafe_false_passes"] == 0
    assert json.loads((tmp_path / "summary.json").read_text())["cases"] == 40
