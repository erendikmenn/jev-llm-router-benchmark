from __future__ import annotations

from jev_router.config import load_config
from jev_router.judge_models import ReviewJudgment, ReviewPacket
from jev_router.judge_service import run_review_bundle
from jev_router.models import Usage


class SequenceJudge:
    def __init__(self):
        self.index = 0

    def judge(self, packet):
        complete = 0.95 if self.index == 0 else 0.2
        self.index += 1
        return ReviewJudgment(
            signals={
                "requirements_complete": complete,
                "scope_aligned": 0.95,
                "behavior_supported": 0.95,
                "regression_risk": 0.05,
                "self_test_bias": 0.05,
                "needs_deep_review": 0.05,
                "policy_violation": 0.01,
            },
            risk_level="low",
            risk_probabilities={"low": 1.0},
            risk_confidence=1.0,
            usage=Usage(100, 0, 10),
            latency_ms=3,
            model_id="fixture",
            provider_cost_usd=0.001,
        )


def test_bundle_uses_most_conservative_chunk_decision():
    packets = tuple(
        ReviewPacket(str(index), "task", ("done",), f"diff {index}")
        for index in range(2)
    )
    bundle = run_review_bundle(packets, SequenceJudge(), load_config("configs/default.toml"))

    assert bundle.decision.action == "revise"
    assert bundle.cost_usd == 0.002
    assert bundle.latency_ms == 6
    assert any(rule.startswith("chunk_2:") for rule in bundle.decision.fired_rules)
