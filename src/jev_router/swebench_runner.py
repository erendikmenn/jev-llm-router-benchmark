from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .codex_dispatch import build_codex_dispatch_plan, run_codex_dispatch
from .config import AppConfig
from .models import Task
from .pipeline import run_coding_pipeline
from .providers.base import ProviderError, ReviewJudgeProvider
from .tiered_routing import OpenRouterTieredJevProvider, decide_tiered_route


_REPO_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_COMMIT = re.compile(r"^[0-9a-fA-F]{7,64}$")
ARMS = (
    "always-luna",
    "always-terra",
    "always-sol",
    "always-astra",
    "router-only",
    "router-judge",
)


@dataclass(frozen=True)
class SWEbenchTask:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str

    @classmethod
    def from_dict(cls, row: dict) -> "SWEbenchTask":
        values = {key: str(row.get(key, "")) for key in cls.__annotations__}
        task = cls(**values)
        if not task.instance_id or not _REPO_SLUG.fullmatch(task.repo):
            raise ValueError("invalid SWE-bench task identity")
        if not _COMMIT.fullmatch(task.base_commit):
            raise ValueError("invalid SWE-bench base commit")
        if not task.problem_statement.strip():
            raise ValueError("empty SWE-bench problem statement")
        return task


def load_swebench_plan(path: str | Path, split: str, limit: int | None) -> list[SWEbenchTask]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if split not in {"dev", "test"}:
        raise ValueError("split must be dev or test")
    rows = payload.get(split) or []
    if limit is not None:
        rows = rows[:limit]
    return [SWEbenchTask.from_dict(row) for row in rows]


def prepare_swebench_checkout(
    task: SWEbenchTask,
    destination: str | Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    target = Path(destination).resolve()
    if target.exists():
        status = runner(
            ["git", "-C", str(target), "status", "--porcelain"],
            text=True,
            capture_output=True,
            check=True,
        )
        head = runner(
            ["git", "-C", str(target), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        if status.stdout.strip() or head != task.base_commit:
            raise RuntimeError(f"existing checkout is not clean at the base commit: {target}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    runner(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            f"https://github.com/{task.repo}.git",
            str(target),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    runner(
        ["git", "-C", str(target), "checkout", "--detach", task.base_commit],
        text=True,
        capture_output=True,
        check=True,
    )
    return target


def _git_diff(repository: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), "diff", "--binary", "HEAD", "--"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout


def _task_prompt(task: SWEbenchTask) -> str:
    return (
        "Solve the following repository issue. Inspect the repository, implement the smallest "
        "complete fix, and run relevant existing tests. Do not look for or use a gold patch, "
        "test patch, FAIL_TO_PASS list, or benchmark answer key.\n\n"
        f"Instance: {task.instance_id}\nRepository: {task.repo}\n\n"
        f"Issue:\n{task.problem_statement}"
    )


def _usage_totals(execution: dict) -> dict[str, int]:
    usages: list[dict] = []
    if isinstance(execution.get("usage"), dict):
        usages.append(execution["usage"])
    for round_ in execution.get("rounds", []):
        usage = round_.get("dispatch", {}).get("usage", {})
        if isinstance(usage, dict):
            usages.append(usage)
    keys = {key for usage in usages for key in usage if isinstance(usage.get(key), int)}
    return {key: sum(int(usage.get(key, 0)) for usage in usages) for key in sorted(keys)}


def generate_swebench_arm(
    tasks: list[SWEbenchTask],
    *,
    arm: str,
    workspace_root: str | Path,
    output_dir: str | Path,
    config: AppConfig,
    review_provider: ReviewJudgeProvider | None = None,
    max_rounds: int = 3,
    max_review_usd: float = 0.05,
    timeout_seconds: float = 900.0,
) -> dict:
    if arm not in ARMS:
        raise ValueError(f"unknown SWE-bench arm: {arm}")
    if arm == "router-judge" and review_provider is None:
        raise ValueError("router-judge arm requires a review provider")
    workspace_root = Path(workspace_root).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipts_dir = output / "receipts"
    receipts_dir.mkdir(exist_ok=True)
    predictions: list[dict] = []
    measurements: list[dict] = []

    for index, task in enumerate(tasks, 1):
        workspace = prepare_swebench_checkout(
            task, workspace_root / arm / task.instance_id
        )
        route_started = time.perf_counter()
        if arm.startswith("always-"):
            role = arm.removeprefix("always-")
            route = {"selected": role, "rule": "fixed_baseline"}
        else:
            anonymous = Task(
                task.instance_id,
                "benchmark",
                "en",
                "coding",
                task.problem_statement,
                "official_harness",
                None,
                {"repository": task.repo, "requires_tools": True},
                {},
                {},
            )
            try:
                tiered = decide_tiered_route(
                    anonymous, OpenRouterTieredJevProvider(config).judge(anonymous)
                )
                role = tiered.selected
                route = tiered.to_dict()
            except ProviderError as exc:
                role = "astra"
                route = {
                    "selected": role,
                    "rule": f"jev_error_fallback:{exc.kind}",
                    "source": "fail_safe",
                }
        route_latency_ms = (time.perf_counter() - route_started) * 1000
        prompt = _task_prompt(task)
        if arm == "router-judge":
            pipeline = run_coding_pipeline(
                workspace,
                task=prompt,
                acceptance_criteria=(task.problem_statement,),
                initial_role=role,
                review_provider=review_provider,
                config=config,
                max_rounds=max_rounds,
                max_review_usd=max_review_usd,
            )
            execution = pipeline.to_dict()
            model_name = "+".join(round_.role for round_ in pipeline.rounds)
            elapsed_ms = pipeline.elapsed_ms
            status = pipeline.status
        else:
            plan = build_codex_dispatch_plan(workspace, role)
            receipt = run_codex_dispatch(plan, prompt, timeout_seconds=timeout_seconds)
            execution = receipt.to_dict()
            model_name = plan.role.model
            elapsed_ms = receipt.elapsed_ms
            status = "completed" if receipt.returncode == 0 else "dispatch_failed"
        patch = _git_diff(workspace)
        prediction = {
            "instance_id": task.instance_id,
            "model_name_or_path": f"jev-router/{arm}/{model_name}",
            "model_patch": patch,
        }
        predictions.append(prediction)
        measurement = {
            "instance_id": task.instance_id,
            "arm": arm,
            "selected_role": role,
            "route": route,
            "route_latency_ms": route_latency_ms,
            "execution_elapsed_ms": elapsed_ms,
            "codex_usage": _usage_totals(execution),
            "jev_route_cost_usd": (
                route.get("judgment", {}).get("provider_cost_usd") or 0.0
            ),
            "jev_review_cost_usd": execution.get("review_cost_usd", 0.0),
            "status": status,
            "patch_bytes": len(patch.encode("utf-8")),
            "empty_patch": not bool(patch.strip()),
        }
        measurements.append(measurement)
        (receipts_dir / f"{task.instance_id}.json").write_text(
            json.dumps(
                {"measurement": measurement, "execution": execution},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _write_generation_outputs(output, arm, predictions, measurements)
        print(f"[progress] {arm} {index}/{len(tasks)} {task.instance_id}", flush=True)

    return _write_generation_outputs(output, arm, predictions, measurements)


def _write_generation_outputs(
    output: Path,
    arm: str,
    predictions: list[dict],
    measurements: list[dict],
) -> dict:
    """Checkpoint official predictions and measurements after each completed task."""
    predictions_path = output / "predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as handle:
        for item in predictions:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    (output / "generation-summary.json").write_text(
        json.dumps(
            {
                "arm": arm,
                "tasks": len(measurements),
                "completed": sum(row["status"] in {"completed", "accepted"} for row in measurements),
                "empty_patches": sum(row["empty_patch"] for row in measurements),
                "measurements": measurements,
                "official_evaluation_required": True,
                "evaluation_command": (
                    f"uvx --from swebench swebench eval verified -p {predictions_path} "
                    f"--run-id {arm} -j 1"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"predictions": str(predictions_path), "measurements": measurements}
