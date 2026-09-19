from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ModelRole = Literal["cheap", "strong"]
RunMode = Literal["fixture", "live"]


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Attempt:
    usage: Usage
    latency_ms: float
    status: str


@dataclass(frozen=True)
class GenerationRequest:
    task_id: str
    prompt: str
    system: str
    max_output_tokens: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResult:
    text: str
    usage: Usage
    latency_ms: float
    ttft_ms: float | None
    model_id: str
    attempts: tuple[Attempt, ...] = ()
    status: str = "ok"
    provider_cost_usd: float | None = None
    generation_id: str | None = None
    provider: str | None = None


@dataclass(frozen=True)
class JevJudgment:
    selected: ModelRole
    strong_probability: float
    confidence: float
    task_type: str
    probabilities: dict[str, float]
    usage: Usage
    latency_ms: float
    model_id: str
    attempts: tuple[Attempt, ...] = ()
    provider_cost_usd: float | None = None
    generation_id: str | None = None
    provider: str | None = None


@dataclass(frozen=True)
class RouteDecision:
    selected: ModelRole | None
    router: str
    rule: str
    task_type: str | None = None
    confidence: float | None = None
    strong_probability: float | None = None
    jev: JevJudgment | None = None
    router_attempts: tuple[Attempt, ...] = ()
    rejected_reason: str | None = None


@dataclass
class Task:
    id: str
    split: str
    language: str
    group: str
    prompt: str
    metric: str
    expected: Any
    constraints: dict[str, Any]
    fixture: dict[str, Any]
    jev_fixture: dict[str, Any]
    tests: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Measurement:
    run_id: str
    mode: RunMode
    baseline: str
    task_id: str
    split: str
    language: str
    group: str
    selected_role: str | None
    selected_model: str | None
    quality: float
    target_cost_usd: float
    router_cost_usd: float
    total_cost_usd: float
    latency_ms: float
    router_latency_ms: float
    target_latency_ms: float
    ttft_ms: float | None
    fallback: bool
    error: str | None
    route_rule: str
    output_text: str
    usage: dict[str, int]
    router_usage: dict[str, int] = field(default_factory=dict)
    target_cost_source: str = "calculated_from_usage"
    router_cost_source: str = "calculated_from_usage"
    target_generation_id: str | None = None
    router_generation_id: str | None = None
    target_provider: str | None = None
    router_provider: str | None = None
    jev_choice: str | None = None
    jev_strong_probability: float | None = None
    jev_confidence: float | None = None
    jev_task_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
