from __future__ import annotations

from typing import Protocol

from ..models import Attempt, GenerationRequest, GenerationResult, JevJudgment, Task


class ProviderError(RuntimeError):
    def __init__(
        self,
        kind: str,
        message: str,
        retryable: bool = False,
        attempts: tuple[Attempt, ...] = (),
    ):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.attempts = attempts


class GeneratorProvider(Protocol):
    def generate(self, request: GenerationRequest, role: str) -> GenerationResult: ...


class JevProvider(Protocol):
    def judge(self, task: Task) -> JevJudgment: ...
