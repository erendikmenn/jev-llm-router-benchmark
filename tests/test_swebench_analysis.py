from __future__ import annotations

import json

from jev_router.swebench_analysis import (
    analyze_swebench_runs,
    merge_evaluation_reports,
    merge_generation_summaries,
)


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_analysis_uses_official_results_and_classifies_routes(tmp_path):
    generations = {}
    evaluations = {}
    resolved_by_arm = {
        "always-luna": [],
        "always-terra": ["task"],
        "always-sol": ["task"],
        "always-astra": ["task"],
        "router-only": ["task"],
    }
    role_by_arm = {
        "always-luna": "luna",
        "always-terra": "terra",
        "always-sol": "sol",
        "always-astra": "astra",
        "router-only": "sol",
    }
    for arm, resolved in resolved_by_arm.items():
        generations[arm] = _write(
            tmp_path,
            f"{arm}-generation.json",
            {
                "measurements": [
                    {
                        "instance_id": "task",
                        "selected_role": role_by_arm[arm],
                        "execution_elapsed_ms": 100,
                        "codex_usage": {"input_tokens": 123, "output_tokens": 7},
                        "jev_route_cost_usd": 0.001 if arm == "router-only" else 0,
                    }
                ]
            },
        )
        evaluations[arm] = _write(
            tmp_path,
            f"{arm}-evaluation.json",
            {
                "submitted_ids": ["task"],
                "resolved_ids": resolved,
                "error_ids": [],
                "infra_failure_ids": [],
            },
        )

    report = analyze_swebench_runs(generations, evaluations)

    assert report["tasks"][0]["oracle_role"] == "terra"
    assert report["tasks"][0]["arms"]["router-only"]["routing_label"] == "over_routed"
    assert report["routing"]["over_route_rate"] == 1.0
    assert report["arms"]["router-only"]["jev_cost_usd"] == 0.001
    assert report["arms"]["router-only"]["codex_usage"]["input_tokens"] == 123
    assert report["arms"]["router-only"]["p95_execution_elapsed_ms"] == 100


def test_analysis_excludes_infrastructure_errors(tmp_path):
    generation = _write(
        tmp_path,
        "generation.json",
        {"measurements": [{"instance_id": "task", "execution_elapsed_ms": 10}]},
    )
    evaluation = _write(
        tmp_path,
        "evaluation.json",
        {
            "submitted_ids": ["task"],
            "resolved_ids": [],
            "error_ids": ["task"],
            "infra_failure_ids": [],
        },
    )

    report = analyze_swebench_runs({"always-luna": generation}, {"always-luna": evaluation})

    assert report["arms"]["always-luna"]["pass_rate"] is None
    assert report["arms"]["always-luna"]["infra_or_evaluator_errors"] == 1


def test_judge_false_accept_is_measured_against_official_outcome(tmp_path):
    generation = _write(
        tmp_path,
        "judge-generation.json",
        {
            "measurements": [
                {
                    "instance_id": "task",
                    "status": "accepted",
                    "selected_role": "terra",
                    "execution_elapsed_ms": 10,
                }
            ]
        },
    )
    evaluation = _write(
        tmp_path,
        "judge-evaluation.json",
        {
            "submitted_ids": ["task"],
            "resolved_ids": [],
            "error_ids": [],
            "infra_failure_ids": [],
        },
    )

    report = analyze_swebench_runs({"router-judge": generation}, {"router-judge": evaluation})

    assert report["arms"]["router-judge"]["judge"]["unsafe_false_accept"] == 1
    assert report["arms"]["router-judge"]["judge"]["accept_precision"] == 0.0


def test_run_segments_merge_without_duplicate_instances(tmp_path):
    generation_paths = []
    evaluation_paths = []
    for index in range(2):
        task_id = f"task-{index}"
        generation_paths.append(
            _write(
                tmp_path,
                f"generation-{index}.json",
                {"arm": "always-luna", "measurements": [{"instance_id": task_id}]},
            )
        )
        evaluation_paths.append(
            _write(
                tmp_path,
                f"evaluation-{index}.json",
                {
                    "submitted_ids": [task_id],
                    "completed_ids": [task_id],
                    "resolved_ids": [task_id] if index else [],
                    "unresolved_ids": [] if index else [task_id],
                },
            )
        )

    generation = merge_generation_summaries(
        generation_paths, tmp_path / "generation-merged.json"
    )
    evaluation = merge_evaluation_reports(
        evaluation_paths, tmp_path / "evaluation-merged.json"
    )

    assert generation["tasks"] == 2
    assert evaluation["submitted_instances"] == 2
    assert evaluation["resolved_instances"] == 1
