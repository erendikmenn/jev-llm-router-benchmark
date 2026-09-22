from __future__ import annotations

import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from .codex_dispatch import (
    CodexDispatchReceipt,
    build_codex_dispatch_plan,
    run_codex_dispatch,
)
from .config import AppConfig
from .evidence import collect_git_review_packet_chunks
from .judge_models import ReviewDecision
from .judge_service import ReviewBundle, ReviewRun, estimate_review_cost, run_review_bundle
from .providers.base import ReviewJudgeProvider
from .tiered_routing import TIERS
from .trajectory import (
    EvidenceGate,
    ProgressSnapshot,
    TrajectoryProfile,
    collect_progress_snapshot,
    decide_evidence_gate,
)


@dataclass(frozen=True)
class VerifierReceipt:
    command: tuple[str, ...]
    returncode: int
    elapsed_ms: float
    stdout_tail: str
    stderr_tail: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class PipelineRound:
    number: int
    role: str
    dispatch: CodexDispatchReceipt
    verifiers: tuple[VerifierReceipt, ...]
    progress: ProgressSnapshot
    evidence_gate: EvidenceGate
    review: ReviewBundle
    review_called: bool
    outcome: str

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "role": self.role,
            "dispatch": self.dispatch.to_dict(),
            "verifiers": [asdict(item) | {"passed": item.passed} for item in self.verifiers],
            "progress": self.progress.to_dict(),
            "evidence_gate": self.evidence_gate.to_dict(),
            "review": self.review.to_dict(),
            "review_called": self.review_called,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class PipelineResult:
    status: str
    profile: TrajectoryProfile
    initial_role: str
    final_role: str
    rounds: tuple[PipelineRound, ...]
    elapsed_ms: float
    review_cost_usd: float

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "profile": self.profile,
            "initial_role": self.initial_role,
            "final_role": self.final_role,
            "rounds": [item.to_dict() for item in self.rounds],
            "elapsed_ms": self.elapsed_ms,
            "review_cost_usd": self.review_cost_usd,
        }


def run_verifiers(
    repository: str | Path,
    commands: Iterable[tuple[str, ...]],
    *,
    timeout_seconds: float = 300.0,
) -> tuple[VerifierReceipt, ...]:
    receipts: list[VerifierReceipt] = []
    for command in commands:
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                list(command),
                cwd=repository,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            returncode = 124
            stdout = exc.stdout or ""
            stderr = exc.stderr or "verifier timed out"
        receipts.append(
            VerifierReceipt(
                tuple(command),
                returncode,
                (time.perf_counter() - started) * 1000,
                str(stdout)[-4000:],
                str(stderr)[-4000:],
            )
        )
    return tuple(receipts)


def _next_tier(role: str) -> str | None:
    normalized = "luna" if role == "cheap" else "sol" if role == "strong" else role
    if normalized not in TIERS:
        return "astra"
    index = TIERS.index(normalized)
    return TIERS[index + 1] if index + 1 < len(TIERS) else None


def _balanced_next_role(role: str) -> str | None:
    normalized = "luna" if role == "cheap" else "sol" if role == "strong" else role
    if normalized in {"luna", "terra"}:
        return "sol"
    if normalized == "sol":
        return "astra"
    return None


def _balanced_effective_action(review: ReviewBundle, config: AppConfig) -> str:
    """Turn Jev's semantic review into a cost-aware trajectory decision.

    The semantic judge is useful for finding concrete defects and operational risk, but
    epistemic uncertainty (for example, asking for deeper repository exploration) is not
    evidence that a second coding worker will improve the patch.  The balanced policy
    therefore promotes only on provider failure, material risk, or a high-confidence
    visible implementation defect.  Softer disagreement is retained in the receipt as a
    shadow warning and measured later by the official benchmark evaluator.
    """

    decision = review.decision
    if decision.action == "block":
        return "block"
    if review.provider_errors:
        return "escalate"

    rules = {
        rule.split(":", 1)[-1] if rule.startswith("chunk_") else rule
        for rule in decision.fired_rules
    }
    if rules & {
        "high_stakes_static_risk_flag",
        "high_semantic_risk",
        "critical_static_risk_flag",
        "critical_semantic_risk",
        "semantic_policy_violation",
    }:
        return "escalate"

    signals = decision.signals
    clear_failure = float(
        config.judge.get("balanced_clear_failure_probability", 0.20)
    )
    regression_failure = float(
        config.judge.get("balanced_regression_escalate", 0.90)
    )
    if signals.get("requirements_complete", 1.0) < clear_failure:
        return "escalate"
    if (
        signals.get("scope_aligned", 1.0) < clear_failure
        and signals.get("behavior_supported", 1.0) < clear_failure
    ):
        return "escalate"
    if signals.get("regression_risk", 0.0) >= regression_failure:
        return "escalate"
    return "accept"


def _synthetic_review(action: str, reason_codes: tuple[str, ...]) -> ReviewBundle:
    risk_level = "critical" if action == "block" else "high"
    decision = ReviewDecision(
        action=action,
        fired_rules=reason_codes,
        signals={},
        risk_level=risk_level,
        risk_confidence=1.0,
    )
    return ReviewBundle(decision, (), 0.0, 0.0, ())


def _retry_prompt(
    task: str,
    previous_role: str,
    next_role: str,
    review: ReviewBundle,
    verifiers: tuple[VerifierReceipt, ...],
    progress: ProgressSnapshot,
    dispatch: CodexDispatchReceipt,
) -> str:
    failed_evidence = []
    for item in verifiers:
        if item.passed:
            continue
        output = (item.stderr_tail or item.stdout_tail or "no output")[-1500:]
        failed_evidence.append(
            f"- {' '.join(item.command)} (exit {item.returncode}):\n{output}"
        )
    dispatch_error = dispatch.stderr[-1500:] if dispatch.stderr else "none"
    return (
        f"Continue the existing implementation for this task:\n\n{task}\n\n"
        f"The previous {previous_role} attempt was not accepted; you are the {next_role} "
        "repair worker. Preserve valid existing changes and fix only what remains.\n"
        f"Reason codes: {', '.join(review.decision.fired_rules) or 'none'}.\n"
        f"Changed files: {', '.join(progress.changed_files) or 'none'}.\n"
        f"Diff size: {progress.diff_bytes} bytes; added/deleted lines: "
        f"{progress.lines_added}/{progress.lines_deleted}.\n"
        f"Worker stderr: {dispatch_error}\n"
        "Failed verifier evidence:\n"
        f"{chr(10).join(failed_evidence) if failed_evidence else '- none'}\n"
        "Inspect the task, current worktree and relevant code, correct the implementation, "
        "then run the relevant tests. Do not discard valid existing changes."
    )


def run_coding_pipeline(
    repository: str | Path,
    *,
    task: str,
    acceptance_criteria: Iterable[str],
    initial_role: str,
    review_provider: ReviewJudgeProvider,
    config: AppConfig,
    verifier_commands: Iterable[tuple[str, ...]] = (),
    profile: TrajectoryProfile = "quality-first",
    max_rounds: int = 3,
    max_review_usd: float = 0.05,
    sandbox: str = "workspace-write",
    dispatch_fn: Callable[..., CodexDispatchReceipt] = run_codex_dispatch,
    round_observer: Callable[[PipelineRound], None] | None = None,
) -> PipelineResult:
    if max_rounds < 1:
        raise ValueError("max_rounds must be positive")
    if profile not in {"quality-first", "balanced"}:
        raise ValueError(f"unknown trajectory profile: {profile}")
    repository = Path(repository).resolve()
    criteria = tuple(acceptance_criteria) or (task,)
    commands = tuple(verifier_commands)
    role = initial_role
    prompt = task
    rounds: list[PipelineRound] = []
    role_attempts: dict[str, int] = {}
    review_spend = 0.0
    previous_progress: ProgressSnapshot | None = None
    started = time.perf_counter()

    for number in range(1, max_rounds + 1):
        role_attempts[role] = role_attempts.get(role, 0) + 1
        plan = build_codex_dispatch_plan(repository, role, sandbox=sandbox)
        dispatch = dispatch_fn(plan, prompt)
        verifiers = run_verifiers(repository, commands)
        progress = collect_progress_snapshot(
            repository,
            dispatch_returncode=dispatch.returncode,
            verifiers=verifiers,
            previous=previous_progress,
        )
        evidence_gate = (
            decide_evidence_gate(progress, current_role=role)
            if profile == "balanced"
            else EvidenceGate("review", ("quality_first_full_review",))
        )
        budget_preflight = False
        review_called = evidence_gate.action == "review"
        if not review_called:
            review = _synthetic_review(evidence_gate.action, evidence_gate.reason_codes)
        else:
            packets = collect_git_review_packet_chunks(
                repository,
                packet_id=f"pipeline-round-{number}",
                task=task,
                acceptance_criteria=criteria,
                base="HEAD",
                head="WORKTREE",
                evidence={
                    "progress": progress.to_dict(),
                    "verifiers": [
                        asdict(item) | {"passed": item.passed} for item in verifiers
                    ],
                    "agent_authored_tests_are_independent": False,
                },
                max_diff_chars=int(config.judge["max_diff_chars"]),
                max_file_chars=int(config.judge["max_file_chars"]),
                max_context_chars=int(config.judge["max_context_chars"]),
            )
            estimated_review = sum(estimate_review_cost(packet, config) for packet in packets)
            budget_preflight = review_spend + estimated_review > max_review_usd
            if budget_preflight:
                budget_run = ReviewRun(
                    decision=ReviewDecision(
                        "escalate", ("review_budget_preflight",), {}, "high", 1.0
                    ),
                    cost_usd=0.0,
                    cost_source="not_called_budget_preflight",
                    latency_ms=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    provider_error="budget_preflight",
                )
                review = ReviewBundle(
                    budget_run.decision,
                    (budget_run,),
                    0.0,
                    0.0,
                    ("budget_preflight",),
                )
                review_called = False
            else:
                review = run_review_bundle(packets, review_provider, config)
        review_spend += review.cost_usd
        verifier_passed = all(item.passed for item in verifiers)
        effective_action = review.decision.action
        if profile == "balanced" and review_called:
            effective_action = _balanced_effective_action(review, config)
        next_role: str | None = None

        if budget_preflight or review_spend > max_review_usd:
            outcome = "budget_exceeded"
            status = "blocked"
        elif effective_action == "block":
            outcome = "blocked_by_policy"
            status = "blocked"
        elif dispatch.returncode != 0:
            outcome = "dispatch_failed"
            next_role = (
                _balanced_next_role(role) if profile == "balanced" else _next_tier(role)
            )
            status = "continue" if next_role is not None else "needs_human_review"
        elif effective_action == "accept" and verifier_passed:
            outcome = (
                "accepted"
                if review.decision.action == "accept"
                else "accepted_with_shadow_warning"
            )
            status = "accepted"
        elif number == max_rounds:
            outcome = "round_limit"
            status = "needs_human_review"
        else:
            if profile == "balanced":
                next_role = _balanced_next_role(role)
            else:
                should_promote = (
                    review.decision.action == "escalate"
                    or dispatch.returncode != 0
                    or role_attempts[role] >= 2
                )
                next_role = _next_tier(role) if should_promote else role
            if next_role is None:
                outcome = "frontier_exhausted"
                status = "needs_human_review"
            else:
                outcome = "promote" if next_role != role else "revise_same_role"
                status = "continue"

        completed_round = PipelineRound(
            number,
            role,
            dispatch,
            verifiers,
            progress,
            evidence_gate,
            review,
            review_called,
            outcome,
        )
        rounds.append(completed_round)
        if round_observer is not None:
            round_observer(completed_round)
        if status != "continue":
            break
        previous_role = role
        role = next_role
        prompt = _retry_prompt(
            task,
            previous_role,
            role,
            review,
            verifiers,
            progress,
            dispatch,
        )
        previous_progress = progress

    return PipelineResult(
        status=status,
        profile=profile,
        initial_role=initial_role,
        final_role=role,
        rounds=tuple(rounds),
        elapsed_ms=(time.perf_counter() - started) * 1000,
        review_cost_usd=review_spend,
    )
