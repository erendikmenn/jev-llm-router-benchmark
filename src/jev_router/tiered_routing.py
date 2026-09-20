from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import AppConfig
from .models import Attempt, Task, Usage
from .providers.base import ProviderError


TIERS = ("luna", "terra", "sol", "astra")
_TIER_INDEX = {tier: index for index, tier in enumerate(TIERS)}
_CRITICAL_PATTERNS = re.compile(
    r"\b(auth(?:entication|orization)?|oauth|cryptograph\w*|payment|billing|"
    r"permission\w*|sandbox|secret\w*|credential\w*|data loss|drop table|"
    r"migration|tenant isolation)\b",
    re.IGNORECASE,
)
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 524, 529}


@dataclass(frozen=True)
class TieredJudgment:
    selected: str
    probabilities: dict[str, float]
    confidence: float
    risk: str
    risk_probabilities: dict[str, float]
    ambiguity_probability: float
    usage: Usage
    latency_ms: float
    model_id: str
    provider_cost_usd: float | None = None
    attempts: tuple[Attempt, ...] = ()


@dataclass(frozen=True)
class TieredRouteDecision:
    selected: str
    raw_selected: str
    rule: str
    hard_guards: tuple[str, ...]
    judgment: TieredJudgment

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["judgment"]["usage"] = asdict(self.judgment.usage)
        payload["judgment"]["attempts"] = [asdict(item) for item in self.judgment.attempts]
        return payload


class OpenRouterTieredJevProvider:
    endpoint = "https://openrouter.ai/api/alpha/decisions"

    def __init__(self, config: AppConfig):
        self.config = config
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ProviderError("missing_key", "OPENROUTER_API_KEY is not set")

    def judge(self, task: Task) -> TieredJudgment:
        profiles = self.config.raw["codex_tiers"]
        body = {
            "model": self.config.router["jev_model"],
            "state": {
                "request": task.prompt,
                "constraints": task.constraints,
                "candidate_profiles": profiles,
            },
            "questions": {
                "target_model": {
                    "type": "choice",
                    "instructions": (
                        "Select the least capable Codex profile likely to complete every stated "
                        "requirement correctly. Prefer the cheaper profile only when it is sufficient."
                    ),
                    "criteria": {
                        tier: str(profiles[tier]["profile"]) for tier in TIERS
                    },
                },
                "risk": {
                    "type": "choice",
                    "instructions": "Classify the impact if the requested code change is implemented incorrectly.",
                    "criteria": {
                        "low": "Localized and easily reversible with no sensitive boundary.",
                        "medium": "Could cause a user-visible regression across a component.",
                        "high": "Could affect security, money, data integrity, permissions, or many users.",
                        "critical": "Could cause irreversible loss or cross-boundary compromise.",
                    },
                },
                "ambiguous": {
                    "type": "noul",
                    "instructions": (
                        "Is the request materially underspecified such that different reasonable "
                        "implementations could violate an unstated requirement?"
                    ),
                },
            },
        }
        attempts: list[Attempt] = []
        max_retries = int(self.config.experiment["max_retries"])
        timeout = float(self.config.experiment["request_timeout_seconds"])
        for attempt_index in range(max_retries + 1):
            started = time.perf_counter()
            usage = Usage()
            try:
                request = Request(
                    self.endpoint,
                    data=json.dumps(body).encode(),
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "X-OpenRouter-Title": "jev-llm-router-benchmark",
                    },
                    method="POST",
                )
                with urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read())
                latency = (time.perf_counter() - started) * 1000
                raw_usage = payload.get("usage") or {}
                usage = Usage(
                    input_tokens=int(raw_usage.get("input_tokens", 0)),
                    output_tokens=int(raw_usage.get("output_tokens", 0)),
                )
                attempts.append(Attempt(usage, latency, "ok"))
                model_answer = payload["answers"]["target_model"]
                risk_answer = payload["answers"]["risk"]
                ambiguity_answer = payload["answers"]["ambiguous"]
                return TieredJudgment(
                    selected=str(model_answer["choice"]),
                    probabilities={
                        key: float(value)
                        for key, value in model_answer["probabilities"].items()
                    },
                    confidence=float(model_answer["confidence"]),
                    risk=str(risk_answer["choice"]),
                    risk_probabilities={
                        key: float(value)
                        for key, value in risk_answer["probabilities"].items()
                    },
                    ambiguity_probability=float(ambiguity_answer["noul"]),
                    usage=usage,
                    latency_ms=sum(item.latency_ms for item in attempts),
                    model_id=str(payload["model"]),
                    provider_cost_usd=(
                        float(raw_usage["cost"])
                        if raw_usage.get("cost") is not None
                        else None
                    ),
                    attempts=tuple(attempts),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ProviderError("invalid_response", str(exc), attempts=tuple(attempts)) from exc
            except HTTPError as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, f"http_{exc.code}"))
                if exc.code not in _RETRYABLE_STATUS or attempt_index == max_retries:
                    raise ProviderError(
                        f"http_{exc.code}", str(exc), exc.code in _RETRYABLE_STATUS, tuple(attempts)
                    ) from exc
            except (TimeoutError, URLError) as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, "network"))
                if attempt_index == max_retries:
                    raise ProviderError("timeout_or_network", str(exc), True, tuple(attempts)) from exc
            time.sleep(min(4.0, 0.5 * (2**attempt_index)) * (0.75 + random.random() * 0.25))
        raise AssertionError("retry loop exhausted")


def _promote(current: str, minimum: str) -> str:
    return TIERS[max(_TIER_INDEX[current], _TIER_INDEX[minimum])]


def decide_tiered_route(task: Task, judgment: TieredJudgment) -> TieredRouteDecision:
    selected = judgment.selected if judgment.selected in TIERS else "sol"
    guards: list[str] = []
    isolated_code = bool(task.constraints.get("isolated_code"))
    if _CRITICAL_PATTERNS.search(task.prompt) and not isolated_code:
        selected = _promote(selected, "astra")
        guards.append("critical_domain_to_astra")
    elif judgment.risk in {"high", "critical"}:
        selected = _promote(selected, "sol")
        guards.append("high_risk_minimum_sol")
    if judgment.ambiguity_probability >= 0.70:
        selected = _promote(selected, "sol")
        guards.append("ambiguity_minimum_sol")
    if judgment.confidence < 0.25:
        selected = _promote(selected, "sol")
        guards.append("low_confidence_minimum_sol")
    rule = "+".join(guards) if guards else "jev_least_sufficient_profile"
    return TieredRouteDecision(selected, judgment.selected, rule, tuple(guards), judgment)
