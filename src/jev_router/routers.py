from __future__ import annotations

import random
import re

from .config import AppConfig
from .eligibility import check_eligibility
from .models import RouteDecision, Task
from .providers.base import JevProvider, ProviderError


def fixed_router(task: Task, role: str, config: AppConfig) -> RouteDecision:
    eligibility = check_eligibility(task, config)
    if eligibility.reject_reason:
        return RouteDecision(None, f"always_{role}", "deterministic_reject", rejected_reason=eligibility.reject_reason)
    selected = role if role in eligibility.eligible_roles else eligibility.eligible_roles[-1]
    return RouteDecision(selected, f"always_{role}", f"fixed_{selected}")


def rule_router(task: Task, config: AppConfig) -> RouteDecision:
    eligibility = check_eligibility(task, config)
    if eligibility.reject_reason:
        return RouteDecision(None, "rule", "deterministic_reject", rejected_reason=eligibility.reject_reason)
    text = task.prompt.casefold()
    strong_patterns = (
        r"\b(prove|kanıtla|debug|hata ayıkla|optimize|dinamik programlama)\b",
        r"\b(step by step|adım adım|all constraints|tüm kısıt)\b",
        r"\b(write a function|fonksiyon yaz)\b",
    )
    selected = "strong" if any(re.search(pattern, text) for pattern in strong_patterns) else "cheap"
    return RouteDecision(selected, "rule", f"rule_pattern_{selected}")


def random_router(task: Task, config: AppConfig, strong_rate: float, seed: int) -> RouteDecision:
    eligibility = check_eligibility(task, config)
    if eligibility.reject_reason:
        return RouteDecision(None, "random_matched", "deterministic_reject", rejected_reason=eligibility.reject_reason)
    rng = random.Random(f"{seed}:{task.id}")
    selected = "strong" if rng.random() < strong_rate else "cheap"
    return RouteDecision(selected, "random_matched", f"seeded_random_at_{strong_rate:.3f}")


def jev_router(task: Task, config: AppConfig, provider: JevProvider, threshold: float) -> RouteDecision:
    eligibility = check_eligibility(task, config)
    if eligibility.reject_reason:
        return RouteDecision(None, "jev", "deterministic_reject", rejected_reason=eligibility.reject_reason)
    try:
        judgment = provider.judge(task)
    except ProviderError as exc:
        return RouteDecision("strong", "jev", f"jev_error_fallback:{exc.kind}")
    selected = "strong" if judgment.strong_probability >= threshold else "cheap"
    rule = f"strong_probability_gte_{threshold:.3f}" if selected == "strong" else f"strong_probability_lt_{threshold:.3f}"
    if judgment.confidence < 0.20:
        selected = "strong"
        rule = "confidence_lt_0.20_fallback_strong"
    return RouteDecision(
        selected=selected,
        router="jev",
        rule=rule,
        task_type=judgment.task_type,
        confidence=judgment.confidence,
        strong_probability=judgment.strong_probability,
        jev=judgment,
    )

