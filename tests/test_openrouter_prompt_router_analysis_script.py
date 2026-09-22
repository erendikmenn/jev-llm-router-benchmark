from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "analyze_openrouter_prompt_router.py"
SPEC = importlib.util.spec_from_file_location("analyze_openrouter_prompt_router", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_prompt_router_uses_calibrated_non_luna_probability():
    ids = ("a", "b")
    routes = {
        "measurements": [
            {
                "question_id": q,
                "route_latency_ms": 10,
                "jev_route_cost_usd": 0.001,
                "route": {"judgment": {"probabilities": {"luna": luna}}},
            }
            for q, luna in zip(ids, (0.95, 0.80))
        ]
    }
    weak = {
        "measurements": [
            {"question_id": q, "worker_cost_usd": 0.01, "worker": {"latency_ms": 100}}
            for q in ids
        ]
    }
    strong = {
        "measurements": [
            {"question_id": q, "worker_cost_usd": 0.10, "worker": {"latency_ms": 200}}
            for q in ids
        ]
    }
    weak_eval = {"official_checker": True, "per_task": [{"question_id": "a", "passed": True}, {"question_id": "b", "passed": False}]}
    strong_eval = {"official_checker": True, "per_task": [{"question_id": "a", "passed": True}, {"question_id": "b", "passed": True}]}

    report = MODULE.analyze(routes, weak, weak_eval, strong, strong_eval, threshold=0.08)

    assert report["passed"] == 2
    assert report["strong_calls"] == 1
    assert report["cost_usd"]["total"] == pytest.approx(0.112)
