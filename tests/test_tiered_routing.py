from __future__ import annotations

from jev_router.models import Task, Usage
from jev_router.tiered_routing import TieredJudgment, decide_tiered_route


def task(prompt: str) -> Task:
    return Task("x", "test", "en", "coding", prompt, "contains_all", [], {}, {}, {})


def judgment(selected="luna", risk="low", ambiguity=0.1, confidence=0.8):
    return TieredJudgment(
        selected=selected,
        probabilities={"luna": 0.7, "terra": 0.1, "sol": 0.1, "astra": 0.1},
        confidence=confidence,
        risk=risk,
        risk_probabilities={risk: 0.8},
        ambiguity_probability=ambiguity,
        usage=Usage(100, 0, 10),
        latency_ms=20,
        model_id="jev",
    )


def test_keeps_low_risk_least_sufficient_tier():
    decision = decide_tiered_route(task("Rename a local variable."), judgment())
    assert decision.selected == "luna"
    assert decision.hard_guards == ()


def test_promotes_high_risk_to_sol():
    decision = decide_tiered_route(task("Refactor a shared component."), judgment(risk="high"))
    assert decision.selected == "sol"
    assert "high_risk_minimum_sol" in decision.hard_guards


def test_critical_domain_promotes_to_astra_without_model_discretion():
    decision = decide_tiered_route(task("Change OAuth token validation."), judgment())
    assert decision.selected == "astra"
    assert decision.rule == "critical_domain_to_astra"


def test_ambiguity_and_low_confidence_promote_to_sol():
    decision = decide_tiered_route(
        task("Improve this module."), judgment(ambiguity=0.8, confidence=0.1)
    )
    assert decision.selected == "sol"
    assert decision.hard_guards == (
        "ambiguity_minimum_sol",
        "low_confidence_minimum_sol",
    )
