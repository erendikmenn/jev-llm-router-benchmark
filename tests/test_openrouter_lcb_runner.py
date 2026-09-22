from __future__ import annotations

from jev_router.config import load_config
from jev_router.livecodebench_runner import LiveCodeBenchTask
from jev_router.models import GenerationResult, Usage
from jev_router.openrouter_lcb_runner import (
    estimate_tier_request_cost,
    run_livecodebench_openrouter,
)


def sample_task() -> LiveCodeBenchTask:
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


def test_tier_estimate_uses_checked_openrouter_prices():
    config = load_config("configs/default.toml")
    luna = estimate_tier_request_cost(
        config, "luna", prompt="short", max_output_tokens=1000
    )
    sol = estimate_tier_request_cost(
        config, "sol", prompt="short", max_output_tokens=1000
    )
    assert 0 < luna < sol


def test_openrouter_lcb_run_checkpoints_provider_cost(monkeypatch, tmp_path):
    import jev_router.openrouter_lcb_runner as module

    class FakeProvider:
        def __init__(self, config):
            pass

        def generate_tier(self, request, tier):
            assert tier == "luna"
            return GenerationResult(
                text="```python\nprint(sum(map(int, input().split())))\n```",
                usage=Usage(120, 0, 20),
                latency_ms=25,
                ttft_ms=5,
                model_id="openai/gpt-5.6-luna",
                provider_cost_usd=0.0001,
                generation_id="gen-1",
                provider="OpenAI",
            )

    monkeypatch.setattr(module, "OpenRouterChatProvider", FakeProvider)
    summary = run_livecodebench_openrouter(
        [sample_task()],
        output_dir=tmp_path,
        config=load_config("configs/default.toml"),
        forced_role="luna",
        max_total_usd=0.01,
        max_output_tokens=256,
    )

    assert summary["transport"] == "openrouter_api"
    assert summary["dispatch_completed"] == 1
    assert summary["worker_cost_usd"] == 0.0001
    assert summary["measurements"][0]["code"].startswith("print(")
    assert (tmp_path / "predictions.json").is_file()


def test_openrouter_lcb_resume_does_not_resample_failed_pass_at_1(monkeypatch, tmp_path):
    import json
    import jev_router.openrouter_lcb_runner as module

    (tmp_path / "generation-summary.json").write_text(
        json.dumps(
            {
                "measurements": [
                    {
                        "question_id": "q1",
                        "status": "generation_failed",
                        "worker_cost_usd": 0.001,
                        "jev_route_cost_usd": 0.0,
                        "code": "",
                    }
                ]
            }
        )
    )

    class MustNotRun:
        def __init__(self, config):
            pass

        def generate_tier(self, request, tier):
            raise AssertionError("pass@1 failure must not be resampled")

    monkeypatch.setattr(module, "OpenRouterChatProvider", MustNotRun)
    summary = run_livecodebench_openrouter(
        [sample_task()],
        output_dir=tmp_path,
        config=load_config("configs/default.toml"),
        forced_role="luna",
        max_total_usd=0.01,
        max_output_tokens=256,
    )

    assert summary["tasks_attempted"] == 1
    assert summary["dispatch_completed"] == 0
