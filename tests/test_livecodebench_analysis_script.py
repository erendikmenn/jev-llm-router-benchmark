from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "analyze_livecodebench_evaluation.py"
SPEC = importlib.util.spec_from_file_location("analyze_livecodebench_evaluation", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_analysis_joins_official_results_and_reports_guardrails():
    generation = {
        "measurements": [
            {
                "question_id": "easy",
                "difficulty": "easy",
                "selected_role": "luna",
                "status": "completed",
                "code": "print(1)",
                "route": {"rule": "jev"},
                "route_latency_ms": 10,
                "execution_elapsed_ms": 100,
                "jev_route_cost_usd": 0.001,
                "codex_usage": {"input_tokens": 10, "output_tokens": 2},
            },
            {
                "question_id": "hard",
                "difficulty": "hard",
                "selected_role": "sol",
                "status": "completed",
                "code": "print(2)",
                "route": {"rule": "guard"},
                "route_latency_ms": 30,
                "execution_elapsed_ms": 300,
                "jev_route_cost_usd": 0.002,
                "codex_usage": {"input_tokens": 20, "output_tokens": 4},
            },
        ]
    }
    evaluation = {
        "official_checker": True,
        "per_task": [
            {"question_id": "easy", "passed": False},
            {"question_id": "hard", "passed": True},
        ],
    }

    result = MODULE.analyze(generation, evaluation)

    assert result["pass_at_1"] == 0.5
    assert result["selected_role_counts"] == {"luna": 1, "sol": 1}
    assert result["codex_tokens"]["input_tokens"] == 30
    assert result["latency_ms"]["execution_p50"] == 200
    assert result["jev_route_cost_usd"] == pytest.approx(0.003)
    assert result["interpretation_guardrails"]["luna_failures_are_underroute_candidates_not_proof"] == ["easy"]


def test_analysis_rejects_unknown_evaluation_ids():
    with pytest.raises(ValueError, match="unknown"):
        MODULE.analyze(
            {"measurements": []},
            {"per_task": [{"question_id": "missing", "passed": False}]},
        )
