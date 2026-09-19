from __future__ import annotations

import json
import os
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import AppConfig
from ..models import Attempt, GenerationRequest, GenerationResult, Usage
from .base import ProviderError


class OpenAIResponsesProvider:
    """Small typed Responses API adapter with bounded retries.

    It deliberately avoids an SDK dependency. Provider-reported usage is the only
    source for measured live cost; retry attempts are preserved for accounting.
    """

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, config: AppConfig):
        self.config = config
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ProviderError("missing_key", "OPENAI_API_KEY is not set")

    def generate(self, request: GenerationRequest, role: str) -> GenerationResult:
        model = getattr(self.config, role)
        attempts: list[Attempt] = []
        max_retries = int(self.config.experiment["max_retries"])
        timeout = float(self.config.experiment["request_timeout_seconds"])
        body = {
            "model": model.model_id,
            "instructions": request.system,
            "input": request.prompt,
            "max_output_tokens": request.max_output_tokens,
            "store": False,
            "reasoning": {"effort": "none"},
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
                    },
                    method="POST",
                )
                with urlopen(req, timeout=timeout) as response:
                    payload = json.loads(response.read())
                latency = (time.perf_counter() - started) * 1000
                raw_usage = payload.get("usage", {})
                input_details = raw_usage.get("input_tokens_details", {})
                usage = Usage(
                    input_tokens=int(raw_usage.get("input_tokens", 0)),
                    cached_input_tokens=int(input_details.get("cached_tokens", 0)),
                    output_tokens=int(raw_usage.get("output_tokens", 0)),
                )
                attempts.append(Attempt(usage, latency, "ok"))
                text = payload.get("output_text") or _extract_output_text(payload)
                return GenerationResult(
                    text=text,
                    usage=usage,
                    latency_ms=sum(item.latency_ms for item in attempts),
                    ttft_ms=None,
                    model_id=payload.get("model", model.model_id),
                    attempts=tuple(attempts),
                )
            except HTTPError as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, f"http_{exc.code}"))
                retryable = exc.code in {408, 429, 500, 502, 503, 504, 529}
                if not retryable or attempt_index == max_retries:
                    raise ProviderError(f"http_{exc.code}", str(exc), retryable, tuple(attempts)) from exc
            except (TimeoutError, URLError) as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, "network"))
                if attempt_index == max_retries:
                    raise ProviderError("timeout_or_network", str(exc), True, tuple(attempts)) from exc
            time.sleep(min(4.0, 0.5 * (2**attempt_index)) * (0.75 + random.random() * 0.25))
        raise AssertionError("retry loop exhausted")


def _extract_output_text(payload: dict) -> str:
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                chunks.append(content.get("text", ""))
    if not chunks:
        raise ProviderError("invalid_response", "Responses API returned no output text")
    return "".join(chunks)
