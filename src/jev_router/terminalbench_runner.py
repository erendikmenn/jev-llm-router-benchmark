from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .codex_dispatch import CODEX_ROLES
from .config import AppConfig
from .models import Task
from .providers.base import ProviderError
from .tiered_routing import OpenRouterTieredJevProvider, decide_tiered_route


@dataclass(frozen=True)
class TerminalBenchTask:
    name: str
    instruction: str
    instruction_sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


def load_terminalbench_tasks(dataset_root: str | Path) -> list[TerminalBenchTask]:
    root = Path(dataset_root).resolve()
    tasks: list[TerminalBenchTask] = []
    for task_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        instruction_path = task_dir / "instruction.md"
        config_path = task_dir / "task.toml"
        if not instruction_path.is_file() or not config_path.is_file():
            continue
        instruction = instruction_path.read_text(encoding="utf-8")
        tasks.append(
            TerminalBenchTask(
                task_dir.name,
                instruction,
                hashlib.sha256(instruction.encode()).hexdigest(),
            )
        )
    if not tasks:
        raise ValueError(f"no Terminal-Bench tasks found under {root}")
    return tasks


def write_terminalbench_plan(
    tasks: list[TerminalBenchTask], output: str | Path, *, source_revision: str
) -> dict:
    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "suite": "terminal-bench-2",
        "source_revision": source_revision,
        "task_count": len(tasks),
        "tasks": [task.to_dict() for task in tasks],
        "oracle_paths_excluded": ["tests/", "solution/"],
        "selection_sha256": hashlib.sha256(
            "\n".join(task.name for task in tasks).encode()
        ).hexdigest(),
    }
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def load_terminalbench_plan(
    path: str | Path, *, offset: int = 0, limit: int | None = None
) -> list[TerminalBenchTask]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("tasks") or []
    if offset < 0 or (limit is not None and limit < 1):
        raise ValueError("offset must be non-negative and limit must be positive")
    selected = rows[offset:] if limit is None else rows[offset : offset + limit]
    return [TerminalBenchTask(**row) for row in selected]


def _write_summary(output: Path, rows: list[dict]) -> dict:
    summary = {
        "suite": "terminal-bench-2",
        "tasks_attempted": len(rows),
        "completed_harness_runs": sum(row["status"] == "completed" for row in rows),
        "jev_route_cost_usd": sum(row["jev_route_cost_usd"] for row in rows),
        "measurements": rows,
        "official_harness": "Harbor",
    }
    (output / "generation-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def run_terminalbench(
    tasks: list[TerminalBenchTask],
    *,
    dataset_root: str | Path,
    output_dir: str | Path,
    config: AppConfig,
    forced_role: str | None = None,
    execute: bool = True,
    timeout_seconds: float = 3600.0,
    max_jev_usd: float = 5.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict:
    """Route tasks through Jev and run official Harbor with the user's Codex auth."""
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipts = output / "receipts"
    receipts.mkdir(exist_ok=True)
    summary_path = output / "generation-summary.json"
    rows = (
        list(json.loads(summary_path.read_text(encoding="utf-8")).get("measurements") or [])
        if summary_path.is_file()
        else []
    )
    completed = {
        row["task_name"]
        for row in rows
        if row.get("status") == "completed" or (not execute and row.get("status") == "routed")
    }
    spent = sum(float(row.get("jev_route_cost_usd", 0.0)) for row in rows)
    environment = os.environ.copy()
    environment["CODEX_FORCE_AUTH_JSON"] = "1"

    for index, task in enumerate(tasks, 1):
        if task.name in completed:
            print(f"[resume] terminal-bench-2 {index}/{len(tasks)} {task.name}", flush=True)
            continue
        if spent >= max_jev_usd:
            raise RuntimeError(f"Jev cost cap reached: ${spent:.6f} >= ${max_jev_usd:.6f}")
        route_started = time.perf_counter()
        if forced_role:
            role = forced_role
            route = {"selected": role, "rule": "fixed_baseline"}
        else:
            routing_task = Task(
                task.name,
                "benchmark",
                "en",
                "coding",
                task.instruction,
                "official_harness",
                None,
                {"requires_tools": True, "environment": "container"},
                {},
                {},
            )
            try:
                decision = decide_tiered_route(
                    routing_task, OpenRouterTieredJevProvider(config).judge(routing_task)
                )
                role = decision.selected
                route = decision.to_dict()
            except ProviderError as exc:
                role = "astra"
                route = {
                    "selected": role,
                    "rule": f"jev_error_fallback:{exc.kind}",
                    "source": "fail_safe",
                }
        route_elapsed_ms = (time.perf_counter() - route_started) * 1000
        spec = CODEX_ROLES[role]
        job_name = f"{index:03d}-{task.name}-{role}"
        command = [
            "uvx",
            "harbor",
            "run",
            "--path",
            str(Path(dataset_root).resolve()),
            "--include-task-name",
            task.name,
            "--agent",
            "codex",
            "--model",
            spec.model,
            "--agent-kwarg",
            f"reasoning_effort={spec.reasoning_effort}",
            "--n-concurrent",
            "1",
            "--jobs-dir",
            str(output / "harbor-jobs"),
            "--job-name",
            job_name,
            "--yes",
        ]
        started = time.perf_counter()
        if execute:
            completed = runner(
                command,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
                env=environment,
            )
            status = "completed" if completed.returncode == 0 else "harness_failed"
            returncode = completed.returncode
            stderr = completed.stderr[-4000:]
        else:
            status = "routed"
            returncode = None
            stderr = ""
        row = {
            "task_name": task.name,
            "selected_role": role,
            "route": route,
            "route_latency_ms": route_elapsed_ms,
            "jev_route_cost_usd": route.get("judgment", {}).get("provider_cost_usd") or 0.0,
            "model": spec.model,
            "reasoning_effort": spec.reasoning_effort,
            "status": status,
            "returncode": returncode,
            "execution_elapsed_ms": (time.perf_counter() - started) * 1000,
            "harbor_job": str(output / "harbor-jobs" / job_name),
            "stderr_tail": stderr,
        }
        rows.append(row)
        spent += float(row["jev_route_cost_usd"])
        (receipts / f"{task.name}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _write_summary(output, rows)
        print(f"[progress] terminal-bench-2 {index}/{len(tasks)} {task.name}", flush=True)
    return _write_summary(output, rows)
