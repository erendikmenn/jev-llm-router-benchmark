from __future__ import annotations

import json
from pathlib import Path

from .config import AppConfig
from .livecodebench_runner import (
    LiveCodeBenchTask,
    extract_livecodebench_code,
    livecodebench_prompt,
)
from .models import GenerationRequest, GenerationResult
from .openrouter_lcb_runner import (
    _SYSTEM,
    _attempt_cost,
    estimate_tier_request_cost,
)
from .providers.base import ProviderError
from .providers.openrouter import OpenRouterChatProvider
from .solution_verifier import (
    OpenRouterSolutionJudgeProvider,
    meets_escalation_threshold,
)


_JEV_CALL_RESERVE_USD = 0.01


def _receipt(result: GenerationResult) -> dict:
    return {
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


def _write(output: Path, rows: list[dict], *, threshold: float, max_total_usd: float) -> dict:
    weak_cost = sum(float(row["weak_cost_usd"]) for row in rows)
    strong_cost = sum(float(row["strong_cost_usd"]) for row in rows)
    judge_cost = sum(float(row["jev_cost_usd"]) for row in rows)
    summary = {
        "suite": "livecodebench-openrouter-cascade",
        "transport": "openrouter_api",
        "threshold": threshold,
        "tasks_attempted": len(rows),
        "dispatch_completed": sum(row["status"] == "completed" for row in rows),
        "nonempty_code": sum(bool(row.get("code")) for row in rows),
        "strong_calls": sum(bool(row["escalated"]) for row in rows),
        "weak_cost_usd": weak_cost,
        "strong_cost_usd": strong_cost,
        "jev_cost_usd": judge_cost,
        "total_cost_usd": weak_cost + strong_cost + judge_cost,
        "max_total_usd": max_total_usd,
        "measurements": rows,
    }
    (output / "generation-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "predictions.json").write_text(
        json.dumps(
            [
                {"question_id": row["question_id"], "code_list": [row.get("code", "")]}
                for row in rows
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def run_livecodebench_openrouter_cascade(
    tasks: list[LiveCodeBenchTask],
    *,
    output_dir: str | Path,
    config: AppConfig,
    threshold: float,
    weak_role: str = "luna",
    strong_role: str = "sol",
    max_total_usd: float = 5.0,
    max_output_tokens: int = 2048,
) -> dict:
    """Generate with a weak tier, use Jev only for escalation, then optionally retry strong."""
    if max_total_usd <= 0:
        raise ValueError("max_total_usd must be positive")
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary_path = output / "generation-summary.json"
    rows = (
        list(json.loads(summary_path.read_text(encoding="utf-8")).get("measurements") or [])
        if summary_path.is_file()
        else []
    )
    completed = {row["question_id"] for row in rows if row.get("status") == "completed"}
    spent = sum(
        float(row.get("weak_cost_usd", 0.0))
        + float(row.get("strong_cost_usd", 0.0))
        + float(row.get("jev_cost_usd", 0.0))
        for row in rows
    )
    worker = OpenRouterChatProvider(config)
    judge = OpenRouterSolutionJudgeProvider(config)

    for index, task in enumerate(tasks, 1):
        if task.question_id in completed:
            print(f"[resume] openrouter-cascade {index}/{len(tasks)} {task.question_id}", flush=True)
            continue
        prompt = livecodebench_prompt(task)
        weak_reserve = estimate_tier_request_cost(
            config, weak_role, prompt=prompt, max_output_tokens=max_output_tokens
        )
        if spent + weak_reserve + _JEV_CALL_RESERVE_USD > max_total_usd:
            raise RuntimeError("estimated weak generation and judge would exceed cost cap")
        request = GenerationRequest(
            task.question_id,
            prompt,
            _SYSTEM,
            max_output_tokens,
            {"suite": "livecodebench", "difficulty": task.difficulty},
        )
        try:
            weak_result = worker.generate_tier(request, weak_role)
            weak_cost = float(weak_result.provider_cost_usd or 0.0)
            weak_code = extract_livecodebench_code(weak_result.text)
            weak_receipt = _receipt(weak_result)
            weak_error = None
        except ProviderError as exc:
            weak_cost = _attempt_cost(config, weak_role, exc)
            weak_code = ""
            weak_receipt = {"error": exc.kind, "attempts": len(exc.attempts)}
            weak_error = exc.kind
        spent += weak_cost

        judgment_payload = None
        jev_cost = 0.0
        if weak_error or not weak_code:
            escalated = True
            escalation_score = 1.0
            escalation_reason = "weak_empty_or_failed"
        else:
            try:
                judgment = judge.judge(task, weak_code)
                judgment_payload = judgment.to_dict()
                jev_cost = float(judgment.provider_cost_usd or 0.0)
                escalation_score = judgment.escalation_score
                escalated = meets_escalation_threshold(escalation_score, threshold)
                escalation_reason = "jev_threshold" if escalated else "jev_accept"
            except ProviderError as exc:
                escalation_score = 1.0
                escalated = True
                escalation_reason = f"jev_error_fallback:{exc.kind}"
        spent += jev_cost

        strong_cost = 0.0
        strong_receipt = None
        strong_code = ""
        strong_error = None
        if escalated:
            strong_reserve = estimate_tier_request_cost(
                config, strong_role, prompt=prompt, max_output_tokens=max_output_tokens
            )
            if spent + strong_reserve > max_total_usd:
                raise RuntimeError("estimated strong escalation would exceed cost cap")
            try:
                strong_result = worker.generate_tier(request, strong_role)
                strong_cost = float(strong_result.provider_cost_usd or 0.0)
                strong_code = extract_livecodebench_code(strong_result.text)
                strong_receipt = _receipt(strong_result)
            except ProviderError as exc:
                strong_cost = _attempt_cost(config, strong_role, exc)
                strong_receipt = {"error": exc.kind, "attempts": len(exc.attempts)}
                strong_error = exc.kind
            spent += strong_cost

        code = strong_code if strong_code else weak_code
        row = {
            "question_id": task.question_id,
            "difficulty": task.difficulty,
            "weak_role": weak_role,
            "strong_role": strong_role,
            "threshold": threshold,
            "escalation_score": escalation_score,
            "escalated": escalated,
            "escalation_reason": escalation_reason,
            "weak_cost_usd": weak_cost,
            "strong_cost_usd": strong_cost,
            "jev_cost_usd": jev_cost,
            "weak": weak_receipt,
            "strong": strong_receipt,
            "judgment": judgment_payload,
            "status": "completed" if code else "generation_failed",
            "error": strong_error or weak_error,
            "code": code,
        }
        rows.append(row)
        _write(output, rows, threshold=threshold, max_total_usd=max_total_usd)
        print(
            f"[progress] openrouter-cascade {index}/{len(tasks)} {task.question_id} "
            f"escalated={escalated} spent=${spent:.6f}",
            flush=True,
        )
    return _write(output, rows, threshold=threshold, max_total_usd=max_total_usd)
