from __future__ import annotations

import subprocess

from jev_router.codex_dispatch import CodexDispatchReceipt
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

    result = run_coding_pipeline(
        tmp_path,
        task="Change before to after.",
        acceptance_criteria=["value.txt contains after"],
        initial_role="luna",
        review_provider=AcceptingJudge(),
        config=load_config("configs/default.toml"),
        verifier_commands=(("sh", "-c", "test $(cat value.txt) = after"),),
        dispatch_fn=dispatch,
    )

    assert result.status == "accepted"
    assert result.final_role == "luna"
    assert result.rounds[0].verifiers[0].passed
    assert result.rounds[0].outcome == "accepted"
