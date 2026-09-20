from __future__ import annotations

import json

from jev_router.swebench_analysis import analyze_swebench_runs


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
