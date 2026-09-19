from __future__ import annotations

from ..config import AppConfig
from ..models import GenerationRequest, GenerationResult, JevJudgment, Task, Usage


class FixtureGenerator:
    def __init__(self, config: AppConfig):
        self.config = config

    def generate(self, request: GenerationRequest, role: str) -> GenerationResult:
        record = request.metadata["fixture"][role]
        model = getattr(self.config, role)
        return GenerationResult(
            text=record["text"],
            usage=Usage(**record["usage"]),
            latency_ms=float(record["latency_ms"]),
            ttft_ms=record.get("ttft_ms"),
            model_id=model.model_id,
            status=record.get("status", "ok"),
        )


class FixtureJev:
    def __init__(self, config: AppConfig):
        self.config = config

    def judge(self, task: Task) -> JevJudgment:
        record = task.jev_fixture
        probabilities = {k: float(v) for k, v in record["probabilities"].items()}
        return JevJudgment(
            selected=record["choice"],
            strong_probability=probabilities["strong"],
            confidence=float(record["confidence"]),
            task_type=record["task_type"],
            probabilities=probabilities,
            usage=Usage(**record["usage"]),
            latency_ms=float(record["latency_ms"]),
            model_id=self.config.router["jev_model"],
        )

