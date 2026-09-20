from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .models import Attempt, Usage

JudgeAction = Literal["accept", "revise", "escalate", "block"]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class ReviewPacket:
    """Bounded, auditable evidence supplied to a semantic code judge."""

    id: str
    task: str
    acceptance_criteria: tuple[str, ...]
    diff: str
    changed_files: tuple[str, ...] = ()
    relevant_code: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    risk_flags: tuple[str, ...] = ()
    forbidden_changes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_state(self) -> dict[str, Any]:
        return {
            "task": {
                "request": self.task,
                "acceptance_criteria": list(self.acceptance_criteria),
                "forbidden_changes": list(self.forbidden_changes),
            },
            "change": {
                "diff": self.diff,
                "changed_files": list(self.changed_files),
                "relevant_code": self.relevant_code,
            },
            "evidence": self.evidence,
            "risk_flags": list(self.risk_flags),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ReviewJudgment:
    """Raw TypeSafe judgments before deterministic policy composition."""

    signals: dict[str, float]
    risk_level: RiskLevel
    risk_probabilities: dict[str, float]
    risk_confidence: float
    usage: Usage
    latency_ms: float
    model_id: str
    attempts: tuple[Attempt, ...] = ()
    provider_cost_usd: float | None = None
    generation_id: str | None = None
    provider: str | None = None


@dataclass(frozen=True)
class ReviewDecision:
    action: JudgeAction
    fired_rules: tuple[str, ...]
    signals: dict[str, float]
    risk_level: RiskLevel
    risk_confidence: float
    uncertain_signals: tuple[str, ...] = ()
    judgment: ReviewJudgment | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JudgeBenchmarkCase:
    packet: ReviewPacket
    split: str
    expected_action: JudgeAction
    oracle_reasons: tuple[str, ...]
    fixture: dict[str, Any] = field(default_factory=dict)
