from __future__ import annotations

from .config import AppConfig
from .judge_models import ReviewDecision, ReviewJudgment, ReviewPacket


CRITICAL_FLAGS = frozenset(
    {
        "destructive",
        "secret_exposure",
        "policy_bypass",
    }
)

HIGH_STAKES_FLAGS = frozenset(
    {
        "authentication",
        "authorization",
        "payment",
        "data_isolation",
        "database_migration",
        "security_boundary",
    }
)


def decide_review(
    packet: ReviewPacket,
    judgment: ReviewJudgment,
    config: AppConfig,
) -> ReviewDecision:
    """Compose semantic signals with explicit, risk-aware control policy."""

    policy = config.judge
    signals = judgment.signals
    fired: list[str] = []
    uncertainty_band = float(policy["uncertainty_band"])
    uncertain = tuple(
        sorted(
            name
            for name, probability in signals.items()
            if abs(probability - 0.5) <= uncertainty_band
        )
    )
    flags = set(packet.risk_flags)

    if flags & CRITICAL_FLAGS:
        fired.append("critical_static_risk_flag")
    if signals.get("policy_violation", 0.0) >= float(policy["policy_violation_block"]):
        fired.append("semantic_policy_violation")
    if judgment.risk_level == "critical":
        fired.append("critical_semantic_risk")
    if fired:
        return ReviewDecision(
            action="block",
            fired_rules=tuple(fired),
            signals=signals,
            risk_level=judgment.risk_level,
            risk_confidence=judgment.risk_confidence,
            uncertain_signals=uncertain,
            judgment=judgment,
        )

    if flags & HIGH_STAKES_FLAGS:
        fired.append("high_stakes_static_risk_flag")
    if judgment.risk_level == "high":
        fired.append("high_semantic_risk")
    if signals.get("needs_deep_review", 0.0) >= float(policy["deep_review_escalate"]):
        fired.append("deep_review_requested")
    if judgment.risk_confidence < float(policy["risk_confidence_min"]):
        fired.append("risk_classification_uncertain")
    if len(uncertain) >= int(policy["max_uncertain_signals"]):
        fired.append("multiple_semantic_signals_uncertain")
    if fired:
        return ReviewDecision(
            action="escalate",
            fired_rules=tuple(fired),
            signals=signals,
            risk_level=judgment.risk_level,
            risk_confidence=judgment.risk_confidence,
            uncertain_signals=uncertain,
            judgment=judgment,
        )

    if signals.get("requirements_complete", 0.0) < float(policy["requirements_min"]):
        fired.append("requirements_incomplete")
    if signals.get("scope_aligned", 0.0) < float(policy["scope_min"]):
        fired.append("scope_misaligned")
    if signals.get("behavior_supported", 0.0) < float(policy["behavior_support_min"]):
        fired.append("behavior_not_supported")
    if signals.get("regression_risk", 1.0) >= float(policy["regression_revise"]):
        fired.append("regression_risk")
    if signals.get("self_test_bias", 1.0) >= float(policy["self_test_bias_revise"]):
        fired.append("self_test_bias")
    if fired:
        return ReviewDecision(
            action="revise",
            fired_rules=tuple(fired),
            signals=signals,
            risk_level=judgment.risk_level,
            risk_confidence=judgment.risk_confidence,
            uncertain_signals=uncertain,
            judgment=judgment,
        )

    return ReviewDecision(
        action="accept",
        fired_rules=("all_acceptance_gates_passed",),
        signals=signals,
        risk_level=judgment.risk_level,
        risk_confidence=judgment.risk_confidence,
        uncertain_signals=uncertain,
        judgment=judgment,
    )
