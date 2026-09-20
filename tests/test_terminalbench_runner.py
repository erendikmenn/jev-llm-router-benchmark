from __future__ import annotations

from jev_router.terminalbench_runner import (
    load_terminalbench_tasks,
    write_terminalbench_plan,
)


def test_terminalbench_plan_excludes_tests_and_solutions(tmp_path):
    task = tmp_path / "sample-task"
    task.mkdir()
    (task / "instruction.md").write_text("Implement the requested tool.")
    (task / "task.toml").write_text("version = '1.0'")
    (task / "tests").mkdir()
    (task / "tests" / "test_secret.py").write_text("SECRET ORACLE")
    (task / "solution").mkdir()
    (task / "solution" / "solve.sh").write_text("GOLD SOLUTION")

    tasks = load_terminalbench_tasks(tmp_path)
    output = tmp_path / "plan.json"
    manifest = write_terminalbench_plan(tasks, output, source_revision="locked")
    serialized = output.read_text()

    assert manifest["task_count"] == 1
    assert manifest["oracle_paths_excluded"] == ["tests/", "solution/"]
    assert "Implement the requested tool" in serialized
    assert "SECRET ORACLE" not in serialized
    assert "GOLD SOLUTION" not in serialized
