from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "analyze_openrouter_cascade.py"
SPEC = importlib.util.spec_from_file_location("analyze_openrouter_cascade", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def generation(role: str, costs: list[float]) -> dict:
    return {
        "measurements": [
            {
                "question_id": question_id,
                "difficulty": "easy" if question_id == "a" else "hard",
                "worker_cost_usd": cost,
                "worker": {"latency_ms": latency},
            }
            for question_id, cost, latency in zip(("a", "b"), costs, (100, 200))
        ],
        "selected_role": role,
    }


def evaluation(a: bool, b: bool) -> dict:
    return {
        "official_checker": True,
        "per_task": [
            {"question_id": "a", "passed": a},
            {"question_id": "b", "passed": b},
        ],
    }


def test_analysis_uses_only_escalated_strong_cost_and_quality():
    result = MODULE.analyze(
        generation("luna", [0.01, 0.02]),
        evaluation(False, True),
        generation("sol", [0.10, 0.20]),
        evaluation(True, True),
        {
            "measurements": [
                {"question_id": "a", "escalation_score": 0.9, "jev_cost_usd": 0.001, "judgment": {"latency_ms": 10}},
                {"question_id": "b", "escalation_score": 0.1, "jev_cost_usd": 0.001, "judgment": {"latency_ms": 10}},
            ]
        },
        threshold=0.5,
    )

    assert result["quality"]["cascade"]["passed"] == 2
    assert result["routing"]["failure_recall"] == 1.0
    assert result["cost_usd"]["cascade"] == pytest.approx(0.132)
    assert result["latency"]["cascade_sequential"]["mean_ms"] == 210


def test_analysis_rejects_unpaired_inputs():
    with pytest.raises(ValueError, match="missing ids"):
        MODULE.analyze(
            {"measurements": []},
            evaluation(True, True),
            generation("sol", [0.1, 0.2]),
            evaluation(True, True),
            {"measurements": []},
            threshold=0.5,
        )


def test_analysis_supports_direct_difficulty_gates():
    result = MODULE.analyze(
        generation("luna", [0.01, 0.02]),
        evaluation(True, False),
        generation("sol", [0.10, 0.20]),
        evaluation(True, True),
        {
            "measurements": [
                {"question_id": "a", "escalation_score": 0.9, "jev_cost_usd": 0.001, "judgment": {"latency_ms": 10}},
                {"question_id": "b", "escalation_score": 0.1, "jev_cost_usd": 0.001, "judgment": {"latency_ms": 10}},
            ]
        },
        threshold=0.5,
        direct_weak_difficulties=frozenset({"easy"}),
        direct_strong_difficulties=frozenset({"hard"}),
    )

    assert result["quality"]["cascade"]["passed"] == 2
    assert result["cost_usd"]["cascade"] == pytest.approx(0.21)
    assert result["cost_usd"]["judge_all"] == 0.0
