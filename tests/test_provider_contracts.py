from __future__ import annotations

import io
from urllib.error import HTTPError

import pytest

from jev_router.config import load_config
from jev_router.providers.base import ProviderError
from jev_router.providers.openai import _extract_output_text
from jev_router.providers.typesafe import TypeSafeJevProvider


def test_openai_invalid_response_contract():
    with pytest.raises(ProviderError, match="no output text"):
        _extract_output_text({"output": []})


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
