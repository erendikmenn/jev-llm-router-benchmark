#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
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


def _index(rows: list[dict], label: str) -> dict[str, dict]:
    result = {str(row["question_id"]): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate ids in {label}")
    return result


def analyze(
    routes: dict,
    weak_generation: dict,
    weak_evaluation: dict,
    strong_generation: dict,
    strong_evaluation: dict,
    *,
    threshold: float,
) -> dict:
    route = _index(routes.get("measurements") or [], "routes")
    weak = _index(weak_generation.get("measurements") or [], "weak generation")
    strong = _index(strong_generation.get("measurements") or [], "strong generation")
    weak_eval = _index(weak_evaluation.get("per_task") or [], "weak evaluation")
    strong_eval = _index(strong_evaluation.get("per_task") or [], "strong evaluation")
    ids = sorted(weak_eval)
    for label, values in (("routes", route), ("weak", weak), ("strong", strong), ("strong evaluation", strong_eval)):
        missing = sorted(set(ids) - set(values))
        if missing:
            raise ValueError(f"{label} missing ids: {missing[:5]}")

    rows = []
    for question_id in ids:
        judgment = route[question_id]["route"]["judgment"]
        strong_probability = 1.0 - float(judgment["probabilities"].get("luna", 0.0))
        selected_strong = strong_probability >= threshold - 1e-12
        worker = strong[question_id] if selected_strong else weak[question_id]
        passed = (
            bool(strong_eval[question_id]["passed"])
            if selected_strong
            else bool(weak_eval[question_id]["passed"])
        )
        worker_latency = worker["worker"].get("latency_ms")
        route_latency = float(route[question_id].get("route_latency_ms", 0.0))
        rows.append(
            {
                "question_id": question_id,
                "selected_role": "sol" if selected_strong else "luna",
                "strong_probability": strong_probability,
                "passed": passed,
                "worker_cost_usd": float(worker.get("worker_cost_usd", 0.0)),
                "route_cost_usd": float(route[question_id].get("jev_route_cost_usd", 0.0)),
                "end_to_end_latency_ms": (
                    route_latency + float(worker_latency)
                    if worker_latency is not None
                    else None
                ),
            }
        )

    tasks = len(rows)
    passed = sum(row["passed"] for row in rows)
    strong_calls = sum(row["selected_role"] == "sol" for row in rows)
    worker_cost = sum(row["worker_cost_usd"] for row in rows)
    route_cost = sum(row["route_cost_usd"] for row in rows)
    strong_baseline_cost = sum(float(strong[question_id]["worker_cost_usd"]) for question_id in ids)
    latency = [row["end_to_end_latency_ms"] for row in rows if row["end_to_end_latency_ms"] is not None]
    return {
        "suite": "livecodebench-openrouter-prompt-router",
        "official_checker": bool(weak_evaluation.get("official_checker") and strong_evaluation.get("official_checker")),
        "threshold": threshold,
        "tasks": tasks,
        "passed": passed,
        "pass_at_1": passed / tasks,
        "strong_baseline_passed": sum(bool(strong_eval[q]["passed"]) for q in ids),
        "weak_baseline_passed": sum(bool(weak_eval[q]["passed"]) for q in ids),
        "strong_calls": strong_calls,
        "strong_call_rate": strong_calls / tasks,
        "cost_usd": {
            "worker": worker_cost,
            "jev_route": route_cost,
            "total": worker_cost + route_cost,
            "strong_baseline": strong_baseline_cost,
            "savings_vs_strong_rate": 1.0 - (worker_cost + route_cost) / strong_baseline_cost,
        },
        "latency_ms": {
            "observed": len(latency),
            "mean": sum(latency) / len(latency) if latency else None,
            "p50": statistics.median(latency) if latency else None,
            "p95": percentile(latency, 0.95),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze calibrated Jev prompt routing on paired OpenRouter outputs")
    parser.add_argument("--routes", required=True)
    parser.add_argument("--weak-generation", required=True)
    parser.add_argument("--weak-evaluation", required=True)
    parser.add_argument("--strong-generation", required=True)
    parser.add_argument("--strong-evaluation", required=True)
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    report = analyze(
        load(args.routes),
        load(args.weak_generation),
        load(args.weak_evaluation),
        load(args.strong_generation),
        load(args.strong_evaluation),
        threshold=args.threshold,
    )
    destination = Path(args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
