from __future__ import annotations

import json
import subprocess

import pytest

from jev_router.codex_dispatch import build_codex_dispatch_plan, run_codex_dispatch


def test_build_plan_maps_router_role_to_native_codex_model(tmp_path):
    (tmp_path / ".git").mkdir()
    plan = build_codex_dispatch_plan(tmp_path, "cheap", sandbox="read-only")

    assert plan.role.model == "gpt-5.6-luna"
    assert plan.role.reasoning_effort == "medium"
    assert plan.command[-1] == "-"
    assert "read-only" in plan.command
    assert "workspace-write" not in plan.command


def test_dispatch_uses_stdin_and_parses_jsonl_receipt(tmp_path):
    (tmp_path / ".git").mkdir()
    plan = build_codex_dispatch_plan(tmp_path, "strong")
    captured = {}

    def fake_runner(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        events = [
            {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
        ]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="\n".join(json.dumps(event) for event in events),
            stderr="",
        )

    receipt = run_codex_dispatch(plan, "private task", runner=fake_runner)

    assert captured["input"] == "private task"
    assert "private task" not in captured["command"]
    assert receipt.final_message == "done"
    assert receipt.usage["input_tokens"] == 10
    assert receipt.returncode == 0
    assert len(receipt.prompt_sha256) == 64


def test_dispatch_rejects_danger_full_access(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="unsupported sandbox"):
        build_codex_dispatch_plan(tmp_path, "sol", sandbox="danger-full-access")


def test_dispatch_records_timeout_instead_of_aborting_campaign(tmp_path):
    (tmp_path / ".git").mkdir()
    plan = build_codex_dispatch_plan(tmp_path, "terra")

    def timeout_runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    receipt = run_codex_dispatch(
        plan,
        "hard task",
        timeout_seconds=12.5,
        runner=timeout_runner,
    )

    assert receipt.returncode == 124
    assert receipt.final_message is None
    assert receipt.usage == {}
    assert "timed out after 12.5 seconds" in receipt.stderr
