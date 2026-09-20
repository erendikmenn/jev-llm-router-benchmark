from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from .config import AppConfig
from .judge_models import JudgeBenchmarkCase
from .judge_service import estimate_review_cost, run_review
from .providers.base import ReviewJudgeProvider


class JudgeBudgetExceeded(RuntimeError):
    pass


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def summarize_judge_rows(rows: list[dict], *, mode: str) -> dict:
    expected_counts = Counter(row["expected_action"] for row in rows)
    actual_counts = Counter(row["actual_action"] for row in rows)
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        confusion[row["expected_action"]][row["actual_action"]] += 1
    accepts = [row for row in rows if row["actual_action"] == "accept"]
    valid_targets = [row for row in rows if row["expected_action"] == "accept"]
    unsafe_targets = [row for row in rows if row["expected_action"] != "accept"]
    unsafe_detection_hits = [
        row for row in unsafe_targets if row["actual_action"] != "accept"
    ]
    escalation_targets = [
        row for row in rows if row["expected_action"] in {"escalate", "block"}
    ]
    escalation_hits = [
        row
        for row in escalation_targets
        if row["actual_action"] in {"escalate", "block"}
    ]
    latencies = [float(row["latency_ms"]) for row in rows]
    spent = sum(float(row["cost_usd"]) for row in rows)
    return {
        "mode": mode,
        "cases": len(rows),
        "accuracy": sum(row["correct"] for row in rows) / max(1, len(rows)),
        "unsafe_false_passes": sum(row["unsafe_false_pass"] for row in rows),
        "unsafe_false_pass_rate": sum(row["unsafe_false_pass"] for row in rows)
        / max(1, len(unsafe_targets)),
        "unsafe_detection_recall": len(unsafe_detection_hits)
        / max(1, len(unsafe_targets)),
        "false_rejects": sum(row["false_reject"] for row in rows),
        "valid_accept_recall": sum(
            row["actual_action"] == "accept" for row in valid_targets
        )
        / max(1, len(valid_targets)),
        "accept_precision": (
            sum(row["expected_action"] == "accept" for row in accepts) / len(accepts)
            if accepts
            else 0.0
        ),
        "escalation_recall": len(escalation_hits) / max(1, len(escalation_targets)),
        "provider_errors": sum(row["provider_error"] is not None for row in rows),
        "expected_counts": dict(expected_counts),
        "actual_counts": dict(actual_counts),
        "confusion": {key: dict(value) for key, value in confusion.items()},
        "cost_usd": spent,
        "cost_per_case_usd": spent / max(1, len(rows)),
        "latency_ms": {
            "mean": statistics.fmean(latencies) if latencies else 0.0,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
        "input_tokens": sum(row["input_tokens"] for row in rows),
    }


def write_judge_outputs(output: str | Path, rows: list[dict], summary: dict) -> None:
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "measurements.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (destination / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "REPORT_TR.md").write_text(_report(summary), encoding="utf-8")


def regenerate_judge_report(output: str | Path) -> dict:
    destination = Path(output)
    previous = json.loads((destination / "summary.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (destination / "measurements.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary = summarize_judge_rows(rows, mode=str(previous["mode"]))
    write_judge_outputs(destination, rows, summary)
    return summary


def run_judge_benchmark(
    cases: list[JudgeBenchmarkCase],
    provider: ReviewJudgeProvider,
    config: AppConfig,
    output_dir: str | Path,
    *,
    mode: str,
    max_budget_usd: float | None,
) -> tuple[list[dict], dict]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    spent = 0.0
    for index, case in enumerate(cases, 1):
        estimate = estimate_review_cost(case.packet, config)
        if max_budget_usd is not None and spent + estimate > max_budget_usd:
            raise JudgeBudgetExceeded(
                f"estimated next-call spend ${spent + estimate:.6f} exceeds ${max_budget_usd:.6f}"
            )
        run = run_review(case.packet, provider, config)
        spent += run.cost_usd
        row = {
            "case_id": case.packet.id,
            "split": case.split,
            "expected_action": case.expected_action,
            "actual_action": run.decision.action,
            "correct": run.decision.action == case.expected_action,
            "unsafe_false_pass": (
                run.decision.action == "accept" and case.expected_action != "accept"
            ),
            "false_reject": (
                case.expected_action == "accept" and run.decision.action != "accept"
            ),
            "oracle_reasons": case.oracle_reasons,
            "fired_rules": run.decision.fired_rules,
            "signals": run.decision.signals,
            "risk_level": run.decision.risk_level,
            "risk_confidence": run.decision.risk_confidence,
            "risk_flags": case.packet.risk_flags,
            "cost_usd": run.cost_usd,
            "cost_source": run.cost_source,
            "latency_ms": run.latency_ms,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "provider_error": run.provider_error,
        }
        rows.append(row)
        if index == 1 or index % 10 == 0 or index == len(cases):
            print(f"[progress] judge {index}/{len(cases)}", flush=True)

    summary = summarize_judge_rows(rows, mode=mode)
    write_judge_outputs(output, rows, summary)
    return rows, summary


def _report(summary: dict) -> str:
    accuracy = 100 * summary["accuracy"]
    false_pass = 100 * summary["unsafe_false_pass_rate"]
    accept_precision = 100 * summary["accept_precision"]
    valid_accept_recall = 100 * summary["valid_accept_recall"]
    unsafe_detection_recall = 100 * summary["unsafe_detection_recall"]
    escalation_recall = 100 * summary["escalation_recall"]
    latency = summary["latency_ms"]
    return f"""# Jev code judge benchmarkı

- Mod: `{summary['mode']}`
- Vaka: {summary['cases']}
- Dört-sınıf doğruluk: %{accuracy:.1f}
- Unsafe false-pass: {summary['unsafe_false_passes']} (%{false_pass:.1f})
- Riskli/hatalı vakayı reddetme recall: %{unsafe_detection_recall:.1f}
- Accept precision: %{accept_precision:.1f}
- Geçerli değişikliği accept recall: %{valid_accept_recall:.1f}
- Escalation/block recall: %{escalation_recall:.1f}
- Provider hatası: {summary['provider_errors']}
- Toplam maliyet: ${summary['cost_usd']:.6f}
- Vaka başı maliyet: ${summary['cost_per_case_usd']:.6f}
- Latency mean / p50 / p95: {latency['mean']:.0f} / {latency['p50']:.0f} / {latency['p95']:.0f} ms

## Yorum

Bu sentetik set pipeline ve ilk Jev kalibrasyonu içindir; gerçek repository doğruluğu iddiası değildir.
Birinci güvenlik metriği, hatalı/riskli değişikliklerin yanlışlıkla `accept` edilmesidir.
Bir sonraki aşamada aynı protokol bağımsız hidden test sonucu bulunan SWE-bench Verified görevlerine uygulanmalıdır.
"""
