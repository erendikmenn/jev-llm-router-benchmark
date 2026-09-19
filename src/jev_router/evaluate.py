from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig
from .models import GenerationRequest, Measurement, RouteDecision, Task, Usage
from .pricing import estimate_request_cost, estimate_tokens, jev_cost, usage_cost
from .providers.base import GeneratorProvider, JevProvider, ProviderError
from .routers import fixed_router, jev_router, random_router, rule_router
from .scoring import score_output


SYSTEM_PROMPT = "Answer the user request directly. Follow all explicit constraints. Do not mention routing or evaluation."


class BudgetExceeded(RuntimeError):
    pass


class BudgetLedger:
    def __init__(self, limit_usd: float | None):
        self.limit_usd = limit_usd
        self.spent_usd = 0.0

    def add(self, amount: float) -> None:
        if self.limit_usd is not None and self.spent_usd + amount > self.limit_usd:
            raise BudgetExceeded(
                f"run cost ${self.spent_usd + amount:.6f} would exceed ${self.limit_usd:.6f} limit"
            )
        self.spent_usd += amount


def _attempt_usage(result_usage: Usage, attempts: tuple) -> Usage:
    if not attempts:
        return result_usage
    return Usage(
        input_tokens=sum(item.usage.input_tokens for item in attempts),
        cached_input_tokens=sum(item.usage.cached_input_tokens for item in attempts),
        output_tokens=sum(item.usage.output_tokens for item in attempts),
    )


def run_measurement(
    run_id: str,
    mode: str,
    baseline: str,
    task: Task,
    decision: RouteDecision,
    generator: GeneratorProvider,
    config: AppConfig,
    ledger: BudgetLedger,
) -> Measurement:
    router_cost = 0.0
    router_latency = 0.0
    if decision.jev:
        jev_usage = _attempt_usage(decision.jev.usage, decision.jev.attempts)
        router_cost = jev_cost(jev_usage, config)
        router_latency = decision.jev.latency_ms
        ledger.add(router_cost)
    elif decision.router_attempts:
        # A failed/timeout response may have been processed and billed even when
        # no usage body reached us. Use reported usage when present; otherwise
        # account conservatively with a clearly flagged input estimate.
        estimated_jev_input = estimate_tokens(
            task.prompt + config.cheap.profile + config.strong.profile
        ) + 180
        for attempt in decision.router_attempts:
            attempt_usage = attempt.usage
            if attempt_usage.input_tokens == 0 and attempt_usage.output_tokens == 0:
                attempt_usage = Usage(input_tokens=estimated_jev_input)
            router_cost += jev_cost(attempt_usage, config)
            router_latency += attempt.latency_ms
        ledger.add(router_cost)
    if decision.selected is None:
        return Measurement(
            run_id, mode, baseline, task.id, task.split, task.language, task.group,
            None, None, 0.0, 0.0, router_cost, router_cost, router_latency,
            router_latency, 0.0, None, False, decision.rejected_reason,
            decision.rule, "", {},
        )

    request = GenerationRequest(
        task_id=task.id,
        prompt=task.prompt,
        system=SYSTEM_PROMPT,
        max_output_tokens=int(task.constraints.get("max_output_tokens", config.experiment["max_output_tokens"])),
        metadata={"fixture": task.fixture},
    )
    selected = decision.selected
    fallback = False
    error: str | None = None
    total_target_cost = 0.0
    try:
        result = generator.generate(request, selected)
    except ProviderError as exc:
        if selected != "cheap":
            raise
        fallback = True
        failed_attempts = exc.attempts or (None,)
        for attempt in failed_attempts:
            if attempt is not None and (
                attempt.usage.input_tokens > 0 or attempt.usage.output_tokens > 0
            ):
                total_target_cost += usage_cost(attempt.usage, config.cheap)
            else:
                total_target_cost += estimate_request_cost(
                    task.prompt, request.max_output_tokens, config.cheap
                )
        error = f"cheap_{exc.kind}_fallback;failed_attempt_cost_estimated_if_usage_missing"
        selected = "strong"
        result = generator.generate(request, selected)
    model_config = getattr(config, selected)
    billed_usage = _attempt_usage(result.usage, result.attempts)
    total_target_cost += usage_cost(billed_usage, model_config)
    ledger.add(total_target_cost)
    quality = score_output(task, result.text)
    return Measurement(
        run_id=run_id,
        mode=mode,
        baseline=baseline,
        task_id=task.id,
        split=task.split,
        language=task.language,
        group=task.group,
        selected_role=selected,
        selected_model=result.model_id,
        quality=quality,
        target_cost_usd=total_target_cost,
        router_cost_usd=router_cost,
        total_cost_usd=total_target_cost + router_cost,
        latency_ms=router_latency + result.latency_ms,
        router_latency_ms=router_latency,
        target_latency_ms=result.latency_ms,
        ttft_ms=result.ttft_ms,
        fallback=fallback,
        error=error,
        route_rule=decision.rule,
        output_text=result.text,
        usage={
            "input_tokens": billed_usage.input_tokens,
            "cached_input_tokens": billed_usage.cached_input_tokens,
            "output_tokens": billed_usage.output_tokens,
        },
    )


def run_benchmark(
    tasks: list[Task],
    generator: GeneratorProvider,
    jev: JevProvider,
    config: AppConfig,
    threshold: float,
    output_dir: str | Path,
    mode: str = "fixture",
    max_budget_usd: float | None = None,
) -> tuple[list[Measurement], dict]:
    if mode == "live" and (max_budget_usd is None or max_budget_usd <= 0):
        raise ValueError("live mode requires a positive --max-usd hard limit")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ledger = BudgetLedger(max_budget_usd)
    jev_decisions = {task.id: jev_router(task, config, jev, threshold) for task in tasks}
    strong_rate = sum(
        decision.selected == "strong" for decision in jev_decisions.values()
    ) / max(1, len(tasks))
    baselines = ["always_strong", "always_cheap", "rule", "random_matched", "jev"]
    measurements: list[Measurement] = []
    for baseline in baselines:
        for task in tasks:
            if baseline == "always_strong":
                decision = fixed_router(task, "strong", config)
            elif baseline == "always_cheap":
                decision = fixed_router(task, "cheap", config)
            elif baseline == "rule":
                decision = rule_router(task, config)
            elif baseline == "random_matched":
                decision = random_router(task, config, strong_rate, int(config.experiment["seed"]))
            else:
                decision = jev_decisions[task.id]
            measurements.append(
                run_measurement(run_id, mode, baseline, task, decision, generator, config, ledger)
            )
    summary = summarize(measurements, int(config.experiment["seed"]))
    summary["run"] = {
        "run_id": run_id,
        "mode": mode,
        "task_count": len(tasks),
        "threshold": threshold,
        "jev_strong_rate": strong_rate,
        "budget_limit_usd": max_budget_usd,
        "ledger_spend_usd": ledger.spent_usd,
        "cost_kind": "calculated_from_fixture_usage" if mode == "fixture" else "calculated_from_provider_usage",
    }
    write_measurements(measurements, output_dir)
    path = Path(output_dir)
    (path / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return measurements, summary


def percentile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def paired_bootstrap_ci(
    baseline: dict[str, float], candidate: dict[str, float], seed: int, samples: int = 2000
) -> list[float]:
    ids = sorted(set(baseline) & set(candidate))
    if not ids:
        return [math.nan, math.nan]
    rng = random.Random(seed)
    diffs: list[float] = []
    for _ in range(samples):
        picked = [rng.choice(ids) for _ in ids]
        diffs.append(sum(candidate[item] - baseline[item] for item in picked) / len(picked))
    return [percentile(diffs, 0.025), percentile(diffs, 0.975)]


def summarize(measurements: list[Measurement], seed: int) -> dict:
    grouped: dict[str, list[Measurement]] = defaultdict(list)
    for measurement in measurements:
        grouped[measurement.baseline].append(measurement)
    strong_scores = {item.task_id: item.quality for item in grouped["always_strong"]}
    strong_total_cost = sum(item.total_cost_usd for item in grouped["always_strong"])
    result: dict = {"baselines": {}, "subgroups": {}}
    for name, rows in grouped.items():
        scores = {item.task_id: item.quality for item in rows}
        total_cost = sum(item.total_cost_usd for item in rows)
        successes = sum(item.quality >= 0.999 for item in rows)
        result["baselines"][name] = {
            "n": len(rows),
            "quality_mean": sum(scores.values()) / max(1, len(scores)),
            "quality_delta_vs_strong": (
                sum(scores.values()) / max(1, len(scores))
                - sum(strong_scores.values()) / max(1, len(strong_scores))
            ),
            "quality_delta_95ci": paired_bootstrap_ci(strong_scores, scores, seed),
            "success_rate": successes / max(1, len(rows)),
            "strong_selection_rate": sum(item.selected_role == "strong" for item in rows) / max(1, len(rows)),
            "fallback_rate": sum(item.fallback for item in rows) / max(1, len(rows)),
            "error_rate": sum(item.error is not None for item in rows) / max(1, len(rows)),
            "total_cost_usd": total_cost,
            "usd_per_request": total_cost / max(1, len(rows)),
            "usd_per_1000_requests": total_cost / max(1, len(rows)) * 1000,
            "usd_per_success": total_cost / successes if successes else None,
            "savings_vs_always_strong": 1 - total_cost / strong_total_cost if strong_total_cost else None,
            "latency_p50_ms": percentile([item.latency_ms for item in rows], 0.5),
            "latency_p95_ms": percentile([item.latency_ms for item in rows], 0.95),
            "router_latency_p50_ms": percentile([item.router_latency_ms for item in rows], 0.5),
            "target_latency_p50_ms": percentile([item.target_latency_ms for item in rows], 0.5),
        }
    for key_name, key_fn in {
        "language": lambda row: row.language,
        "group": lambda row: row.group,
    }.items():
        buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in measurements:
            buckets[key_fn(row)][row.baseline].append(row.quality)
        result["subgroups"][key_name] = {
            bucket: {baseline: sum(values) / len(values) for baseline, values in baseline_values.items()}
            for bucket, baseline_values in buckets.items()
        }
    return result


def write_measurements(measurements: list[Measurement], output_dir: str | Path) -> None:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    dictionaries = [item.to_dict() for item in measurements]
    with (path / "measurements.jsonl").open("w", encoding="utf-8") as handle:
        for row in dictionaries:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    flat_rows = []
    for row in dictionaries:
        flat = {**row, "usage": json.dumps(row["usage"], sort_keys=True)}
        flat_rows.append(flat)
    with (path / "measurements.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0]) if flat_rows else [])
        if flat_rows:
            writer.writeheader()
            writer.writerows(flat_rows)
