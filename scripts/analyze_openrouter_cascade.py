#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from jev_router.solution_verifier import meets_escalation_threshold


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float | None]:
    if total == 0:
        return [None, None]
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    spread = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return [max(0.0, center - spread), min(1.0, center + spread)]


def _indexed(rows: list[dict], label: str) -> dict[str, dict]:
    indexed = {str(row["question_id"]): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"duplicate question ids in {label}")
    return indexed


def _latencies(values: list[float | None]) -> dict[str, float | int | None]:
    observed = [value for value in values if value is not None]
    return {
        "observed": len(observed),
        "mean_ms": sum(observed) / len(observed) if observed else None,
        "p50_ms": statistics.median(observed) if observed else None,
        "p95_ms": percentile(observed, 0.95),
    }


def analyze(
    weak_generation: dict,
    weak_evaluation: dict,
    strong_generation: dict,
    strong_evaluation: dict,
    judgments: dict,
    *,
    threshold: float,
    direct_weak_difficulties: frozenset[str] = frozenset(),
    direct_strong_difficulties: frozenset[str] = frozenset(),
) -> dict:
    if direct_weak_difficulties & direct_strong_difficulties:
        raise ValueError("a difficulty cannot be both direct-weak and direct-strong")
    weak = _indexed(weak_generation.get("measurements") or [], "weak generation")
    strong = _indexed(strong_generation.get("measurements") or [], "strong generation")
    weak_eval = _indexed(weak_evaluation.get("per_task") or [], "weak evaluation")
    strong_eval = _indexed(strong_evaluation.get("per_task") or [], "strong evaluation")
    judge = _indexed(judgments.get("measurements") or [], "judgments")
    ids = sorted(set(weak) & set(strong) & set(weak_eval) & set(strong_eval) & set(judge))
    expected = set(weak_eval)
    if set(ids) != expected:
        missing = sorted(expected - set(ids))
        raise ValueError(f"paired cascade is missing ids: {missing[:5]}")

    rows = []
    for question_id in ids:
        score = float(judge[question_id]["escalation_score"])
        difficulty = weak[question_id]["difficulty"]
        if difficulty in direct_strong_difficulties:
            route_mode = "direct_strong"
            escalated = True
            used_judge = False
            used_weak = False
        elif difficulty in direct_weak_difficulties:
            route_mode = "direct_weak"
            escalated = False
            used_judge = False
            used_weak = True
        else:
            route_mode = "jev_cascade"
            escalated = meets_escalation_threshold(score, threshold)
            used_judge = True
            used_weak = True
        weak_passed = bool(weak_eval[question_id]["passed"])
        strong_passed = bool(strong_eval[question_id]["passed"])
        judgment = judge[question_id].get("judgment") or {}
        weak_raw_latency = weak[question_id]["worker"].get("latency_ms")
        strong_raw_latency = strong[question_id]["worker"].get("latency_ms")
        weak_latency = float(weak_raw_latency) if weak_raw_latency is not None else None
        strong_latency = float(strong_raw_latency) if strong_raw_latency is not None else None
        judge_latency = float(judgment.get("latency_ms", 0.0))
        rows.append(
            {
                "question_id": question_id,
                "difficulty": difficulty,
                "route_mode": route_mode,
                "escalation_score": score,
                "escalated": escalated,
                "weak_passed": weak_passed,
                "strong_passed": strong_passed,
                "cascade_passed": strong_passed if escalated else weak_passed,
                "oracle_passed": weak_passed or strong_passed,
                "weak_cost_usd": float(weak[question_id]["worker_cost_usd"]),
                "strong_cost_usd": float(strong[question_id]["worker_cost_usd"]),
                "judge_cost_usd": float(judge[question_id].get("jev_cost_usd", 0.0)),
                "weak_latency_ms": weak_latency,
                "strong_latency_ms": strong_latency,
                "judge_latency_ms": judge_latency,
                "cascade_sequential_latency_ms": (
                    (weak_latency if used_weak else 0.0)
                    + (judge_latency if used_judge else 0.0)
                    + (strong_latency if escalated else 0.0)
                    if (not used_weak or weak_latency is not None)
                    and (not escalated or strong_latency is not None)
                    else None
                ),
                "policy_weak_cost_usd": float(weak[question_id]["worker_cost_usd"])
                if used_weak
                else 0.0,
                "policy_strong_cost_usd": float(strong[question_id]["worker_cost_usd"])
                if escalated
                else 0.0,
                "policy_judge_cost_usd": float(judge[question_id].get("jev_cost_usd", 0.0))
                if used_judge
                else 0.0,
            }
        )

    total = len(rows)
    weak_passed = sum(row["weak_passed"] for row in rows)
    strong_passed = sum(row["strong_passed"] for row in rows)
    cascade_passed = sum(row["cascade_passed"] for row in rows)
    oracle_passed = sum(row["oracle_passed"] for row in rows)
    escalated = [row for row in rows if row["escalated"]]
    weak_failures = [row for row in rows if not row["weak_passed"]]
    caught = [row for row in weak_failures if row["escalated"]]
    false_escalations = [row for row in escalated if row["weak_passed"]]
    weak_cost = sum(row["weak_cost_usd"] for row in rows)
    strong_cost = sum(row["strong_cost_usd"] for row in rows)
    judge_cost = sum(row["policy_judge_cost_usd"] for row in rows)
    policy_weak_cost = sum(row["policy_weak_cost_usd"] for row in rows)
    escalated_strong_cost = sum(row["policy_strong_cost_usd"] for row in rows)
    cascade_cost = policy_weak_cost + judge_cost + escalated_strong_cost

    by_difficulty: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_difficulty[row["difficulty"]].append(row)

    return {
        "suite": "livecodebench-openrouter-paired-cascade",
        "official_checker": bool(
            weak_evaluation.get("official_checker") and strong_evaluation.get("official_checker")
        ),
        "threshold": threshold,
        "policy": {
            "direct_weak_difficulties": sorted(direct_weak_difficulties),
            "direct_strong_difficulties": sorted(direct_strong_difficulties),
            "other_difficulties": "weak_then_jev_then_optional_strong",
        },
        "tasks": total,
        "quality": {
            "weak": {"passed": weak_passed, "pass_at_1": weak_passed / total, "95ci_wilson": wilson(weak_passed, total)},
            "strong": {"passed": strong_passed, "pass_at_1": strong_passed / total, "95ci_wilson": wilson(strong_passed, total)},
            "cascade": {"passed": cascade_passed, "pass_at_1": cascade_passed / total, "95ci_wilson": wilson(cascade_passed, total)},
            "paired_oracle": {"passed": oracle_passed, "pass_at_1": oracle_passed / total},
        },
        "routing": {
            "strong_calls": len(escalated),
            "strong_call_rate": len(escalated) / total,
            "weak_failures": len(weak_failures),
            "caught_weak_failures": len(caught),
            "failure_recall": len(caught) / len(weak_failures) if weak_failures else None,
            "false_escalations": len(false_escalations),
            "false_escalation_rate_among_weak_passes": (
                len(false_escalations) / weak_passed if weak_passed else None
            ),
            "missed_failure_ids": [row["question_id"] for row in weak_failures if not row["escalated"]],
        },
        "cost_usd": {
            "weak_all": weak_cost,
            "strong_all": strong_cost,
            "policy_weak": policy_weak_cost,
            "judge_all": judge_cost,
            "escalated_strong": escalated_strong_cost,
            "cascade": cascade_cost,
            "savings_vs_strong": strong_cost - cascade_cost,
            "savings_vs_strong_rate": 1.0 - cascade_cost / strong_cost,
            "strong_to_cascade_multiple": strong_cost / cascade_cost,
        },
        "latency": {
            "weak_worker": _latencies([row["weak_latency_ms"] for row in rows]),
            "strong_worker": _latencies([row["strong_latency_ms"] for row in rows]),
            "judge": _latencies([row["judge_latency_ms"] for row in rows]),
            "cascade_sequential": _latencies(
                [row["cascade_sequential_latency_ms"] for row in rows]
            ),
        },
        "by_difficulty": {
            difficulty: {
                "tasks": len(items),
                "weak_passed": sum(row["weak_passed"] for row in items),
                "strong_passed": sum(row["strong_passed"] for row in items),
                "cascade_passed": sum(row["cascade_passed"] for row in items),
                "strong_calls": sum(row["escalated"] for row in items),
            }
            for difficulty, items in sorted(by_difficulty.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze an official paired OpenRouter cascade")
    parser.add_argument("--weak-generation", required=True)
    parser.add_argument("--weak-evaluation", required=True)
    parser.add_argument("--strong-generation", required=True)
    parser.add_argument("--strong-evaluation", required=True)
    parser.add_argument("--judgments", required=True)
    parser.add_argument("--threshold", required=True, type=float)
    parser.add_argument("--direct-weak-difficulty", action="append", default=[])
    parser.add_argument("--direct-strong-difficulty", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    report = analyze(
        load(args.weak_generation),
        load(args.weak_evaluation),
        load(args.strong_generation),
        load(args.strong_evaluation),
        load(args.judgments),
        threshold=args.threshold,
        direct_weak_difficulties=frozenset(args.direct_weak_difficulty),
        direct_strong_difficulties=frozenset(args.direct_strong_difficulty),
    )
    destination = Path(args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
