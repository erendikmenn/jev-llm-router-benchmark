from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .codex_dispatch import build_codex_dispatch_plan, run_codex_dispatch
from .config import AppConfig
from .models import Task
from .providers.base import ProviderError
from .tiered_routing import OpenRouterTieredJevProvider, decide_tiered_route


_DATA_FILES = (
    "test.jsonl",
    "test2.jsonl",
    "test3.jsonl",
    "test4.jsonl",
    "test5.jsonl",
    "test6.jsonl",
)
_SAFE_FIELDS = (
    "question_title",
    "question_content",
    "platform",
    "question_id",
    "contest_id",
    "contest_date",
    "starter_code",
    "difficulty",
)


@dataclass(frozen=True)
class LiveCodeBenchTask:
    question_title: str
    question_content: str
    platform: str
    question_id: str
    contest_id: str
    contest_date: str
    starter_code: str
    difficulty: str

    @classmethod
    def from_dict(cls, row: dict) -> "LiveCodeBenchTask":
        safe = {field: str(row.get(field, "")) for field in _SAFE_FIELDS}
        task = cls(**safe)
        if not task.question_id.strip() or not task.question_content.strip():
            raise ValueError("LiveCodeBench row is missing its identity or question")
        return task

    def to_dict(self) -> dict:
        return asdict(self)


def load_livecodebench_tasks(
    dataset_dir: str | Path,
    *,
    release: str = "release_v6",
) -> list[LiveCodeBenchTask]:
    """Load only model-visible fields; test cases never leave this function."""
    if release == "release_v6":
        names = _DATA_FILES
    elif re.fullmatch(r"v[1-6]", release):
        index = int(release[1:])
        names = (_DATA_FILES[index - 1],)
    else:
        raise ValueError("release must be release_v6 or one of v1..v6")
    root = Path(dataset_dir).resolve()
    tasks: list[LiveCodeBenchTask] = []
    seen: set[str] = set()
    for name in names:
        source = root / name
        if not source.is_file():
            raise FileNotFoundError(source)
        with source.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                task = LiveCodeBenchTask.from_dict(row)
                if task.question_id in seen:
                    raise ValueError(f"duplicate question_id: {task.question_id}")
                seen.add(task.question_id)
                tasks.append(task)
    return tasks


def livecodebench_prompt(task: LiveCodeBenchTask) -> str:
    starter = (
        f"\nComplete the following starter code:\n```python\n{task.starter_code}\n```\n"
        if task.starter_code.strip()
        else ""
    )
    return (
        "You are an expert Python programmer. Solve the programming problem below. "
        "Return exactly one complete Python solution inside a fenced code block. "
        "Do not use or ask for private tests, an answer key, or benchmark solutions.\n\n"
        f"{task.question_content.strip()}\n"
        f"{starter}"
    )


def extract_livecodebench_code(model_output: str | None) -> str:
    """Match LiveCodeBench's generic extraction: content of the final code fence."""
    if not model_output:
        return ""
    lines = model_output.splitlines()
    fences = [index for index, line in enumerate(lines) if "```" in line]
    if len(fences) < 2:
        return ""
    return "\n".join(lines[fences[-2] + 1 : fences[-1]]).strip()


def write_livecodebench_plan(
    tasks: list[LiveCodeBenchTask], output: str | Path, *, source_revision: str
) -> dict:
    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = [task.to_dict() for task in tasks]
    manifest = {
        "schema_version": 1,
        "suite": "livecodebench",
        "release": "release_v6",
        "source_revision": source_revision,
        "tasks": rows,
        "task_count": len(rows),
        "oracle_fields_excluded": ["public_test_cases", "private_test_cases", "metadata"],
        "selection_sha256": hashlib.sha256(
            "\n".join(task.question_id for task in tasks).encode()
        ).hexdigest(),
    }
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def load_livecodebench_plan(
    path: str | Path, *, offset: int = 0, limit: int | None = None
) -> list[LiveCodeBenchTask]:
    if offset < 0 or (limit is not None and limit < 1):
        raise ValueError("offset must be non-negative and limit must be positive")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("tasks") or []
    selected = rows[offset:] if limit is None else rows[offset : offset + limit]
    return [LiveCodeBenchTask.from_dict(row) for row in selected]


def _write_outputs(output: Path, measurements: list[dict]) -> dict:
    predictions = [
        {"question_id": row["question_id"], "code_list": [row["code"]]}
        for row in measurements
    ]
    predictions_path = output / "predictions.json"
    predictions_path.write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = {
        "suite": "livecodebench",
        "tasks_attempted": len(measurements),
        "dispatch_completed": sum(row["status"] == "completed" for row in measurements),
        "nonempty_code": sum(bool(row["code"]) for row in measurements),
        "jev_route_cost_usd": sum(row["jev_route_cost_usd"] for row in measurements),
        "codex_input_tokens": sum(
            int(row["codex_usage"].get("input_tokens", 0)) for row in measurements
        ),
        "codex_output_tokens": sum(
            int(row["codex_usage"].get("output_tokens", 0)) for row in measurements
        ),
        "official_evaluation_required": True,
        "measurements": measurements,
    }
    (output / "generation-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def run_livecodebench(
    tasks: list[LiveCodeBenchTask],
    *,
    repository: str | Path,
    output_dir: str | Path,
    config: AppConfig,
    forced_role: str | None = None,
    execute: bool = True,
    timeout_seconds: float = 900.0,
    max_jev_usd: float = 5.0,
) -> dict:
    """Route and checkpoint independent pass@1 generations using local Codex auth."""
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipts = output / "receipts"
    receipts.mkdir(exist_ok=True)
    summary_path = output / "generation-summary.json"
    if summary_path.is_file():
        previous = json.loads(summary_path.read_text(encoding="utf-8"))
        measurements = list(previous.get("measurements") or [])
    else:
        measurements = []
    completed_ids = {
        row["question_id"]
        for row in measurements
        if row.get("status") == "completed" or (not execute and row.get("status") == "routed")
    }
    spent = sum(float(row.get("jev_route_cost_usd", 0.0)) for row in measurements)

    for index, task in enumerate(tasks, 1):
        if task.question_id in completed_ids:
            print(
                f"[resume] livecodebench {index}/{len(tasks)} {task.question_id}",
                flush=True,
            )
            continue
        if spent >= max_jev_usd:
            raise RuntimeError(f"Jev cost cap reached: ${spent:.6f} >= ${max_jev_usd:.6f}")
        prompt = livecodebench_prompt(task)
        route_started = time.perf_counter()
        if forced_role:
            role = forced_role
            route = {"selected": role, "rule": "fixed_baseline"}
        else:
            routing_task = Task(
                task.question_id,
                "benchmark",
                "en",
                "coding",
                task.question_content,
                "official_harness",
                None,
                {
                    "platform": task.platform,
                    "requires_tools": False,
                    "isolated_code": True,
                },
                {},
                {},
            )
            try:
                route_decision = decide_tiered_route(
                    routing_task, OpenRouterTieredJevProvider(config).judge(routing_task)
                )
                role = route_decision.selected
                route = route_decision.to_dict()
            except ProviderError as exc:
                role = "astra"
                route = {
                    "selected": role,
                    "rule": f"jev_error_fallback:{exc.kind}",
                    "source": "fail_safe",
                }
        route_elapsed_ms = (time.perf_counter() - route_started) * 1000
        if execute:
            dispatch = run_codex_dispatch(
                build_codex_dispatch_plan(repository, role, sandbox="read-only"),
                prompt,
                timeout_seconds=timeout_seconds,
            )
            receipt = dispatch.to_dict()
            code = extract_livecodebench_code(dispatch.final_message)
            status = "completed" if dispatch.returncode == 0 else "dispatch_failed"
            elapsed_ms = dispatch.elapsed_ms
            usage = dispatch.usage
        else:
            receipt = None
            code = ""
            status = "routed"
            elapsed_ms = 0.0
            usage = {}
        row = {
            "question_id": task.question_id,
            "difficulty": task.difficulty,
            "selected_role": role,
            "route": route,
            "route_latency_ms": route_elapsed_ms,
            "jev_route_cost_usd": route.get("judgment", {}).get("provider_cost_usd") or 0.0,
            "status": status,
            "execution_elapsed_ms": elapsed_ms,
            "codex_usage": usage,
            "code": code,
        }
        measurements.append(row)
        spent += float(row["jev_route_cost_usd"])
        (receipts / f"{task.question_id}.json").write_text(
            json.dumps({"measurement": row, "dispatch": receipt}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        _write_outputs(output, measurements)
        print(f"[progress] livecodebench {index}/{len(tasks)} {task.question_id}", flush=True)
    return _write_outputs(output, measurements)
