from __future__ import annotations

from ..config import AppConfig
from ..judge_models import JudgeBenchmarkCase, ReviewJudgment
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


class FixtureReviewJudge:
    def __init__(self, config: AppConfig, cases: list[JudgeBenchmarkCase]):
        self.config = config
        self.records = {case.packet.id: case.fixture for case in cases}

    def judge(self, packet) -> ReviewJudgment:
        record = self.records[packet.id]
        return ReviewJudgment(
            signals={key: float(value) for key, value in record["signals"].items()},
            risk_level=record["risk_level"],
            risk_probabilities={
                key: float(value)
                for key, value in record["risk_probabilities"].items()
            },
            risk_confidence=float(record["risk_confidence"]),
            usage=Usage(**record["usage"]),
            latency_ms=float(record["latency_ms"]),
            model_id="fixture/jev-review",
        )
