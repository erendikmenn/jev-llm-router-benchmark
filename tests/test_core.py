from __future__ import annotations

from dataclasses import replace

import pytest

from jev_router.calibrate import calibration_curve, select_threshold
from jev_router.config import load_config
from jev_router.dataset import find_cross_split_duplicates, load_tasks
from jev_router.eligibility import check_eligibility
from jev_router.evaluate import BudgetLedger, run_measurement
from jev_router.models import GenerationResult, JevJudgment, RouteDecision, Usage
from jev_router.providers.base import ProviderError
from jev_router.providers.base import CachedGeneratorProvider
from jev_router.models import GenerationRequest
from jev_router.pricing import jev_cost, usage_cost
from jev_router.routers import jev_router
from jev_router.routers import rule_router
from jev_router.scoring import score_output


@pytest.fixture()
def config():
    return load_config("configs/default.toml")


@pytest.fixture()
def tasks():
    return load_tasks("data/demo_pilot.jsonl")


def test_demo_dataset_has_no_cross_split_exact_duplicates(tasks):
    assert len(tasks) == 40
    assert find_cross_split_duplicates(tasks) == []


def test_scoring_json_and_code(tasks):
    assert score_output(tasks[0], tasks[0].fixture["strong"]["text"]) == 1
    coding = next(task for task in tasks if task.metric == "python_tests")
    assert score_output(coding, coding.fixture["strong"]["text"]) == 1


def test_public_benchmark_choice_and_numeric_scoring(tasks):
    choice = replace(tasks[0], metric="choice_exact", expected="B")
    assert score_output(choice, "B") == 1
    assert score_output(choice, "(B).") == 1
    assert score_output(choice, "The answer is B") == 1
    assert score_output(choice, "A") == 0
    numeric = replace(tasks[0], metric="numeric_exact", expected="1,250")
    assert score_output(numeric, "$1,250") == 1
    assert score_output(numeric, "Final answer: 1250") == 1
    assert score_output(numeric, "1251") == 0


def test_code_sandbox_blocks_network_socket(tasks):
    coding = next(task for task in tasks if task.metric == "python_tests")
    probe = replace(
        coding,
        tests=[{"expression": "network_is_blocked()"}],
    )
    source = (
        "def network_is_blocked():\n"
        "    try:\n"
        "        import socket\n"
        "        sock = socket.socket()\n"
        "        sock.bind(('127.0.0.1', 0))\n"
        "        return False\n"
        "    except OSError:\n"
        "        return True\n"
    )
    assert score_output(probe, source) == 1


def test_deterministic_filter_rejects_non_text(config, tasks):
    task = replace(tasks[0], constraints={"modality": "image"})
    assert check_eligibility(task, config).reject_reason == "unsupported_modality:image"


def test_price_includes_cached_tokens(config):
    value = usage_cost(Usage(100, 40, 20), config.cheap)
    expected = (60 * 0.20 + 40 * 0.02 + 20 * 1.20) / 1_000_000
    assert value == pytest.approx(expected)
    assert jev_cost(Usage(100, 0, 50), config) == pytest.approx(100 * 0.042 / 1_000_000)


def test_calibration_uses_dev_and_returns_curve(config, tasks):
    dev = [task for task in tasks if task.split == "dev"]
    points = calibration_curve(dev)
    chosen = select_threshold(points, 2.0)
    assert points
    assert 0 <= chosen.strong_rate <= 1


class BrokenJev:
    def judge(self, task):
        raise ProviderError("invalid_response", "bad schema")


def test_jev_parse_error_falls_back_to_strong(config, tasks):
    decision = jev_router(tasks[0], config, BrokenJev(), 0.5)
    assert decision.selected == "strong"
    assert decision.rule == "jev_error_fallback:invalid_response"


def test_router_error_fallback_is_recorded_in_measurement(config, tasks):
    measurement = run_measurement(
        "test", "fixture", "jev", tasks[0],
        RouteDecision("strong", "jev", "jev_error_fallback:http_520"),
        CheapTimeoutThenStrong(),
        config, BudgetLedger(None),
    )
    assert measurement.error == "jev_error_fallback:http_520"


class LowConfidenceJev:
    def judge(self, task):
        return JevJudgment("cheap", 0.1, 0.1, "general_qa", {"cheap": 0.9, "strong": 0.1}, Usage(10, 0, 2), 4, "jev-1.13.0")


def test_low_confidence_falls_back_to_strong(config, tasks):
    decision = jev_router(tasks[0], config, LowConfidenceJev(), 0.5)
    assert decision.selected == "strong"
    assert "confidence" in decision.rule


def test_rule_router_catches_turkish_inflection(config, tasks):
    task = replace(tasks[0], prompt="Bir Python fonksiyonu yaz ve tüm kısıtları uygula.")
    assert rule_router(task, config).selected == "strong"


class CheapTimeoutThenStrong:
    def generate(self, request, role):
        if role == "cheap":
            raise ProviderError("timeout", "timed out", True)
        return GenerationResult(
            text=request.metadata["fixture"]["strong"]["text"],
            usage=Usage(10, 0, 2), latency_ms=30, ttft_ms=None, model_id="strong-test"
        )


def test_target_timeout_fallback_is_recorded(config, tasks):
    measurement = run_measurement(
        "test", "fixture", "jev", tasks[0], RouteDecision("cheap", "jev", "test"),
        CheapTimeoutThenStrong(), config, BudgetLedger(None)
    )
    assert measurement.fallback is True
    assert measurement.selected_role == "strong"
    assert measurement.error.startswith("cheap_timeout_fallback")
    assert measurement.target_cost_usd > usage_cost(Usage(10, 0, 2), config.strong)


def test_budget_limit_is_hard():
    ledger = BudgetLedger(0.01)
    ledger.add(0.009)
    with pytest.raises(Exception, match="exceed"):
        ledger.add(0.002)


def test_cached_generator_reuses_live_matrix_result():
    class CountingProvider:
        calls = 0

        def generate(self, request, role):
            self.calls += 1
            return GenerationResult(
                text="ok", usage=Usage(3, 0, 1), latency_ms=12,
                ttft_ms=4, model_id=role, provider_cost_usd=0.001,
            )

    inner = CountingProvider()
    cached = CachedGeneratorProvider(inner)
    request = GenerationRequest("task-1", "p", "s", 10)
    first = cached.generate(request, "cheap")
    second = cached.generate(request, "cheap")
    assert inner.calls == 1
    assert first.status == "ok"
    assert second.status == "cache_replay"
    assert second.provider_cost_usd == first.provider_cost_usd
