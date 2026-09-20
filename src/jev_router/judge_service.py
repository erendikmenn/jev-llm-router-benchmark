from __future__ import annotations

import json
from dataclasses import dataclass

from .config import AppConfig
from .judge_models import ReviewDecision, ReviewPacket
from .judge_policy import decide_review
from .pricing import estimate_tokens, jev_cost
from .providers.base import ProviderError, ReviewJudgeProvider


_ACTION_SEVERITY = {"accept": 0, "revise": 1, "escalate": 2, "block": 3}


@dataclass(frozen=True)
class ReviewRun:
    decision: ReviewDecision
    cost_usd: float
    cost_source: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    provider_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.to_dict(),
            "cost_usd": self.cost_usd,
            "cost_source": self.cost_source,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "provider_error": self.provider_error,
        }


@dataclass(frozen=True)
class ReviewBundle:
    decision: ReviewDecision
    runs: tuple[ReviewRun, ...]
    cost_usd: float
    latency_ms: float
    provider_errors: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.to_dict(),
            "chunks": [run.to_dict() for run in self.runs],
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "provider_errors": self.provider_errors,
        }


def estimate_review_cost(packet: ReviewPacket, config: AppConfig) -> float:
    payload = json.dumps(packet.to_state(), ensure_ascii=False, sort_keys=True)
    estimated_input = estimate_tokens(payload) + 900
    return estimated_input * float(config.jev_price["input_usd_per_million"]) / 1_000_000


def run_review(
    packet: ReviewPacket,
    provider: ReviewJudgeProvider,
    config: AppConfig,
) -> ReviewRun:
    try:
        judgment = provider.judge(packet)
    except ProviderError as exc:
        decision = ReviewDecision(
            action="escalate",
            fired_rules=(f"judge_error:{exc.kind}",),
            signals={},
            risk_level="high",
            risk_confidence=0.0,
        )
        return ReviewRun(
            decision=decision,
            cost_usd=0.0,
            cost_source="unknown_after_provider_error",
            latency_ms=sum(attempt.latency_ms for attempt in exc.attempts),
            input_tokens=sum(attempt.usage.input_tokens for attempt in exc.attempts),
            output_tokens=sum(attempt.usage.output_tokens for attempt in exc.attempts),
            provider_error=exc.kind,
        )

    if judgment.provider_cost_usd is not None:
        cost = judgment.provider_cost_usd
        source = "provider_reported"
    else:
        cost = jev_cost(judgment.usage, config)
        source = "calculated_from_usage"
    return ReviewRun(
        decision=decide_review(packet, judgment, config),
        cost_usd=cost,
        cost_source=source,
        latency_ms=judgment.latency_ms,
        input_tokens=judgment.usage.input_tokens,
        output_tokens=judgment.usage.output_tokens,
    )


def run_review_bundle(
    packets: tuple[ReviewPacket, ...],
    provider: ReviewJudgeProvider,
    config: AppConfig,
) -> ReviewBundle:
    if not packets:
        raise ValueError("review bundle requires at least one packet")
    runs = tuple(run_review(packet, provider, config) for packet in packets)
    worst = max(runs, key=lambda run: _ACTION_SEVERITY[run.decision.action])
    fired_rules = tuple(
        f"chunk_{index + 1}:{rule}"
        for index, run in enumerate(runs)
        for rule in run.decision.fired_rules
        if run.decision.action != "accept" or len(runs) == 1
    )
    decision = ReviewDecision(
        action=worst.decision.action,
        fired_rules=fired_rules or worst.decision.fired_rules,
        signals=worst.decision.signals,
        risk_level=worst.decision.risk_level,
        risk_confidence=worst.decision.risk_confidence,
        uncertain_signals=worst.decision.uncertain_signals,
        judgment=worst.decision.judgment,
    )
    return ReviewBundle(
        decision=decision,
        runs=runs,
        cost_usd=sum(run.cost_usd for run in runs),
        latency_ms=sum(run.latency_ms for run in runs),
        provider_errors=tuple(
            run.provider_error for run in runs if run.provider_error is not None
        ),
    )
