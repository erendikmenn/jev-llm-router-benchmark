from __future__ import annotations

import pytest

from jev_router.config import load_config
from jev_router.control import run_control
from jev_router.judge_models import ReviewJudgment, ReviewPacket
from jev_router.models import JevJudgment, Task, Usage


class RouteCheap:
    def judge(self, task):
        return JevJudgment(
            selected="cheap",
            strong_probability=0.2,
            confidence=0.8,
            task_type="coding",
            probabilities={"cheap": 0.8, "strong": 0.2},
            usage=Usage(100, 0, 20),
            latency_ms=50,
            model_id="jev-route",
            provider_cost_usd=0.00001,
        )


class ReviewEscalate:
    def judge(self, packet):
        return ReviewJudgment(
            signals={
                "requirements_complete": 0.8,
                "scope_aligned": 0.9,
                "behavior_supported": 0.6,
                "regression_risk": 0.4,
                "self_test_bias": 0.5,
                "needs_deep_review": 0.9,
                "policy_violation": 0.0,
            },
            risk_level="medium",
            risk_probabilities={"low": 0.2, "medium": 0.8},
            risk_confidence=0.7,
            usage=Usage(200, 0, 30),
            latency_ms=75,
            model_id="jev-review",
            provider_cost_usd=0.00002,
        )


def task():
    return Task(
        id="task",
        split="adhoc",
        language="en",
        group="coding",
        prompt="Fix the bug.",
        metric="contains_all",
        expected=[],
        constraints={"modality": "text", "requires_tools": False},
        fixture={},
        jev_fixture={},
    )


def packet():
    return ReviewPacket(
        id="packet",
        task="Fix the bug.",
        acceptance_criteria=("Preserve callers.",),
        diff="+fix",
    )


def test_control_escalates_cheap_worker_to_strong():
    result = run_control(
        task(),
        packet(),
        RouteCheap(),
        ReviewEscalate(),
        load_config("configs/default.toml"),
        0.58,
    )
    assert result.route.selected == "cheap"
    assert result.next_step == "escalate_to_strong"
    assert result.recommended_role == "strong"
    assert result.total_control_cost_usd == pytest.approx(0.00003)
