from __future__ import annotations

import json
import time
from pathlib import Path

from .config import AppConfig
from .livecodebench_runner import (
    LiveCodeBenchTask,
    extract_livecodebench_code,
    livecodebench_prompt,
)
from .models import GenerationRequest, Task
from .pricing import estimate_tokens
from .providers.base import ProviderError
from .providers.openrouter import OpenRouterChatProvider
from .tiered_routing import OpenRouterTieredJevProvider, decide_tiered_route


_SYSTEM = (
    "You are an expert Python programmer. Solve the supplied programming problem. "
    "Return exactly one complete Python solution inside a fenced code block. Do not "
    "use or ask for private tests, answer keys, or benchmark solutions."
)


def _tier_price(config: AppConfig, tier: str) -> tuple[float, float]:
    raw = config.raw["openrouter_tier_pricing"][tier]
    return float(raw["input_usd_per_million"]), float(raw["output_usd_per_million"])


def estimate_tier_request_cost(
    config: AppConfig,
    tier: str,
    *,
    prompt: str,
    max_output_tokens: int,
) -> float:
    input_rate, output_rate = _tier_price(config, tier)
    return (
        estimate_tokens(_SYSTEM + "\n" + prompt) * input_rate
        + max_output_tokens * output_rate
    ) / 1_000_000


def _attempt_cost(config: AppConfig, tier: str, exc: ProviderError) -> float:
    input_rate, output_rate = _tier_price(config, tier)
    return sum(
        (
            attempt.usage.input_tokens * input_rate
            + attempt.usage.output_tokens * output_rate
        )
        / 1_000_000
        for attempt in exc.attempts
    )


def _write_summary(output: Path, rows: list[dict], *, max_total_usd: float) -> dict:
    worker = sum(float(row.get("worker_cost_usd", 0.0)) for row in rows)
    routing = sum(float(row.get("jev_route_cost_usd", 0.0)) for row in rows)
    summary = {
        "suite": "livecodebench",
        "transport": "openrouter_api",
        "tasks_attempted": len(rows),
        "dispatch_completed": sum(row["status"] == "completed" for row in rows),
        "nonempty_code": sum(bool(row.get("code")) for row in rows),
        "worker_cost_usd": worker,
        "jev_route_cost_usd": routing,
        "total_cost_usd": worker + routing,
        "max_total_usd": max_total_usd,
        "measurements": rows,
    }
    (output / "generation-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    predictions = [
        {"question_id": row["question_id"], "code_list": [row.get("code", "")]}
        for row in rows
    ]
    (output / "predictions.json").write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def run_livecodebench_openrouter(
    tasks: list[LiveCodeBenchTask],
    *,
    output_dir: str | Path,
    config: AppConfig,
    forced_role: str | None = None,
    max_total_usd: float = 5.0,
    max_output_tokens: int = 2048,
) -> dict:
    """Run an oracle-isolated LiveCodeBench arm entirely through OpenRouter."""
    if max_total_usd <= 0:
        raise ValueError("max_total_usd must be positive")
    if max_output_tokens < 256:
        raise ValueError("max_output_tokens must be at least 256")
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
    # A failed first attempt is still the pass@1 result. Never silently resample it
    # on resume because that would inflate benchmark quality and hide its cost.
    completed = {row["question_id"] for row in rows}
    spent = sum(
        float(row.get("worker_cost_usd", 0.0))
        + float(row.get("jev_route_cost_usd", 0.0))
        for row in rows
    )
    worker = OpenRouterChatProvider(config)
    router = None if forced_role else OpenRouterTieredJevProvider(config)

    for index, task in enumerate(tasks, 1):
        if task.question_id in completed:
            print(f"[resume] openrouter-lcb {index}/{len(tasks)} {task.question_id}", flush=True)
            continue
        if spent >= max_total_usd:
            raise RuntimeError(
                f"OpenRouter cost cap reached: ${spent:.6f} >= ${max_total_usd:.6f}"
            )
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
                {"platform": task.platform, "requires_tools": False, "isolated_code": True},
                {},
                {},
            )
            try:
                decision = decide_tiered_route(
                    routing_task,
                    router.judge(routing_task),
                    isolated_code_strong_probability_threshold=float(
                        config.router["isolated_code_strong_probability_threshold"]
                    ),
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
        route_latency_ms = (time.perf_counter() - route_started) * 1000
        route_cost = float(route.get("judgment", {}).get("provider_cost_usd") or 0.0)
        reserved = estimate_tier_request_cost(
            config,
            role,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
        )
        if spent + route_cost + reserved > max_total_usd:
            raise RuntimeError(
                "estimated next OpenRouter call would exceed cost cap: "
                f"${spent + route_cost + reserved:.6f} > ${max_total_usd:.6f}"
            )
        request = GenerationRequest(
            task.question_id,
            prompt,
            _SYSTEM,
            max_output_tokens,
            {"suite": "livecodebench", "difficulty": task.difficulty},
        )
        try:
            result = worker.generate_tier(request, role)
            worker_cost = float(result.provider_cost_usd or 0.0)
            code = extract_livecodebench_code(result.text)
            status = "completed"
            error = None
            receipt = {
                "model_id": result.model_id,
                "provider": result.provider,
                "generation_id": result.generation_id,
                "usage": {
                    "input_tokens": result.usage.input_tokens,
                    "cached_input_tokens": result.usage.cached_input_tokens,
                    "output_tokens": result.usage.output_tokens,
                },
                "latency_ms": result.latency_ms,
                "ttft_ms": result.ttft_ms,
                "provider_cost_usd": result.provider_cost_usd,
            }
        except ProviderError as exc:
            worker_cost = _attempt_cost(config, role, exc)
            code = ""
            status = "generation_failed"
            error = exc.kind
            receipt = {
                "error": exc.kind,
                "retryable": exc.retryable,
                "attempts": len(exc.attempts),
            }
        row = {
            "question_id": task.question_id,
            "difficulty": task.difficulty,
            "selected_role": role,
            "route": route,
            "route_latency_ms": route_latency_ms,
            "jev_route_cost_usd": route_cost,
            "status": status,
            "error": error,
            "worker_cost_usd": worker_cost,
            "worker": receipt,
            "code": code,
        }
        rows.append(row)
        spent += route_cost + worker_cost
        (receipts / f"{task.question_id}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _write_summary(output, rows, max_total_usd=max_total_usd)
        print(
            f"[progress] openrouter-lcb {index}/{len(tasks)} {task.question_id} "
            f"spent=${spent:.6f}",
            flush=True,
        )
    return _write_summary(output, rows, max_total_usd=max_total_usd)
