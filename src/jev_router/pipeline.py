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
    review: ReviewBundle
    outcome: str

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "role": self.role,
            "dispatch": self.dispatch.to_dict(),
            "verifiers": [asdict(item) | {"passed": item.passed} for item in self.verifiers],
            "review": self.review.to_dict(),
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class PipelineResult:
    status: str
    initial_role: str
    final_role: str
    rounds: tuple[PipelineRound, ...]
    elapsed_ms: float
    review_cost_usd: float

    def to_dict(self) -> dict:
        return {
            "status": self.status,
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


def _retry_prompt(
    task: str,
    role: str,
    review: ReviewBundle,
    verifiers: tuple[VerifierReceipt, ...],
) -> str:
    failed_commands = [" ".join(item.command) for item in verifiers if not item.passed]
    return (
        f"Continue the existing implementation for this task:\n\n{task}\n\n"
        f"The previous {role} attempt was not accepted. Review rules: "
        f"{', '.join(review.decision.fired_rules) or 'none'}. "
        f"Failed verifier commands: {failed_commands or 'none'}. "
        "Inspect the current working tree, correct the implementation, run relevant tests, "
        "and do not discard valid existing changes."
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
    max_rounds: int = 3,
    max_review_usd: float = 0.05,
    sandbox: str = "workspace-write",
    dispatch_fn: Callable[..., CodexDispatchReceipt] = run_codex_dispatch,
) -> PipelineResult:
    if max_rounds < 1:
        raise ValueError("max_rounds must be positive")
    repository = Path(repository).resolve()
    criteria = tuple(acceptance_criteria) or (task,)
    commands = tuple(verifier_commands)
    role = initial_role
    prompt = task
    rounds: list[PipelineRound] = []
    role_attempts: dict[str, int] = {}
    review_spend = 0.0
    started = time.perf_counter()

    for number in range(1, max_rounds + 1):
        role_attempts[role] = role_attempts.get(role, 0) + 1
        plan = build_codex_dispatch_plan(repository, role, sandbox=sandbox)
        dispatch = dispatch_fn(plan, prompt)
        verifiers = run_verifiers(repository, commands)
        packets = collect_git_review_packet_chunks(
            repository,
            packet_id=f"pipeline-round-{number}",
            task=task,
            acceptance_criteria=criteria,
            base="HEAD",
            head="WORKTREE",
            evidence={
                "verifiers": [asdict(item) | {"passed": item.passed} for item in verifiers],
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
        else:
            review = run_review_bundle(packets, review_provider, config)
        review_spend += review.cost_usd
        verifier_passed = all(item.passed for item in verifiers)
        next_role: str | None = None

        if budget_preflight or review_spend > max_review_usd:
            outcome = "budget_exceeded"
            status = "blocked"
        elif dispatch.returncode != 0:
            outcome = "dispatch_failed"
            next_role = _next_tier(role)
            status = "continue" if next_role is not None else "needs_human_review"
        elif review.decision.action == "block":
            outcome = "blocked_by_policy"
            status = "blocked"
        elif review.decision.action == "accept" and verifier_passed:
            outcome = "accepted"
            status = "accepted"
        elif number == max_rounds:
            outcome = "round_limit"
            status = "needs_human_review"
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

        rounds.append(PipelineRound(number, role, dispatch, verifiers, review, outcome))
        if status != "continue":
            break
        role = next_role
        prompt = _retry_prompt(task, role, review, verifiers)

    return PipelineResult(
        status=status,
        initial_role=initial_role,
        final_role=role,
        rounds=tuple(rounds),
        elapsed_ms=(time.perf_counter() - started) * 1000,
        review_cost_usd=review_spend,
    )
