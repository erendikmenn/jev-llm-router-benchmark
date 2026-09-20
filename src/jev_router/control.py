from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
from .judge_models import ReviewPacket
from .judge_service import ReviewRun, run_review
from .models import RouteDecision, Task
from .pricing import jev_cost
from .providers.base import JevProvider, ReviewJudgeProvider
from .routers import jev_router


@dataclass(frozen=True)
class ControlResult:
    route: RouteDecision
    review: ReviewRun
    next_step: str
    recommended_role: str | None
    total_control_cost_usd: float
    total_control_latency_ms: float

    def to_dict(self) -> dict:
        return {
            "route": {
                "selected_role": self.route.selected,
                "rule": self.route.rule,
                "task_type": self.route.task_type,
                "confidence": self.route.confidence,
                "strong_probability": self.route.strong_probability,
            },
            "review": self.review.to_dict(),
            "next_step": self.next_step,
            "recommended_role": self.recommended_role,
            "total_control_cost_usd": self.total_control_cost_usd,
            "total_control_latency_ms": self.total_control_latency_ms,
        }


def run_control(
    task: Task,
    packet: ReviewPacket,
    route_provider: JevProvider,
    review_provider: ReviewJudgeProvider,
    config: AppConfig,
    threshold: float,
) -> ControlResult:
    route = jev_router(task, config, route_provider, threshold)
    review = run_review(packet, review_provider, config)
    selected = route.selected or "strong"
    action = review.decision.action
    if action == "accept":
        next_step = "complete"
        recommended_role = selected
    elif action == "revise":
        next_step = "retry_same_model"
        recommended_role = selected
    elif action == "escalate" and selected == "cheap":
        next_step = "escalate_to_strong"
        recommended_role = "strong"
    elif action == "escalate":
        next_step = "human_or_frontier_review"
        recommended_role = None
    else:
        next_step = "block"
        recommended_role = None

    route_cost = 0.0
    route_latency = 0.0
    if route.jev is not None:
        route_cost = (
            route.jev.provider_cost_usd
            if route.jev.provider_cost_usd is not None
            else jev_cost(route.jev.usage, config)
        )
        route_latency = route.jev.latency_ms
    return ControlResult(
        route=route,
        review=review,
        next_step=next_step,
        recommended_role=recommended_role,
        total_control_cost_usd=route_cost + review.cost_usd,
        total_control_latency_ms=route_latency + review.latency_ms,
    )
