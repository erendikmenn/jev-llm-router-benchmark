from __future__ import annotations

from .config import AppConfig, ModelConfig
from .models import Attempt, Usage


def usage_cost(usage: Usage, model: ModelConfig) -> float:
    uncached = max(0, usage.input_tokens - usage.cached_input_tokens)
    return (
        uncached * model.input_usd_per_million
        + usage.cached_input_tokens * model.cached_input_usd_per_million
        + usage.output_tokens * model.output_usd_per_million
    ) / 1_000_000


def attempts_cost(attempts: tuple[Attempt, ...], model: ModelConfig) -> float:
    return sum(usage_cost(attempt.usage, model) for attempt in attempts)


def jev_cost(usage: Usage, config: AppConfig) -> float:
    price = config.jev_price
    return (
        usage.input_tokens * float(price["input_usd_per_million"])
        + usage.output_tokens * float(price["output_usd_per_million"])
    ) / 1_000_000


def estimate_tokens(text: str) -> int:
    """Conservative preflight estimate only; billed cost uses provider usage."""
    return max(1, (len(text.encode("utf-8")) + 2) // 3)


def estimate_request_cost(prompt: str, max_output_tokens: int, model: ModelConfig) -> float:
    return usage_cost(Usage(estimate_tokens(prompt), 0, max_output_tokens), model)

