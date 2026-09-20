#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


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


def _group(rows: list[dict], field: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row[field])].append(row)
    result = []
    for name, items in sorted(groups.items()):
        passed = sum(bool(item["passed"]) for item in items)
        result.append(
            {
                field: name,
                "tasks": len(items),
                "passed": passed,
                "pass_at_1": passed / len(items),
                "pass_at_1_95ci_wilson": wilson(passed, len(items)),
                "execution_latency_p50_ms": percentile(
                    [float(item["execution_elapsed_ms"]) for item in items], 0.5
                ),
                "execution_latency_p95_ms": percentile(
                    [float(item["execution_elapsed_ms"]) for item in items], 0.95
                ),
            }
        )
    return result


def analyze(generation: dict, evaluation: dict) -> dict:
    measurements = generation.get("measurements") or []
    generated = {str(row["question_id"]): row for row in measurements}
    evaluated = evaluation.get("per_task") or []
    evaluated_ids = [str(row["question_id"]) for row in evaluated]
    if len(evaluated_ids) != len(set(evaluated_ids)):
        raise ValueError("duplicate evaluation question ids")
    missing = sorted(set(evaluated_ids) - generated.keys())
    if missing:
        raise ValueError(f"evaluation references unknown question ids: {missing[:5]}")

    rows = []
    for outcome in evaluated:
        measurement = generated[str(outcome["question_id"])]
        route = measurement.get("route") or {}
        rows.append(
            {
                "question_id": str(outcome["question_id"]),
                "passed": bool(outcome["passed"]),
                "selected_role": measurement["selected_role"],
                "difficulty": measurement["difficulty"],
                "route_rule": route.get("rule", "unknown"),
                "execution_elapsed_ms": float(measurement.get("execution_elapsed_ms", 0)),
                "route_latency_ms": float(measurement.get("route_latency_ms", 0)),
                "jev_route_cost_usd": float(measurement.get("jev_route_cost_usd", 0)),
                "codex_usage": measurement.get("codex_usage") or {},
            }
        )

    passed = sum(row["passed"] for row in rows)
    execution_latencies = [row["execution_elapsed_ms"] for row in rows]
    route_latencies = [row["route_latency_ms"] for row in rows]
    role_counts = Counter(row["selected_role"] for row in rows)
    failure_role_counts = Counter(row["selected_role"] for row in rows if not row["passed"])
    return {
        "suite": "livecodebench",
        "official_checker": bool(evaluation.get("official_checker")),
        "tasks": len(rows),
        "passed": passed,
        "pass_at_1": passed / len(rows) if rows else None,
        "pass_at_1_95ci_wilson": wilson(passed, len(rows)),
        "dispatch_status": dict(Counter(row.get("status", "unknown") for row in measurements)),
        "nonempty_code": sum(bool(row.get("code")) for row in measurements),
        "selected_role_counts": dict(role_counts),
        "failed_role_counts": dict(failure_role_counts),
        "by_selected_role": _group(rows, "selected_role"),
        "by_difficulty": _group(rows, "difficulty"),
        "by_route_rule": _group(rows, "route_rule"),
        "latency_ms": {
            "execution_mean": sum(execution_latencies) / len(execution_latencies)
            if execution_latencies
            else None,
            "execution_p50": percentile(execution_latencies, 0.5),
            "execution_p95": percentile(execution_latencies, 0.95),
            "route_mean": sum(route_latencies) / len(route_latencies)
            if route_latencies
            else None,
            "route_p50": percentile(route_latencies, 0.5),
            "route_p95": percentile(route_latencies, 0.95),
        },
        "codex_tokens": {
            field: sum(int(row["codex_usage"].get(field, 0)) for row in rows)
            for field in (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
            )
        },
        "jev_route_cost_usd": sum(row["jev_route_cost_usd"] for row in rows),
        "failed_question_ids": [row["question_id"] for row in rows if not row["passed"]],
        "interpretation_guardrails": {
            "tier_rates_are_not_causal": (
                "Harder tasks are preferentially routed to stronger tiers; compare tiers only with paired counterfactual runs."
            ),
            "luna_failures_are_underroute_candidates_not_proof": [
                row["question_id"]
                for row in rows
                if not row["passed"] and row["selected_role"] == "luna"
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize an officially evaluated LiveCodeBench Codex routing run"
    )
    parser.add_argument("--generation", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    generation = json.loads(Path(args.generation).read_text(encoding="utf-8"))
    evaluation = json.loads(Path(args.evaluation).read_text(encoding="utf-8"))
    summary = analyze(generation, evaluation)
    destination = Path(args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
