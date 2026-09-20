from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from ..judge_models import ReviewJudgment, ReviewPacket
from ..models import Attempt, GenerationRequest, GenerationResult, JevJudgment, Task


class ProviderError(RuntimeError):
    def __init__(
        self,
        kind: str,
        message: str,
        retryable: bool = False,
        attempts: tuple[Attempt, ...] = (),
        cached: bool = False,
    ):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.attempts = attempts
        self.cached = cached


class GeneratorProvider(Protocol):
    def generate(self, request: GenerationRequest, role: str) -> GenerationResult: ...


class JevProvider(Protocol):
    def judge(self, task: Task) -> JevJudgment: ...


class ReviewJudgeProvider(Protocol):
    def judge(self, packet: ReviewPacket) -> ReviewJudgment: ...


class CachedGeneratorProvider:
    """Reuse each live task/model result across counterfactual routing policies."""

    def __init__(self, provider: GeneratorProvider):
        self.provider = provider
        self._cache: dict[tuple[str, str], GenerationResult | ProviderError] = {}

    def generate(self, request: GenerationRequest, role: str) -> GenerationResult:
        key = (request.task_id, role)
        cached = self._cache.get(key)
        if isinstance(cached, ProviderError):
            raise ProviderError(
                cached.kind,
                str(cached),
                cached.retryable,
                cached.attempts,
                cached=True,
            )
        if cached is not None:
            return replace(cached, status="cache_replay")
        try:
            result = self.provider.generate(request, role)
        except ProviderError as exc:
            self._cache[key] = exc
            raise
        self._cache[key] = result
        return result
