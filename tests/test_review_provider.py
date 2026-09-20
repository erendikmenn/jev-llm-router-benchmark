from __future__ import annotations

import json

import pytest

from jev_router.config import load_config
from jev_router.judge_models import ReviewPacket
from jev_router.providers.base import ProviderError
from jev_router.providers.review import OpenRouterReviewJudgeProvider, REVIEW_QUESTIONS


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def packet() -> ReviewPacket:
    return ReviewPacket(
        id="review-1",
        task="Fix email normalization.",
        acceptance_criteria=("Normalize every lookup path.",),
        diff="diff --git a/users.py b/users.py",
        changed_files=("users.py",),
        relevant_code={"users.py": "def find(email): ..."},
    )


def response_payload() -> dict:
    answers = {
        name: {"type": "noul", "noul": 0.9}
        for name in REVIEW_QUESTIONS
        if name != "action_risk"
    }
    answers["regression_risk"]["noul"] = 0.1
    answers["self_test_bias"]["noul"] = 0.1
    answers["needs_deep_review"]["noul"] = 0.1
    answers["policy_violation"]["noul"] = 0.05
    answers["action_risk"] = {
        "type": "choice",
        "choice": "low",
        "probabilities": {"low": 0.9, "medium": 0.1, "high": 0.0, "critical": 0.0},
        "confidence": 0.87,
    }
    return {
        "id": "decision-1",
        "model": "typesafe/jev-1.13",
        "provider": "TypeSafe",
        "answers": answers,
        "usage": {"input_tokens": 600, "output_tokens": 80, "cost": 0.0000252},
    }


def test_openrouter_review_provider_sends_packet_and_parses_all_signals(monkeypatch):
    import jev_router.providers.review as module

    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse(response_payload())

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    result = OpenRouterReviewJudgeProvider(load_config("configs/default.toml")).judge(packet())

    assert captured["body"]["state"]["change"]["diff"].startswith("diff --git")
    assert set(captured["body"]["questions"]) == set(REVIEW_QUESTIONS)
    assert result.signals["requirements_complete"] == pytest.approx(0.9)
    assert result.signals["regression_risk"] == pytest.approx(0.1)
    assert result.risk_level == "low"
    assert result.provider_cost_usd == pytest.approx(0.0000252)


def test_review_provider_fails_closed_on_missing_answer(monkeypatch):
    import jev_router.providers.review as module

    payload = response_payload()
    del payload["answers"]["scope_aligned"]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse(payload))
    with pytest.raises(ProviderError) as exc:
        OpenRouterReviewJudgeProvider(load_config("configs/default.toml")).judge(packet())
    assert exc.value.kind == "invalid_response"
