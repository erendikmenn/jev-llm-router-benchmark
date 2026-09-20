from __future__ import annotations

import json
from dataclasses import dataclass

from .config import AppConfig
from .judge_models import ReviewDecision, ReviewPacket
from .judge_policy import decide_review
from .pricing import estimate_tokens, jev_cost
from .providers.base import ProviderError, ReviewJudgeProvider


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
