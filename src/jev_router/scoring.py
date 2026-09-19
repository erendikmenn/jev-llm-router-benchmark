from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .models import Task


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip(" .,!?:;\n\t")


def score_output(task: Task, output: str) -> float:
    if task.metric == "exact_normalized":
        return float(_normalize(output) == _normalize(str(task.expected)))
    if task.metric in {"contains_all", "translation_keywords", "summary_keywords"}:
        expected = [str(item) for item in task.expected]
        if not expected:
            return 1.0
        haystack = _normalize(output)
        return sum(_normalize(item) in haystack for item in expected) / len(expected)
    if task.metric == "json_match":
        try:
            actual = json.loads(output)
        except json.JSONDecodeError:
            return 0.0
        expected: dict[str, Any] = task.expected
        if not expected:
            return 1.0
        return sum(actual.get(key) == value for key, value in expected.items()) / len(expected)
    if task.metric == "python_tests":
        return _score_python(task, output)
    raise ValueError(f"unknown metric: {task.metric}")


def _score_python(task: Task, output: str) -> float:
    source = re.sub(r"^```(?:python)?\s*|\s*```$", "", output.strip(), flags=re.I | re.S)
    assertions = "\n".join(f"assert {case['expression']}" for case in task.tests)
    program = f"{source}\n{assertions}\n"
    with tempfile.TemporaryDirectory(prefix="jev-router-code-") as temp_dir:
        script = Path(temp_dir) / "candidate.py"
        script.write_text(program, encoding="utf-8")

        def limit_resources() -> None:
            if sys.platform != "win32":
                import resource

                # Some macOS/Python combinations reject lowering a hard limit in
                # preexec. Apply every available limit independently; the parent
                # timeout remains mandatory on every platform.
                for resource_id, limit in (
                    (resource.RLIMIT_CPU, 1),
                    (resource.RLIMIT_AS, 512 * 1024 * 1024),
                    (resource.RLIMIT_FSIZE, 1024 * 1024),
                ):
                    try:
                        resource.setrlimit(resource_id, (limit, limit))
                    except (OSError, ValueError):
                        pass

        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"}
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-S", str(script)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2,
                check=False,
                env=env,
                preexec_fn=limit_resources if sys.platform != "win32" else None,
            )
        except subprocess.TimeoutExpired:
            return 0.0
    return float(completed.returncode == 0)
