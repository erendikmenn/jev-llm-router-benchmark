from __future__ import annotations

import pytest

from jev_router.config import load_config
from jev_router.judge_models import ReviewJudgment, ReviewPacket
from jev_router.judge_policy import decide_review
from jev_router.models import Usage


@pytest.fixture()
def config():
    return load_config("configs/default.toml")


def packet(*risk_flags: str) -> ReviewPacket:
    return ReviewPacket(
        id="case",
        task="Implement case-insensitive email lookup.",
        acceptance_criteria=("All lookup paths normalize email addresses.",),
        diff="diff --git a/users.py b/users.py",
        risk_flags=tuple(risk_flags),
    )


def judgment(**overrides) -> ReviewJudgment:
    signals = {
        "requirements_complete": 0.95,
        "scope_aligned": 0.95,
        "behavior_supported": 0.90,
        "regression_risk": 0.10,
        "self_test_bias": 0.10,
        "needs_deep_review": 0.10,
        "policy_violation": 0.05,
    }
    signals.update(overrides.pop("signals", {}))
    return ReviewJudgment(
        signals=signals,
        risk_level=overrides.pop("risk_level", "low"),
        risk_probabilities={"low": 0.9, "medium": 0.1, "high": 0.0, "critical": 0.0},
        risk_confidence=overrides.pop("risk_confidence", 0.9),
        usage=Usage(100, 0, 20),
        latency_ms=100,
        model_id="jev-test",
        **overrides,
    )


def test_accepts_low_risk_complete_change(config):
    decision = decide_review(packet(), judgment(), config)
    assert decision.action == "accept"
    assert decision.fired_rules == ("all_acceptance_gates_passed",)


def test_revises_incomplete_change(config):
    decision = decide_review(
        packet(),
        judgment(signals={"requirements_complete": 0.20}),
        config,
    )
    assert decision.action == "revise"
    assert "clearly_incomplete_requirements" in decision.fired_rules


def test_escalates_high_stakes_change_even_when_signals_pass(config):
    decision = decide_review(packet("authentication"), judgment(), config)
    assert decision.action == "escalate"
    assert "high_stakes_static_risk_flag" in decision.fired_rules


def test_blocks_destructive_change(config):
    decision = decide_review(packet("destructive"), judgment(), config)
    assert decision.action == "block"
    assert "critical_static_risk_flag" in decision.fired_rules


def test_uncertainty_routes_to_deep_review(config):
    decision = decide_review(
        packet(),
        judgment(signals={"regression_risk": 0.50, "self_test_bias": 0.50}),
        config,
    )
    assert decision.action == "escalate"
    assert "multiple_semantic_signals_uncertain" in decision.fired_rules


def test_clear_low_risk_failure_revises_before_optional_deep_review(config):
    decision = decide_review(
        packet(),
        judgment(
            signals={
                "requirements_complete": 0.20,
                "needs_deep_review": 0.90,
            }
        ),
        config,
    )
    assert decision.action == "revise"
    assert "clearly_incomplete_requirements" in decision.fired_rules


def test_low_confidence_low_risk_change_can_still_pass(config):
    decision = decide_review(packet(), judgment(risk_confidence=0.20), config)
    assert decision.action == "accept"
