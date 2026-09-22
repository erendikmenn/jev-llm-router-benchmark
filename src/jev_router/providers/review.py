from __future__ import annotations

import json
import os
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import AppConfig
from ..judge_models import ReviewJudgment, ReviewPacket
from ..models import Attempt, Usage
from .base import ProviderError


_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 524, 529}

REVIEW_QUESTIONS = {
    "requirements_complete": {
        "type": "noul",
        "instructions": (
            "Does `change` fully implement every item in `task.acceptance_criteria`, "
            "based on the supplied diff and relevant code?"
        ),
        "criteria": {
            "true": "Every stated acceptance criterion is implemented.",
            "false": "At least one criterion is missing, partial, or contradicted.",
        },
    },
    "scope_aligned": {
        "type": "noul",
        "instructions": (
            "Is `change` limited to work necessary for `task.request`, without unrelated "
            "behavior changes or changes listed in `task.forbidden_changes`?"
        ),
    },
    "behavior_supported": {
        "type": "noul",
        "instructions": (
            "Do `change.relevant_code` and `evidence` support that the changed behavior "
            "will work as requested, rather than merely compiling or satisfying a narrow self-written test?"
        ),
    },
    "regression_risk": {
        "type": "noul",
        "instructions": (
            "Is there a material regression risk visible in `change`, such as broken callers, "
            "API incompatibility, changed error semantics, or an unhandled edge case?"
        ),
    },
    "self_test_bias": {
        "type": "noul",
        "instructions": (
            "Does the supplied validation rely too heavily on tests written with the same change, "
            "or tests that repeat the implementation instead of independently checking the task?"
        ),
    },
    "needs_deep_review": {
        "type": "noul",
        "instructions": (
            "Is there concrete evidence in the supplied state that another, stronger coding "
            "worker must inspect or modify this patch? Do not answer true merely because hidden "
            "tests, more execution, or broader repository exploration could increase confidence."
        ),
        "criteria": {
            "true": "A specific visible defect or unresolved requirement is likely to need a stronger worker.",
            "false": "No concrete defect is visible, even if independent verification would still be useful.",
        },
    },
    "policy_violation": {
        "type": "noul",
        "instructions": (
            "Does `change` expose secrets, bypass a security or authorization policy, perform a "
            "forbidden destructive action, or violate `task.forbidden_changes`?"
        ),
    },
    "action_risk": {
        "type": "choice",
        "instructions": "What is the highest operational risk level of applying `change`?",
        "criteria": {
            "low": "Localized and readily reversible; no sensitive boundary is affected.",
            "medium": "Broader or user-visible behavior changes, but recovery is straightforward.",
            "high": "Authentication, authorization, payments, migrations, tenant data, or a security boundary is affected.",
            "critical": "Secrets, destructive irreversible actions, or explicit policy bypass are present.",
        },
    },
}


class HTTPReviewJudgeProvider:
    def __init__(
        self,
        config: AppConfig,
        *,
        endpoint: str,
        api_key_env: str,
        model_id: str,
        provider_name: str,
        extra_headers: dict[str, str] | None = None,
    ):
        self.config = config
        self.endpoint = endpoint
        self.model_id = model_id
        self.provider_name = provider_name
        self.extra_headers = extra_headers or {}
        self.api_key = os.getenv(api_key_env)
        if not self.api_key:
            raise ProviderError("missing_key", f"{api_key_env} is not set")

    def judge(self, packet: ReviewPacket) -> ReviewJudgment:
        attempts: list[Attempt] = []
        max_retries = int(self.config.experiment["max_retries"])
        timeout = float(self.config.experiment["request_timeout_seconds"])
        body = {
            "model": self.model_id,
            "state": packet.to_state(),
            "questions": REVIEW_QUESTIONS,
        }
        for attempt_index in range(max_retries + 1):
            started = time.perf_counter()
            usage = Usage()
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    **self.extra_headers,
                }
                request = Request(
                    self.endpoint,
                    data=json.dumps(body).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read())
                latency = (time.perf_counter() - started) * 1000
                raw_usage = payload["usage"]
                usage = Usage(
                    input_tokens=int(raw_usage.get("input_tokens", 0)),
                    output_tokens=int(raw_usage.get("output_tokens", 0)),
                )
                attempts.append(Attempt(usage, latency, "ok"))
                answers = payload["answers"]
                signals = {
                    name: float(answers[name]["noul"])
                    for name in REVIEW_QUESTIONS
                    if name != "action_risk"
                }
                risk = answers["action_risk"]
                probabilities = {
                    name: float(probability)
                    for name, probability in risk["probabilities"].items()
                }
                return ReviewJudgment(
                    signals=signals,
                    risk_level=risk["choice"],
                    risk_probabilities=probabilities,
                    risk_confidence=float(risk["confidence"]),
                    usage=usage,
                    latency_ms=sum(item.latency_ms for item in attempts),
                    model_id=payload["model"],
                    attempts=tuple(attempts),
                    provider_cost_usd=(
                        float(raw_usage["cost"])
                        if raw_usage.get("cost") is not None
                        else None
                    ),
                    generation_id=payload.get("id"),
                    provider=payload.get("provider") or self.provider_name,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError(
                    "invalid_response", str(exc), False, tuple(attempts)
                ) from exc
            except HTTPError as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, f"http_{exc.code}"))
                retryable = exc.code in _RETRYABLE_STATUS
                if not retryable or attempt_index == max_retries:
                    raise ProviderError(
                        f"http_{exc.code}", str(exc), retryable, tuple(attempts)
                    ) from exc
            except (TimeoutError, URLError) as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, "network"))
                if attempt_index == max_retries:
                    raise ProviderError(
                        "timeout_or_network", str(exc), True, tuple(attempts)
                    ) from exc
            time.sleep(
                min(4.0, 0.5 * (2**attempt_index))
                * (0.75 + random.random() * 0.25)
            )
        raise AssertionError("retry loop exhausted")


class OpenRouterReviewJudgeProvider(HTTPReviewJudgeProvider):
    def __init__(self, config: AppConfig):
        super().__init__(
            config,
            endpoint="https://openrouter.ai/api/alpha/decisions",
            api_key_env="OPENROUTER_API_KEY",
            model_id=config.router["jev_model"],
            provider_name="OpenRouter",
            extra_headers={"X-OpenRouter-Title": "jev-llm-router-benchmark"},
        )


class TypeSafeReviewJudgeProvider(HTTPReviewJudgeProvider):
    def __init__(self, config: AppConfig):
        super().__init__(
            config,
            endpoint="https://api.typesafe.ai/v1/systemone",
            api_key_env="TYPESAFE_API_KEY",
            model_id=config.router["typesafe_model"],
            provider_name="TypeSafe",
        )
