from __future__ import annotations

import subprocess

from jev_router.codex_dispatch import CodexDispatchReceipt
from jev_router.cli import parser
from jev_router.config import load_config
from jev_router.judge_models import ReviewJudgment
from jev_router.models import Usage
from jev_router.pipeline import run_coding_pipeline


class AcceptingJudge:
    def judge(self, packet):
        return ReviewJudgment(
            signals={
                "requirements_complete": 0.95,
                "scope_aligned": 0.95,
                "behavior_supported": 0.95,
                "regression_risk": 0.05,
                "self_test_bias": 0.05,
                "needs_deep_review": 0.05,
                "policy_violation": 0.01,
            },
            risk_level="low",
            risk_probabilities={"low": 0.95, "medium": 0.03, "high": 0.01, "critical": 0.01},
            risk_confidence=0.92,
            usage=Usage(100, 0, 10),
            latency_ms=5,
            model_id="fixture-jev",
            provider_cost_usd=0.0,
        )


class CountingJudge(AcceptingJudge):
    def __init__(self):
        self.calls = 0

    def judge(self, packet):
        self.calls += 1
        return super().judge(packet)


def test_pipeline_cli_exposes_both_trajectory_profiles():
    balanced = parser().parse_args(
        ["pipeline", "--task", "Change one file.", "--profile", "balanced"]
    )
    quality = parser().parse_args(
        ["pipeline", "--task", "Change one file.", "--profile", "quality-first"]
    )

    assert balanced.profile == "balanced"
    assert quality.profile == "quality-first"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def test_pipeline_dispatches_verifies_and_accepts(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / "value.txt").write_text("before\n", encoding="utf-8")
    git(tmp_path, "add", "value.txt")
    git(tmp_path, "commit", "-qm", "initial")

    def dispatch(plan, prompt):
        (tmp_path / "value.txt").write_text("after\n", encoding="utf-8")
        return CodexDispatchReceipt(plan, "0" * 64, 0, 10, {}, "done", "", 0, 2)

    observed = []
    result = run_coding_pipeline(
        tmp_path,
        task="Change before to after.",
        acceptance_criteria=["value.txt contains after"],
        initial_role="luna",
        review_provider=AcceptingJudge(),
        config=load_config("configs/default.toml"),
        verifier_commands=(("sh", "-c", "test $(cat value.txt) = after"),),
        dispatch_fn=dispatch,
        round_observer=observed.append,
    )

    assert result.status == "accepted"
    assert result.final_role == "luna"
    assert result.rounds[0].verifiers[0].passed
    assert result.rounds[0].outcome == "accepted"
    assert observed == [result.rounds[0]]


def test_balanced_pipeline_promotes_failed_luna_directly_to_sol(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / "value.txt").write_text("before\n", encoding="utf-8")
    git(tmp_path, "add", "value.txt")
    git(tmp_path, "commit", "-qm", "initial")
    roles = []
    prompts = []

    def dispatch(plan, prompt):
        roles.append(plan.role.name)
        prompts.append(prompt)
        value = "wrong\n" if plan.role.name == "luna" else "after\n"
        (tmp_path / "value.txt").write_text(value, encoding="utf-8")
        return CodexDispatchReceipt(plan, "0" * 64, 0, 10, {}, "done", "", 0, 2)

    judge = CountingJudge()
    result = run_coding_pipeline(
        tmp_path,
        task="Change before to after.",
        acceptance_criteria=["value.txt contains after"],
        initial_role="luna",
        review_provider=judge,
        config=load_config("configs/default.toml"),
        verifier_commands=(("sh", "-c", "test $(cat value.txt) = after"),),
        profile="balanced",
        dispatch_fn=dispatch,
    )

    assert result.status == "accepted"
    assert result.profile == "balanced"
    assert roles == ["luna", "sol"]
    assert result.rounds[0].review_called is False
    assert result.rounds[0].evidence_gate.reason_codes == ("verifier_failed",)
    assert result.rounds[1].review_called is True
    assert judge.calls == 1
    assert "previous luna attempt" in prompts[1]
    assert "verifier_failed" in prompts[1]


def test_balanced_pipeline_blocks_destructive_change_without_judge(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "initial")

    def dispatch(plan, prompt):
        target = tmp_path / "migrations" / "001.sql"
        target.parent.mkdir(exist_ok=True)
        target.write_text("DROP TABLE users;\n", encoding="utf-8")
        return CodexDispatchReceipt(plan, "0" * 64, 0, 10, {}, "done", "", 0, 2)

    judge = CountingJudge()
    result = run_coding_pipeline(
        tmp_path,
        task="Update the data layer.",
        acceptance_criteria=["Data remains safe."],
        initial_role="luna",
        review_provider=judge,
        config=load_config("configs/default.toml"),
        profile="balanced",
        dispatch_fn=dispatch,
    )

    assert result.status == "blocked"
    assert result.rounds[0].outcome == "blocked_by_policy"
    assert result.rounds[0].review_called is False
    assert judge.calls == 0
