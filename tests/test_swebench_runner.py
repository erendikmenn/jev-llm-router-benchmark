from __future__ import annotations

import json
import subprocess

import pytest

from jev_router.swebench_runner import (
    ARMS,
    SWEbenchTask,
    load_swebench_plan,
    prepare_swebench_checkout,
)


def test_plan_loader_uses_only_public_task_fields(tmp_path):
    plan = {
        "dev": [
            {
                "instance_id": "owner__repo-1",
                "repo": "owner/repo",
                "base_commit": "a" * 40,
                "problem_statement": "Fix the bug.",
                "patch": "gold must not be loaded",
            }
        ],
        "test": [],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    tasks = load_swebench_plan(path, "dev", 1)

    assert tasks == [SWEbenchTask("owner__repo-1", "owner/repo", "a" * 40, "Fix the bug.")]
    assert not hasattr(tasks[0], "patch")


def test_task_rejects_untrusted_repo_and_commit():
    with pytest.raises(ValueError):
        SWEbenchTask.from_dict(
            {
                "instance_id": "bad",
                "repo": "owner/repo;touch bad",
                "base_commit": "HEAD",
                "problem_statement": "bad",
            }
        )
    with pytest.raises(ValueError):
        SWEbenchTask.from_dict(
            {
                "instance_id": "owner/repo;touch bad",
                "repo": "owner/repo",
                "base_commit": "a" * 40,
                "problem_statement": "bad",
            }
        )


def test_existing_checkout_must_be_clean_and_exact(tmp_path):
    task = SWEbenchTask("owner__repo-1", "owner/repo", "a" * 40, "Fix")

    def runner(command, **kwargs):
        if command[-2:] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, stdout="dirty\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="a" * 40 + "\n", stderr="")

    with pytest.raises(RuntimeError):
        prepare_swebench_checkout(task, tmp_path, runner=runner)


def test_all_four_fixed_tiers_and_router_arms_are_available():
    assert ARMS == (
        "always-luna",
        "always-terra",
        "always-sol",
        "always-astra",
        "router-only",
        "router-judge",
    )


def test_plan_loader_supports_deterministic_offset(tmp_path):
    rows = [
        {
            "instance_id": f"owner__repo-{index}",
            "repo": "owner/repo",
            "base_commit": "a" * 40,
            "problem_statement": f"Fix {index}",
        }
        for index in range(3)
    ]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"dev": rows, "test": []}), encoding="utf-8")

    assert load_swebench_plan(path, "dev", 1, 1)[0].instance_id == "owner__repo-1"
