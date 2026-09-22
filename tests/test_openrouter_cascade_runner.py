from __future__ import annotations

import pytest

from jev_router.config import load_config
from jev_router.livecodebench_runner import LiveCodeBenchTask
from jev_router.models import GenerationResult, Usage
from jev_router.openrouter_cascade_runner import run_livecodebench_openrouter_cascade
from jev_router.solution_verifier import SolutionJudgment


def task() -> LiveCodeBenchTask:
    return LiveCodeBenchTask(
        question_title="Add",
        question_content="Read two integers and print their sum.",
        platform="unit",
        question_id="q1",
        contest_id="c1",
        contest_date="2026-01-01",
        starter_code="",
        difficulty="easy",
    )


def result(model: str, cost: float, code: str) -> GenerationResult:
    return GenerationResult(
        text=f"```python\n{code}\n```",
        usage=Usage(100, 0, 20),
        latency_ms=20,
        ttft_ms=5,
        model_id=model,
        provider_cost_usd=cost,
        generation_id=f"gen-{model}",
        provider="OpenAI",
    )


def test_cascade_escalates_and_returns_strong_code(monkeypatch, tmp_path):
    import jev_router.openrouter_cascade_runner as module

    calls = []

    class Worker:
        def __init__(self, config):
            pass

        def generate_tier(self, request, tier):
            calls.append(tier)
            return result(tier, 0.001 if tier == "luna" else 0.01, f"print('{tier}')")

    class Judge:
        def __init__(self, config):
            pass

        def judge(self, task, code):
            return SolutionJudgment(
                signals={"fully_correct": 0.1, "edge_case_failure": 0.8, "complexity_failure": 0.2, "needs_stronger_model": 0.9},
                failure_mode="logic",
                failure_probabilities={"logic": 1.0},
                confidence=0.9,
                escalation_score=0.9,
                usage=Usage(20, 0, 2),
                latency_ms=10,
                model_id="jev",
                provider_cost_usd=0.0001,
            )

    monkeypatch.setattr(module, "OpenRouterChatProvider", Worker)
    monkeypatch.setattr(module, "OpenRouterSolutionJudgeProvider", Judge)
    summary = run_livecodebench_openrouter_cascade(
        [task()],
        output_dir=tmp_path,
        config=load_config("configs/default.toml"),
        threshold=0.66,
        max_total_usd=1.0,
        max_output_tokens=256,
    )

    assert calls == ["luna", "sol"]
    assert summary["strong_calls"] == 1
    assert summary["total_cost_usd"] == pytest.approx(0.0111)
    assert summary["measurements"][0]["code"] == "print('sol')"


def test_cascade_accepts_weak_code_below_threshold(monkeypatch, tmp_path):
    import jev_router.openrouter_cascade_runner as module

    class Worker:
        def __init__(self, config):
            pass

        def generate_tier(self, request, tier):
            assert tier == "luna"
            return result(tier, 0.001, "print('luna')")

    class Judge:
        def __init__(self, config):
            pass

        def judge(self, task, code):
            return SolutionJudgment(
                signals={"fully_correct": 0.95, "edge_case_failure": 0.05, "complexity_failure": 0.01, "needs_stronger_model": 0.05},
                failure_mode="none",
                failure_probabilities={"none": 1.0},
                confidence=0.9,
                escalation_score=0.05,
                usage=Usage(20, 0, 2),
                latency_ms=10,
                model_id="jev",
                provider_cost_usd=0.0001,
            )

    monkeypatch.setattr(module, "OpenRouterChatProvider", Worker)
    monkeypatch.setattr(module, "OpenRouterSolutionJudgeProvider", Judge)
    summary = run_livecodebench_openrouter_cascade(
        [task()],
        output_dir=tmp_path,
        config=load_config("configs/default.toml"),
        threshold=0.66,
        max_total_usd=1.0,
        max_output_tokens=256,
    )

    assert summary["strong_calls"] == 0
    assert summary["measurements"][0]["code"] == "print('luna')"


def test_difficulty_gate_sends_hard_directly_to_strong(monkeypatch, tmp_path):
    import jev_router.openrouter_cascade_runner as module

    calls = []

    class Worker:
        def __init__(self, config):
            pass

        def generate_tier(self, request, tier):
            calls.append(tier)
            return result(tier, 0.01, "print('sol')")

    class JudgeMustNotRun:
        def __init__(self, config):
            pass

        def judge(self, task, code):
            raise AssertionError("hard direct route must skip Jev")

    hard = task()
    object.__setattr__(hard, "difficulty", "hard")
    monkeypatch.setattr(module, "OpenRouterChatProvider", Worker)
    monkeypatch.setattr(module, "OpenRouterSolutionJudgeProvider", JudgeMustNotRun)
    summary = run_livecodebench_openrouter_cascade(
        [hard],
        output_dir=tmp_path,
        config=load_config("configs/default.toml"),
        threshold=0.21,
        max_total_usd=1.0,
        max_output_tokens=256,
        direct_strong_difficulties=frozenset({"hard"}),
    )

    assert calls == ["sol"]
    assert summary["measurements"][0]["escalation_reason"] == "difficulty_direct_strong"
    assert summary["weak_cost_usd"] == 0.0
