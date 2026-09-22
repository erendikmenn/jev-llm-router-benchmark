from __future__ import annotations

import io
import time
from urllib.error import HTTPError

import pytest

from jev_router.config import load_config
from jev_router.providers.base import ProviderError
from jev_router.providers.openai import _extract_output_text
from jev_router.providers.typesafe import TypeSafeJevProvider
from jev_router.providers.openrouter import OpenRouterChatProvider


def test_openai_invalid_response_contract():
    with pytest.raises(ProviderError, match="no output text"):
        _extract_output_text({"output": []})


def test_openrouter_stream_captures_text_usage_cost_and_ttft():
    lines = [
        b'data: {"id":"gen-1","model":"openai/gpt-5.6-luna","provider":"OpenAI","choices":[{"delta":{"content":"4"}}]}\n',
        b'data: {"id":"gen-1","model":"openai/gpt-5.6-luna","choices":[{"delta":{"content":"2"}}],"usage":{"prompt_tokens":10,"completion_tokens":2,"prompt_tokens_details":{"cached_tokens":3},"cost":0.000004}}\n',
        b'data: [DONE]\n',
    ]
    parsed = OpenRouterChatProvider._read_stream(lines, time.perf_counter())
    assert parsed["text"] == "42"
    assert parsed["usage"].input_tokens == 10
    assert parsed["usage"].cached_input_tokens == 3
    assert parsed["cost"] == pytest.approx(0.000004)
    assert parsed["ttft_ms"] is not None


def test_openrouter_tier_uses_openrouter_model_and_configured_reasoning(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    provider = OpenRouterChatProvider(load_config("configs/default.toml"))
    captured = {}

    def fake_generate(request, **kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(provider, "_generate", fake_generate)
    request = __import__("jev_router.models", fromlist=["GenerationRequest"]).GenerationRequest(
        "task", "prompt", "system", 128
    )

    assert provider.generate_tier(request, "sol") == "ok"
    assert captured == {
        "model_id": "openai/gpt-5.6-sol",
        "supports_streaming": True,
        "reasoning_effort": "high",
    }

    with pytest.raises(ValueError, match="unknown OpenRouter tier"):
        provider.generate_tier(request, "unknown")


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def test_typesafe_invalid_response_fails_closed(monkeypatch):
    from jev_router.dataset import load_tasks
    import jev_router.providers.typesafe as module

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only")
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse(b'{"model":"jev-1.13.0","answers":{},"usage":{}}'))
    provider = TypeSafeJevProvider(load_config("configs/default.toml"))
    with pytest.raises(ProviderError) as exc:
        provider.judge(load_tasks("data/demo_pilot.jsonl")[0])
    assert exc.value.kind == "invalid_response"


def test_typesafe_rate_limit_is_bounded(monkeypatch):
    from jev_router.dataset import load_tasks
    import jev_router.providers.typesafe as module

    config = load_config("configs/default.toml")
    config.raw["experiment"]["max_retries"] = 0
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only")

    def limited(*args, **kwargs):
        raise HTTPError("https://api.typesafe.ai", 429, "rate limit", {}, io.BytesIO())

    monkeypatch.setattr(module, "urlopen", limited)
    provider = TypeSafeJevProvider(config)
    with pytest.raises(ProviderError) as exc:
        provider.judge(load_tasks("data/demo_pilot.jsonl")[0])
    assert exc.value.kind == "http_429"
    assert exc.value.retryable is True


def test_typesafe_timeout_is_bounded(monkeypatch):
    from jev_router.dataset import load_tasks
    import jev_router.providers.typesafe as module

    config = load_config("configs/default.toml")
    config.raw["experiment"]["max_retries"] = 0
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only")
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("slow")))
    provider = TypeSafeJevProvider(config)
    with pytest.raises(ProviderError) as exc:
        provider.judge(load_tasks("data/demo_pilot.jsonl")[0])
    assert exc.value.kind == "timeout_or_network"
