from __future__ import annotations

from jev_router.config import load_config
from jev_router.judge_models import ReviewJudgment, ReviewPacket
from jev_router.judge_service import estimate_review_cost, run_review
from jev_router.models import Usage
from jev_router.providers.base import ProviderError


def packet():
    return ReviewPacket(
        id="case",
        task="Fix normalization.",
        acceptance_criteria=("Normalize all paths.",),
        diff="+return email.casefold()",
    )


class PassingJudge:
    def judge(self, packet):
        return ReviewJudgment(
            signals={
                "requirements_complete": 0.95,
                "scope_aligned": 0.95,
                "behavior_supported": 0.90,
                "regression_risk": 0.10,
                "self_test_bias": 0.10,
                "needs_deep_review": 0.10,
                "policy_violation": 0.0,
            },
            risk_level="low",
            risk_probabilities={"low": 1.0},
            risk_confidence=1.0,
            usage=Usage(1000, 0, 100),
            latency_ms=80,
            model_id="jev-test",
            provider_cost_usd=0.000042,
        )


class BrokenJudge:
    def judge(self, packet):
        raise ProviderError("timeout_or_network", "timeout")


def test_run_review_returns_policy_decision_and_provider_cost():
    result = run_review(packet(), PassingJudge(), load_config("configs/default.toml"))
    assert result.decision.action == "accept"
    assert result.cost_usd == 0.000042
    assert result.cost_source == "provider_reported"


def test_run_review_fails_safe_to_escalation():
    result = run_review(packet(), BrokenJudge(), load_config("configs/default.toml"))
    assert result.decision.action == "escalate"
    assert result.provider_error == "timeout_or_network"


def test_review_cost_estimate_is_positive_and_small():
    cost = estimate_review_cost(packet(), load_config("configs/default.toml"))
    assert 0 < cost < 0.01
