from __future__ import annotations

import pytest

from jev_router.solution_verifier import (
    choose_escalation_threshold,
    evaluate_paired_cascade,
    solution_escalation_score,
)


def evaluation(labels: dict[str, bool]) -> dict:
    return {
        "per_task": [
            {"question_id": question_id, "passed": passed}
            for question_id, passed in labels.items()
        ]
    }


def test_escalation_score_is_conservative_maximum():
    score = solution_escalation_score(
        {
            "fully_correct": 0.8,
            "edge_case_failure": 0.3,
            "complexity_failure": 0.1,
            "needs_stronger_model": 0.7,
        }
    )
    assert score == pytest.approx(0.7)


def test_threshold_calibration_targets_failure_recall_with_minimum_escalation():
    judgments = [
        {"question_id": "a", "source_role": "luna", "escalation_score": 0.9},
        {"question_id": "b", "source_role": "luna", "escalation_score": 0.8},
        {"question_id": "c", "source_role": "luna", "escalation_score": 0.7},
        {"question_id": "d", "source_role": "luna", "escalation_score": 0.1},
    ]
    result = choose_escalation_threshold(
        judgments,
        evaluation({"a": False, "b": False, "c": True, "d": True}),
        minimum_failure_recall=1.0,
    )
    assert result["chosen"]["threshold"] == pytest.approx(0.8)
    assert result["chosen"]["escalation_rate"] == pytest.approx(0.5)


def test_paired_cascade_can_capture_model_complementarity():
    judgments = [
        {"question_id": "a", "escalation_score": 0.9},
        {"question_id": "b", "escalation_score": 0.1},
        {"question_id": "c", "escalation_score": 0.2},
    ]
    result = evaluate_paired_cascade(
        judgments,
        evaluation({"a": False, "b": True, "c": True}),
        evaluation({"a": True, "b": True, "c": False}),
        threshold=0.8,
    )
    assert result["weak_passed"] == 2
    assert result["strong_passed"] == 2
    assert result["cascade_passed"] == 3
    assert result["strong_calls"] == 1
