from __future__ import annotations

import json
import os
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import AppConfig
from ..models import Attempt, JevJudgment, Task, Usage
from .base import ProviderError


class TypeSafeJevProvider:
    endpoint = "https://api.typesafe.ai/v1/systemone"

    def __init__(self, config: AppConfig):
        self.config = config
        self.api_key = os.getenv("TYPESAFE_API_KEY")
        if not self.api_key:
            raise ProviderError("missing_key", "TYPESAFE_API_KEY is not set")

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
                        "cheap": "The cheap profile is sufficient for all stated constraints.",
                        "strong": "The strong profile is needed because the cheap profile is materially likely to fail.",
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
                probabilities = {k: float(v) for k, v in target["probabilities"].items()}
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
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError("invalid_response", str(exc), False) from exc
            except HTTPError as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, f"http_{exc.code}"))
                retryable = exc.code in {408, 429, 500, 502, 503, 504, 529}
                if not retryable or attempt_index == max_retries:
                    raise ProviderError(f"http_{exc.code}", str(exc), retryable) from exc
            except (TimeoutError, URLError) as exc:
                latency = (time.perf_counter() - started) * 1000
                attempts.append(Attempt(usage, latency, "network"))
                if attempt_index == max_retries:
                    raise ProviderError("timeout_or_network", str(exc), True) from exc
            time.sleep(min(4.0, 0.5 * (2**attempt_index)) * (0.75 + random.random() * 0.25))
        raise AssertionError("retry loop exhausted")
