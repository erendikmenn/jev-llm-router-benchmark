from __future__ import annotations

import json
import os
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import AppConfig
from ..models import Attempt, GenerationRequest, GenerationResult, JevJudgment, Task, Usage
from .base import ProviderError


_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 524, 529}


def _usage_from_chat(raw: dict) -> Usage:
    details = raw.get("prompt_tokens_details") or {}
    return Usage(
        input_tokens=int(raw.get("prompt_tokens", 0)),
        cached_input_tokens=int(details.get("cached_tokens", 0)),
        output_tokens=int(raw.get("completion_tokens", 0)),
    )


class OpenRouterChatProvider:
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, config: AppConfig):
        self.config = config
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ProviderError("missing_key", "OPENROUTER_API_KEY is not set")

    def generate(self, request: GenerationRequest, role: str) -> GenerationResult:
        model = getattr(self.config, role)
        return self._generate(
            request,
            model_id=model.model_id,
            supports_streaming=model.supports_streaming,
            reasoning_effort="none",
        )

    def generate_tier(self, request: GenerationRequest, tier: str) -> GenerationResult:
        """Generate with one of the four Codex-compatible OpenRouter tiers.

        This path deliberately uses the user's OpenRouter account rather than the
        local Codex CLI. Provider-reported usage and cost remain the source of
        truth for benchmark accounting.
        """
        profiles = self.config.raw["codex_tiers"]
        if tier not in profiles:
            raise ValueError(f"unknown OpenRouter tier: {tier}")
        profile = profiles[tier]
        model_id = str(profile["model"])
        if "/" not in model_id:
            model_id = f"openai/{model_id}"
        return self._generate(
            request,
            model_id=model_id,
            supports_streaming=True,
            reasoning_effort=str(profile["reasoning_effort"]),
        )

    def _generate(
        self,
        request: GenerationRequest,
        *,
        model_id: str,
        supports_streaming: bool,
        reasoning_effort: str,
    ) -> GenerationResult:
        attempts: list[Attempt] = []
        max_retries = int(self.config.experiment["max_retries"])
        timeout = float(self.config.experiment["request_timeout_seconds"])
        stream = bool(self.config.experiment.get("stream", True)) and supports_streaming
        body = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "max_tokens": request.max_output_tokens,
            "reasoning": {"effort": reasoning_effort},
            "stream": stream,
        }
        for attempt_index in range(max_retries + 1):
            started = time.perf_counter()
            usage = Usage()
            try:
                req = Request(
                    self.endpoint,
                    data=json.dumps(body).encode(),
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "X-OpenRouter-Title": "jev-llm-router-benchmark",
                    },
                    method="POST",
                )
                with urlopen(req, timeout=timeout) as response:
                    if stream:
                        parsed = self._read_stream(response, started)
                    else:
                        parsed = self._read_non_stream(response)
                latency = (time.perf_counter() - started) * 1000
                usage = parsed["usage"]
                if usage.input_tokens <= 0:
                    raise ProviderError("missing_usage", "OpenRouter response omitted usage")
                attempts.append(Attempt(usage, latency, "ok"))
                if not parsed["text"]:
                    raise ProviderError(
                        "invalid_response",
                        "OpenRouter returned no output text",
                        False,
                        tuple(attempts),
                    )
                return GenerationResult(
                    text=parsed["text"],
                    usage=usage,
                    latency_ms=sum(item.latency_ms for item in attempts),
                    ttft_ms=parsed["ttft_ms"],
                    model_id=parsed["model"] or model_id,
                    attempts=tuple(attempts),
                    provider_cost_usd=parsed["cost"],
                    generation_id=parsed["id"],
                    provider=parsed["provider"],
                )
            except HTTPError as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, f"http_{exc.code}"))
                retryable = exc.code in _RETRYABLE_STATUS
                if not retryable or attempt_index == max_retries:
                    raise ProviderError(f"http_{exc.code}", str(exc), retryable, tuple(attempts)) from exc
            except (TimeoutError, URLError) as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, "network"))
                if attempt_index == max_retries:
                    raise ProviderError("timeout_or_network", str(exc), True, tuple(attempts)) from exc
            time.sleep(min(4.0, 0.5 * (2**attempt_index)) * (0.75 + random.random() * 0.25))
        raise AssertionError("retry loop exhausted")

    @staticmethod
    def _read_non_stream(response) -> dict:
        payload = json.loads(response.read())
        if payload.get("error"):
            raise ProviderError("provider_error", str(payload["error"].get("message", "provider error")))
        choice = (payload.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content")
        raw_usage = payload.get("usage") or {}
        return {
            "text": content if isinstance(content, str) else "",
            "usage": _usage_from_chat(raw_usage),
            "cost": float(raw_usage["cost"]) if raw_usage.get("cost") is not None else None,
            "ttft_ms": None,
            "id": payload.get("id"),
            "model": payload.get("model"),
            "provider": payload.get("provider"),
        }

    @staticmethod
    def _read_stream(response, started: float) -> dict:
        chunks: list[str] = []
        ttft_ms: float | None = None
        usage = Usage()
        cost: float | None = None
        generation_id: str | None = None
        model_id: str | None = None
        provider: str | None = None
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            payload = json.loads(data)
            if payload.get("error"):
                raise ProviderError("provider_error", str(payload["error"].get("message", "provider error")))
            generation_id = payload.get("id") or generation_id
            model_id = payload.get("model") or model_id
            provider = payload.get("provider") or provider
            for choice in payload.get("choices") or []:
                content = (choice.get("delta") or {}).get("content")
                if isinstance(content, str) and content:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - started) * 1000
                    chunks.append(content)
            raw_usage = payload.get("usage") or {}
            if raw_usage:
                usage = _usage_from_chat(raw_usage)
                if raw_usage.get("cost") is not None:
                    cost = float(raw_usage["cost"])
        text = "".join(chunks)
        return {
            "text": text,
            "usage": usage,
            "cost": cost,
            "ttft_ms": ttft_ms,
            "id": generation_id,
            "model": model_id,
            "provider": provider,
        }


class OpenRouterJevProvider:
    endpoint = "https://openrouter.ai/api/alpha/decisions"

    def __init__(self, config: AppConfig):
        self.config = config
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ProviderError("missing_key", "OPENROUTER_API_KEY is not set")

    def judge(self, task: Task) -> JevJudgment:
        attempts: list[Attempt] = []
        max_retries = int(self.config.experiment["max_retries"])
        timeout = float(self.config.experiment["request_timeout_seconds"])
        body = {
            "model": self.config.router["jev_model"],
            "state": {
                "request": task.prompt,
                "conversation_context": task.constraints.get("history", []),
                "task_constraints": task.constraints,
                "model_profiles": {
                    "cheap": self.config.cheap.profile,
                    "strong": self.config.strong.profile,
                },
            },
            "questions": {
                "target_model": {
                    "type": "choice",
                    "instructions": "Which model profile is more likely to satisfy this request fully? Judge capability fit only; do not calculate price.",
                    "criteria": {
                        "cheap": "The cheap profile is sufficient for every stated constraint.",
                        "strong": "The strong profile is needed because the cheap profile is materially likely to fail at least one constraint.",
                    },
                },
                "task_type": {
                    "type": "choice",
                    "instructions": "Which single task family best describes the request?",
                    "criteria": {
                        "extraction_classification": "Structured extraction or classification",
                        "translation_summary": "Translation, rewriting, or summarization",
                        "general_qa": "General factual question answering",
                        "multi_step_reasoning": "Multi-step logical or mathematical reasoning",
                        "coding": "Writing, debugging, or reasoning about code",
                        "other": "None of the other task families",
                    },
                },
            },
        }
        for attempt_index in range(max_retries + 1):
            started = time.perf_counter()
            usage = Usage()
            try:
                req = Request(
                    self.endpoint,
                    data=json.dumps(body).encode(),
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "X-OpenRouter-Title": "jev-llm-router-benchmark",
                    },
                    method="POST",
                )
                with urlopen(req, timeout=timeout) as response:
                    payload = json.loads(response.read())
                latency = (time.perf_counter() - started) * 1000
                raw_usage = payload["usage"]
                usage = Usage(
                    input_tokens=int(raw_usage.get("input_tokens", 0)),
                    output_tokens=int(raw_usage.get("output_tokens", 0)),
                )
                attempts.append(Attempt(usage, latency, "ok"))
                target = payload["answers"]["target_model"]
                task_type = payload["answers"]["task_type"]
                probabilities = {key: float(value) for key, value in target["probabilities"].items()}
                return JevJudgment(
                    selected=target["choice"],
                    strong_probability=probabilities["strong"],
                    confidence=float(target["confidence"]),
                    task_type=task_type["choice"],
                    probabilities=probabilities,
                    usage=usage,
                    latency_ms=sum(item.latency_ms for item in attempts),
                    model_id=payload["model"],
                    attempts=tuple(attempts),
                    provider_cost_usd=float(raw_usage["cost"]) if raw_usage.get("cost") is not None else None,
                    generation_id=payload.get("id"),
                    provider=payload.get("provider"),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ProviderError("invalid_response", str(exc), False, tuple(attempts)) from exc
            except HTTPError as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, f"http_{exc.code}"))
                retryable = exc.code in _RETRYABLE_STATUS
                if not retryable or attempt_index == max_retries:
                    raise ProviderError(f"http_{exc.code}", str(exc), retryable, tuple(attempts)) from exc
            except (TimeoutError, URLError) as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, "network"))
                if attempt_index == max_retries:
                    raise ProviderError("timeout_or_network", str(exc), True, tuple(attempts)) from exc
            time.sleep(min(4.0, 0.5 * (2**attempt_index)) * (0.75 + random.random() * 0.25))
        raise AssertionError("retry loop exhausted")
