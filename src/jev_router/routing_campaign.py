from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from .config import AppConfig
from .models import Task
from .providers.base import ProviderError
from .swebench_runner import SWEbenchTask
from .tiered_routing import OpenRouterTieredJevProvider, decide_tiered_route


def _write_summary(output: Path, suite: str, rows: list[dict]) -> dict:
    distribution = Counter(row["selected_role"] for row in rows)
    summary = {
        "suite": suite,
        "tasks_routed": len(rows),
        "route_distribution": dict(sorted(distribution.items())),
        "jev_route_cost_usd": sum(float(row["jev_route_cost_usd"]) for row in rows),
        "mean_route_latency_ms": (
            sum(float(row["route_latency_ms"]) for row in rows) / len(rows) if rows else 0.0
        ),
        "measurements": rows,
    }
    (output / "routing-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def route_swebench_tasks(
    tasks: list[SWEbenchTask],
    *,
    suite: str,
    output_dir: str | Path,
    config: AppConfig,
    max_jev_usd: float = 5.0,
) -> dict:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipts = output / "receipts"
    receipts.mkdir(exist_ok=True)
    summary_path = output / "routing-summary.json"
    rows = (
        list(json.loads(summary_path.read_text(encoding="utf-8")).get("measurements") or [])
        if summary_path.is_file()
        else []
    )
    completed = {row["instance_id"] for row in rows}
    spent = sum(float(row.get("jev_route_cost_usd", 0.0)) for row in rows)
    provider = OpenRouterTieredJevProvider(config)

    for index, task in enumerate(tasks, 1):
        if task.instance_id in completed:
            print(f"[resume] {suite} {index}/{len(tasks)} {task.instance_id}", flush=True)
            continue
        if spent >= max_jev_usd:
            raise RuntimeError(f"Jev cost cap reached: ${spent:.6f} >= ${max_jev_usd:.6f}")
        routing_task = Task(
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
        started = time.perf_counter()
        try:
            decision = decide_tiered_route(routing_task, provider.judge(routing_task))
            role = decision.selected
            route = decision.to_dict()
        except ProviderError as exc:
            role = "astra"
            route = {
                "selected": role,
                "rule": f"jev_error_fallback:{exc.kind}",
                "source": "fail_safe",
            }
        row = {
            "instance_id": task.instance_id,
            "selected_role": role,
            "route": route,
            "route_latency_ms": (time.perf_counter() - started) * 1000,
            "jev_route_cost_usd": route.get("judgment", {}).get("provider_cost_usd") or 0.0,
        }
        rows.append(row)
        spent += float(row["jev_route_cost_usd"])
        (receipts / f"{task.instance_id}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _write_summary(output, suite, rows)
        print(f"[progress] {suite} {index}/{len(tasks)} {task.instance_id}", flush=True)
    return _write_summary(output, suite, rows)
