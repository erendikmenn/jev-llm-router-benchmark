from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal, InvalidOperation
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
    if task.metric == "choice_exact":
        expected = str(task.expected).strip().upper()
        cleaned = output.strip().upper()
        direct = re.fullmatch(r"[\s\(\[\{]*([A-D])[\s\.\)\]\}:;!]*", cleaned)
        if direct:
            return float(direct.group(1) == expected)
        explicit = re.search(r"(?:ANSWER|OPTION|CHOICE)\s*(?:IS|:)?\s*[\(\[]?([A-D])\b", cleaned)
        return float(bool(explicit and explicit.group(1) == expected))
    if task.metric == "numeric_exact":
        return float(_numeric_value(output) == _numeric_value(str(task.expected)))
    raise ValueError(f"unknown metric: {task.metric}")


def _numeric_value(value: str) -> Decimal | None:
    normalized = value.replace("−", "-").replace("–", "-")
    matches = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", normalized)
    if not matches:
        return None
    try:
        return Decimal(matches[-1].replace(",", ""))
    except InvalidOperation:
        return None


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
        command = _sandboxed_python_command(script, Path(temp_dir))
        try:
            completed = subprocess.run(
                command,
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
        if completed.returncode != 0 and os.getenv("JEV_SANDBOX_DEBUG") == "1":
            stderr = completed.stderr.decode("utf-8", errors="replace")
            print(
                f"sandbox command failed ({completed.returncode}): {command!r}\n{stderr}",
                file=sys.stderr,
            )
    return float(completed.returncode == 0)


def sandbox_backend() -> str:
    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        return "sandbox-exec"
    if platform.system() == "Linux" and shutil.which("bwrap"):
        return "bubblewrap"
    return "unavailable"


def _sandboxed_python_command(script: Path, temp_dir: Path) -> list[str]:
    backend = sandbox_backend()
    python_command = [sys.executable, "-B", "-I", "-S", str(script)]
    if backend == "sandbox-exec":
        profile = "(version 1)(allow default)(deny network*)(deny file-write*)"
        return ["sandbox-exec", "-p", profile, *python_command]
    if backend == "bubblewrap":
        sandbox_dir = "/workspace"
        sandbox_script = f"{sandbox_dir}/candidate.py"
        return [
            "bwrap",
            "--unshare-net",
            "--die-with-parent",
            "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--proc", "/proc",
            "--tmpfs", "/tmp",
            "--dir", sandbox_dir,
            "--ro-bind", str(script), sandbox_script,
            "--chdir", sandbox_dir,
            sys.executable, "-B", "-I", "-S", sandbox_script,
        ]
    raise RuntimeError(
        "No network-isolating code sandbox available; install bubblewrap on Linux."
    )
