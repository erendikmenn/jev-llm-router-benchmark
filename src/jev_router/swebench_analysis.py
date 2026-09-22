from __future__ import annotations

import json
from pathlib import Path
from statistics import median


TIERS = ("luna", "terra", "sol", "astra")
FIXED_ARMS = {f"always-{tier}": tier for tier in TIERS}
ROUTER_ARMS = {"router-only", "router-judge"}
PIPELINE_ARMS = {"router-judge", "balanced-trajectory"}


def _load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * probability)))
    return ordered[index]


def analyze_swebench_runs(
    generation_summaries: dict[str, str | Path],
    evaluation_reports: dict[str, str | Path],
) -> dict:
    """Join Codex receipts to official SWE-bench outcomes without inventing labels."""
    generations = {arm: _load(path) for arm, path in generation_summaries.items()}
    evaluations = {arm: _load(path) for arm, path in evaluation_reports.items()}
    unknown = (set(generations) | set(evaluations)) - (
        set(FIXED_ARMS) | ROUTER_ARMS | PIPELINE_ARMS
    )
    if unknown:
        raise ValueError(f"unknown arms: {sorted(unknown)}")
    if set(generations) != set(evaluations):
        raise ValueError("generation and evaluation arms must match")

    by_arm: dict[str, dict] = {}
    task_rows: dict[str, dict] = {}
    for arm, generation in generations.items():
        evaluation = evaluations[arm]
        submitted = set(evaluation.get("submitted_ids", []))
        resolved = set(evaluation.get("resolved_ids", []))
        errors = set(evaluation.get("error_ids", []))
        infra = set(evaluation.get("infra_failure_ids", []))
        measurements = {
            item["instance_id"]: item for item in generation.get("measurements", [])
        }
        measured_ids = set(measurements)
        if submitted != measured_ids:
            raise ValueError(
                f"{arm}: evaluator submitted IDs and generation measurements differ"
            )
        eligible = submitted - errors - infra
        latencies = [
            float(measurements[item]["execution_elapsed_ms"])
            for item in eligible
        ]
        route_cost = sum(
            float(measurements[item].get("jev_route_cost_usd", 0.0))
            for item in submitted
        )
        review_cost = sum(
            float(measurements[item].get("jev_review_cost_usd", 0.0))
            for item in submitted
        )
        usage_keys = {
            key
            for item in submitted
            for key, value in measurements[item].get("codex_usage", {}).items()
            if isinstance(value, int)
        }
        codex_usage = {
            key: sum(
                int(measurements[item].get("codex_usage", {}).get(key, 0))
                for item in submitted
            )
            for key in sorted(usage_keys)
        }
        by_arm[arm] = {
            "submitted": len(submitted),
            "officially_evaluable": len(eligible),
            "resolved": len(resolved & eligible),
            "pass_rate": len(resolved & eligible) / len(eligible) if eligible else None,
            "infra_or_evaluator_errors": len((errors | infra) & submitted),
            "mean_execution_elapsed_ms": _mean(latencies),
            "p50_execution_elapsed_ms": median(latencies) if latencies else None,
            "p95_execution_elapsed_ms": _percentile(latencies, 0.95),
            "codex_usage": codex_usage,
            "jev_cost_usd": route_cost + review_cost,
        }
        if arm in PIPELINE_ARMS:
            accepted = {
                task_id
                for task_id, measurement in measurements.items()
                if measurement.get("status") == "accepted"
            }
            accepted_evaluable = accepted & eligible
            rejected_evaluable = eligible - accepted
            true_accepts = accepted_evaluable & resolved
            false_accepts = accepted_evaluable - resolved
            false_nonaccepts = rejected_evaluable & resolved
            by_arm[arm]["judge"] = {
                "accepted": len(accepted_evaluable),
                "accepted_and_resolved": len(true_accepts),
                "unsafe_false_accept": len(false_accepts),
                "nonaccepted_but_resolved": len(false_nonaccepts),
                "accept_precision": (
                    len(true_accepts) / len(accepted_evaluable)
                    if accepted_evaluable
                    else None
                ),
                "resolved_recall": (
                    len(true_accepts) / len(resolved & eligible)
                    if resolved & eligible
                    else None
                ),
            }
            round_roles = [
                tuple(round_.get("role") for round_ in measurement.get("rounds", []))
                for measurement in measurements.values()
            ]
            by_arm[arm]["trajectory"] = {
                "tasks_with_sol_or_astra": sum(
                    any(role in {"sol", "astra"} for role in roles)
                    for roles in round_roles
                ),
                "tasks_luna_only": sum(roles == ("luna",) for roles in round_roles),
                "worker_rounds": sum(len(roles) for roles in round_roles),
                "review_calls": sum(
                    bool(round_.get("review_called"))
                    for measurement in measurements.values()
                    for round_ in measurement.get("rounds", [])
                ),
            }
        for task_id in submitted:
            task_rows.setdefault(task_id, {"instance_id": task_id, "arms": {}})["arms"][arm] = {
                "resolved": task_id in resolved,
                "evaluable": task_id in eligible,
                "selected_role": measurements[task_id].get("selected_role"),
            }

    routing_counts = {
        "oracle_covered": 0,
        "exact": 0,
        "under_routed": 0,
        "over_routed": 0,
        "no_fixed_tier_succeeded": 0,
    }
    for row in task_rows.values():
        fixed = row["arms"]
        if not all(arm in fixed and fixed[arm]["evaluable"] for arm in FIXED_ARMS):
            row["oracle_role"] = None
            row["oracle_status"] = "incomplete_fixed_matrix"
            continue
        successful = [
            tier for arm, tier in FIXED_ARMS.items() if fixed[arm]["resolved"]
        ]
        if not successful:
            row["oracle_role"] = None
            row["oracle_status"] = "no_fixed_tier_succeeded"
            routing_counts["no_fixed_tier_succeeded"] += 1
            continue
        oracle = min(successful, key=TIERS.index)
        row["oracle_role"] = oracle
        row["oracle_status"] = "observed_cheapest_success"
        routing_counts["oracle_covered"] += 1
        for arm in ROUTER_ARMS:
            if arm not in fixed or not fixed[arm]["evaluable"]:
                continue
            selected = fixed[arm]["selected_role"]
            label = (
                "exact"
                if selected == oracle
                else "under_routed"
                if TIERS.index(selected) < TIERS.index(oracle)
                else "over_routed"
            )
            fixed[arm]["routing_label"] = label
            routing_counts[label] += 1

    classified = routing_counts["exact"] + routing_counts["under_routed"] + routing_counts["over_routed"]
    return {
        "schema_version": 1,
        "truth_source": "official_swebench_evaluator",
        "arms": by_arm,
        "routing": {
            **routing_counts,
            "classified_router_decisions": classified,
            "exact_route_rate": routing_counts["exact"] / classified if classified else None,
            "under_route_rate": routing_counts["under_routed"] / classified if classified else None,
            "over_route_rate": routing_counts["over_routed"] / classified if classified else None,
        },
        "tasks": sorted(task_rows.values(), key=lambda item: item["instance_id"]),
        "limitations": [
            "The oracle is the cheapest fixed-tier run observed to pass; model stochasticity remains.",
            "Codex subscription usage is reported as tokens and latency, not invented API dollars.",
            "Infrastructure and evaluator errors are excluded from pass-rate denominators.",
            "Judge labels describe the final pipeline patch, not every intermediate retry patch.",
        ],
    }


def write_swebench_analysis(
    generation_summaries: dict[str, str | Path],
    evaluation_reports: dict[str, str | Path],
    output: str | Path,
) -> dict:
    report = analyze_swebench_runs(generation_summaries, evaluation_reports)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def merge_generation_summaries(paths: list[str | Path], output: str | Path) -> dict:
    payloads = [_load(path) for path in paths]
    arms = {payload.get("arm") for payload in payloads}
    if len(arms) != 1 or None in arms:
        raise ValueError("generation summaries must belong to one arm")
    measurements = [item for payload in payloads for item in payload.get("measurements", [])]
    ids = [item["instance_id"] for item in measurements]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate generation instance IDs")
    merged = {
        "arm": arms.pop(),
        "tasks": len(measurements),
        "completed": sum(
            item.get("status") in {"completed", "accepted"} for item in measurements
        ),
        "empty_patches": sum(bool(item.get("empty_patch")) for item in measurements),
        "measurements": measurements,
        "official_evaluation_required": True,
        "merged_from": [str(Path(path)) for path in paths],
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return merged


def merge_evaluation_reports(paths: list[str | Path], output: str | Path) -> dict:
    payloads = [_load(path) for path in paths]
    list_fields = (
        "submitted_ids",
        "completed_ids",
        "resolved_ids",
        "unresolved_ids",
        "infra_failure_ids",
        "ambiguous_failure_ids",
        "empty_patch_ids",
        "error_ids",
    )
    merged_lists = {
        field: sorted({item for payload in payloads for item in payload.get(field, [])})
        for field in list_fields
    }
    if sum(len(payload.get("submitted_ids", [])) for payload in payloads) != len(
        merged_lists["submitted_ids"]
    ):
        raise ValueError("duplicate evaluation instance IDs")
    merged = {
        "schema_version": 2,
        "total_instances": len(merged_lists["submitted_ids"]),
        "submitted_instances": len(merged_lists["submitted_ids"]),
        "completed_instances": len(merged_lists["completed_ids"]),
        "resolved_instances": len(merged_lists["resolved_ids"]),
        "unresolved_instances": len(merged_lists["unresolved_ids"]),
        "infra_failure_instances": len(merged_lists["infra_failure_ids"]),
        "ambiguous_failure_instances": len(merged_lists["ambiguous_failure_ids"]),
        "empty_patch_instances": len(merged_lists["empty_patch_ids"]),
        "error_instances": len(merged_lists["error_ids"]),
        **merged_lists,
        "merged_from": [str(Path(path)) for path in paths],
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return merged
