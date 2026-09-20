from __future__ import annotations

import json

import pytest

from jev_router.livecodebench_runner import (
    LiveCodeBenchTask,
    extract_livecodebench_code,
    livecodebench_prompt,
    load_livecodebench_tasks,
    merge_livecodebench_runs,
    run_livecodebench,
    write_livecodebench_plan,
)


def _row(question_id: str = "abc") -> dict:
    return {
        "question_title": "Sum",
        "question_content": "Read two integers and print their sum.",
        "platform": "codeforces",
        "question_id": question_id,
        "contest_id": "1",
        "contest_date": "2026-01-01T00:00:00",
        "starter_code": "",
        "difficulty": "easy",
        "public_test_cases": "PUBLIC ORACLE",
        "private_test_cases": "PRIVATE ORACLE",
        "metadata": "HIDDEN METADATA",
    }


def test_loader_excludes_all_oracle_fields(tmp_path):
    for index, name in enumerate(
        ("test.jsonl", "test2.jsonl", "test3.jsonl", "test4.jsonl", "test5.jsonl", "test6.jsonl")
    ):
        (tmp_path / name).write_text(json.dumps(_row(str(index))) + "\n")

    tasks = load_livecodebench_tasks(tmp_path)
    plan_path = tmp_path / "plan.json"
    manifest = write_livecodebench_plan(tasks, plan_path, source_revision="locked")
    serialized = plan_path.read_text()

    assert len(tasks) == 6
    assert manifest["oracle_fields_excluded"] == [
        "public_test_cases",
        "private_test_cases",
        "metadata",
    ]
    assert "ORACLE" not in serialized
    assert "HIDDEN METADATA" not in serialized


def test_prompt_contains_problem_but_no_test_data():
    prompt = livecodebench_prompt(LiveCodeBenchTask.from_dict(_row()))
    assert "Read two integers" in prompt
    assert "PRIVATE ORACLE" not in prompt
    assert "PUBLIC ORACLE" not in prompt


def test_extraction_matches_final_fenced_block():
    output = "first\n```python\nprint('wrong')\n```\nfinal\n```python\nprint('right')\n```"
    assert extract_livecodebench_code(output) == "print('right')"
    assert extract_livecodebench_code("no fence") == ""


def test_duplicate_ids_are_rejected(tmp_path):
    for name in ("test.jsonl", "test2.jsonl", "test3.jsonl", "test4.jsonl", "test5.jsonl", "test6.jsonl"):
        (tmp_path / name).write_text(json.dumps(_row()) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_livecodebench_tasks(tmp_path)


def test_route_only_run_resumes_without_duplicate_rows(tmp_path):
    task = LiveCodeBenchTask.from_dict(_row())
    first = run_livecodebench(
        [task],
        repository=tmp_path,
        output_dir=tmp_path / "out",
        config=object(),
        forced_role="luna",
        execute=False,
    )
    second = run_livecodebench(
        [task],
        repository=tmp_path,
        output_dir=tmp_path / "out",
        config=object(),
        forced_role="luna",
        execute=False,
    )

    assert first["tasks_attempted"] == 1
    assert second["tasks_attempted"] == 1


def test_merge_combines_disjoint_segments(tmp_path):
    inputs = []
    for index in range(2):
        path = tmp_path / f"segment-{index}.json"
        path.write_text(
            json.dumps(
                {
                    "measurements": [
                        {
                            "question_id": str(index),
                            "status": "completed",
                            "code": "print(1)",
                            "jev_route_cost_usd": 0.001,
                            "codex_usage": {},
                        }
                    ]
                }
            )
        )
        inputs.append(path)

    merged = merge_livecodebench_runs(inputs, tmp_path / "merged")

    assert merged["tasks_attempted"] == 2
    assert merged["nonempty_code"] == 2
