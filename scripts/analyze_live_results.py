#!/usr/bin/env python3
"""Analyze a live full-matrix run and optionally select a dev-only threshold."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n == 0:
        return [math.nan, math.nan]
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - spread), min(1.0, center + spread)]


def bootstrap_delta(left: list[float], right: list[float], seed: int = 20260919) -> list[float]:
    rng = random.Random(seed)
    n = len(left)
    values = []
    for _ in range(5000):
        indices = [rng.randrange(n) for _ in range(n)]
        values.append(sum(right[i] - left[i] for i in indices) / n)
    return [percentile(values, 0.025), percentile(values, 0.975)]


def mcnemar_exact(left: list[float], right: list[float]) -> dict:
    left_only = sum(a >= 0.999 and b < 0.999 for a, b in zip(left, right))
    right_only = sum(a < 0.999 and b >= 0.999 for a, b in zip(left, right))
    discordant = left_only + right_only
    if not discordant:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, i) for i in range(min(left_only, right_only) + 1)) / (2**discordant)
        p_value = min(1.0, 2 * tail)
    return {"left_only": left_only, "right_only": right_only, "p_value_two_sided": p_value}


def load_rows(directory: Path) -> tuple[list[dict], dict]:
    rows = [json.loads(line) for line in (directory / "measurements.jsonl").read_text().splitlines() if line]
    summary = json.loads((directory / "summary.json").read_text())
    return rows, summary


def matrix(rows: list[dict]) -> dict[str, dict[str, dict]]:
    result: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        result[row["task_id"]][row["baseline"]] = row
    return dict(result)


def threshold_curve(items: dict[str, dict[str, dict]]) -> list[dict]:
    curve = []
    for step in range(101):
        threshold = step / 100
        quality = cost = latency = strong_count = 0.0
        for policies in items.values():
            jev = policies["jev"]
            probability = jev["jev_strong_probability"]
            force_strong = probability is None or (jev["jev_confidence"] or 0) < 0.20
            role = "strong" if force_strong or probability >= threshold else "cheap"
            target = policies[f"always_{role}"]
            quality += target["quality"]
            cost += jev["router_cost_usd"] + target["target_cost_usd"]
            latency += jev["router_latency_ms"] + target["target_latency_ms"]
            strong_count += role == "strong"
        n = len(items)
        curve.append({
            "threshold": threshold,
            "quality": quality / n,
            "strong_rate": strong_count / n,
            "total_cost_usd": cost,
            "latency_mean_ms": latency / n,
        })
    strong_quality = sum(p["always_strong"]["quality"] for p in items.values()) / len(items)
    for point in curve:
        point["quality_loss_pp_vs_strong"] = (strong_quality - point["quality"]) * 100
    return curve


def select_threshold(curve: list[dict], max_loss_pp: float) -> dict:
    feasible = [point for point in curve if point["quality_loss_pp_vs_strong"] <= max_loss_pp]
    candidates = feasible or curve
    return min(candidates, key=lambda point: (point["total_cost_usd"], point["strong_rate"], -point["threshold"]))


def probability_diagnostics(items: dict[str, dict[str, dict]]) -> dict:
    buckets: dict[int, list[tuple[float, float]]] = defaultdict(list)
    pairs = []
    for policies in items.values():
        probability = policies["jev"]["jev_strong_probability"]
        if probability is None:
            continue
        needed = float(policies["always_strong"]["quality"] > policies["always_cheap"]["quality"])
        bucket = min(9, int(probability * 10))
        buckets[bucket].append((probability, needed))
        pairs.append((probability, needed))
    brier = sum((probability - needed) ** 2 for probability, needed in pairs) / max(1, len(pairs))
    calibration = []
    ece = 0.0
    for bucket in range(10):
        values = buckets.get(bucket, [])
        if not values:
            continue
        predicted = sum(item[0] for item in values) / len(values)
        observed = sum(item[1] for item in values) / len(values)
        ece += len(values) / len(pairs) * abs(predicted - observed)
        calibration.append({"range": f"{bucket / 10:.1f}-{(bucket + 1) / 10:.1f}", "n": len(values), "predicted": predicted, "observed_need": observed})
    return {"brier_score": brier, "expected_calibration_error": ece, "bins": calibration}


def analyze(directory: Path, max_loss_pp: float) -> dict:
    rows, summary = load_rows(directory)
    items = matrix(rows)
    ids = sorted(items)
    strong = [items[item]["always_strong"]["quality"] for item in ids]
    cheap = [items[item]["always_cheap"]["quality"] for item in ids]
    jev = [items[item]["jev"]["quality"] for item in ids]
    random_matched = [items[item]["random_matched"]["quality"] for item in ids]
    cases = Counter()
    for item in ids:
        policies = items[item]
        s = policies["always_strong"]["quality"] >= 0.999
        c = policies["always_cheap"]["quality"] >= 0.999
        selected = policies["jev"]["selected_role"]
        if policies["jev"]["route_rule"].startswith("jev_error_fallback:"):
            cases["router_error_fallback"] += 1
        cases["both_correct" if s and c else "only_strong_correct" if s else "only_cheap_correct" if c else "neither_correct"] += 1
        if selected == "cheap" and s and not c:
            cases["unsafe_cheap"] += 1
        if selected == "strong" and s and not c:
            cases["recovered_by_strong"] += 1
        if selected == "strong" and c:
            cases["needless_strong"] += 1
    curve = threshold_curve(items)
    chosen = select_threshold(curve, max_loss_pp)
    selected_strong = [item for item in ids if items[item]["jev"]["selected_role"] == "strong"]
    strong_needed = [item for item in ids if items[item]["always_strong"]["quality"] > items[item]["always_cheap"]["quality"]]
    true_positive = len(set(selected_strong) & set(strong_needed))
    router_cost = sum(items[item]["jev"]["router_cost_usd"] for item in ids)
    oracle_quality = 0.0
    oracle_target_cost = 0.0
    for item in ids:
        cheap_row = items[item]["always_cheap"]
        strong_row = items[item]["always_strong"]
        oracle_row = cheap_row if cheap_row["quality"] >= strong_row["quality"] else strong_row
        oracle_quality += oracle_row["quality"]
        oracle_target_cost += oracle_row["target_cost_usd"]
    baselines = {}
    for name in ("always_strong", "always_cheap", "rule", "random_matched", "jev"):
        values = [items[item][name]["quality"] for item in ids]
        successes = sum(value >= 0.999 for value in values)
        baselines[name] = {
            **summary["baselines"][name],
            "accuracy_95ci_wilson": wilson(successes, len(values)),
            "input_tokens": sum(items[item][name]["usage"].get("input_tokens", 0) for item in ids),
            "output_tokens": sum(items[item][name]["usage"].get("output_tokens", 0) for item in ids),
        }
    group_stats: dict[str, dict[str, dict]] = defaultdict(dict)
    groups = sorted({items[item]["jev"]["group"] for item in ids})
    for group in groups:
        group_ids = [item for item in ids if items[item]["jev"]["group"] == group]
        for name in ("always_strong", "always_cheap", "jev"):
            group_rows = [items[item][name] for item in group_ids]
            successes = sum(row["quality"] >= 0.999 for row in group_rows)
            group_stats[group][name] = {
                "n": len(group_rows),
                "accuracy": successes / len(group_rows),
                "accuracy_95ci_wilson": wilson(successes, len(group_rows)),
                "cost_usd": sum(row["total_cost_usd"] for row in group_rows),
                "latency_p50_ms": percentile([row["latency_ms"] for row in group_rows], 0.5),
                "latency_p95_ms": percentile([row["latency_ms"] for row in group_rows], 0.95),
            }
    return {
        "run": summary["run"],
        "baselines": baselines,
        "paired": {
            "jev_minus_strong_bootstrap_95ci": bootstrap_delta(strong, jev),
            "jev_minus_random_matched_bootstrap_95ci": bootstrap_delta(random_matched, jev),
            "jev_vs_strong_mcnemar": mcnemar_exact(strong, jev),
            "cheap_vs_strong_mcnemar": mcnemar_exact(strong, cheap),
        },
        "routing_cases": dict(cases),
        "routing_classifier": {
            "strong_needed_count": len(strong_needed),
            "selected_strong_count": len(selected_strong),
            "true_positive": true_positive,
            "precision": true_positive / len(selected_strong) if selected_strong else None,
            "recall": true_positive / len(strong_needed) if strong_needed else None,
        },
        "oracle": {
            "quality": oracle_quality / len(ids),
            "target_cost_usd": oracle_target_cost,
            "cost_with_observed_jev_overhead_usd": oracle_target_cost + router_cost,
        },
        "probability_calibration": probability_diagnostics(items),
        "threshold_diagnostic": {"selected_under_max_loss": chosen, "curve": curve},
        "groups": dict(group_stats),
        "providers": {
            name: dict(Counter(row.get("target_provider") or "unknown" for row in rows if row["baseline"] == name))
            for name in ("always_strong", "always_cheap")
        },
    }


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def report(analysis: dict, directory: Path, dev_only: bool, calibration: dict | None) -> None:
    run = analysis["run"]
    baselines = analysis["baselines"]
    cases = analysis["routing_cases"]
    quality_loss_pp = (baselines["always_strong"]["quality_mean"] - baselines["jev"]["quality_mean"]) * 100
    target_passed = quality_loss_pp <= 2.0
    total_spend = run["ledger_spend_usd"] + (calibration["run"]["ledger_spend_usd"] if calibration else 0)
    lines = [
        "# Ayrıntılı Canlı Benchmark Analizi",
        "",
        f"- Örnek: {run['task_count']}",
        f"- Gerçek benzersiz çağrı: {run['unique_live_target_calls']} hedef + {run['unique_live_jev_calls']} Jev",
        f"- Ledger harcaması: ${run['ledger_spend_usd']:.6f}",
        f"- Kalibrasyon dahil toplam harcama: ${total_spend:.6f}",
        f"- Birincil eşik: {run['threshold']:.2f}",
        f"- Analiz rolü: {'yalnız kalibrasyon; test iddiası değildir' if dev_only else 'kilitli test'}",
        "",
        "## Ana hüküm",
        "",
        f"Jev yolu Sol'a göre **{quality_loss_pp:.2f} yüzde puan** kalite kaybetti ve **%{baselines['jev']['savings_vs_always_strong'] * 100:.1f}** politika maliyeti tasarrufu sağladı. Önceden tanımlı ≤2 yüzde puan kalite kaybı hedefi **{'GEÇTİ' if target_passed else 'GEÇMEDİ'}**.",
        f"Uçtan uca p50 Jev gecikmesi {baselines['jev']['latency_p50_ms']:.0f} ms; Sol {baselines['always_strong']['latency_p50_ms']:.0f} ms ve Luna {baselines['always_cheap']['latency_p50_ms']:.0f} ms. Jev yönlendirme p50 ek yükü {baselines['jev']['router_latency_p50_ms']:.0f} ms.",
        "",
        "## Politika sonuçları",
        "",
        "| Politika | Doğruluk | %95 Wilson GA | Sol'a fark | Güçlü oranı | Politika maliyeti | Tasarruf | p50 / p95 gecikme |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("always_strong", "always_cheap", "rule", "random_matched", "jev"):
        row = baselines[name]
        ci = row["accuracy_95ci_wilson"]
        lines.append(
            f"| {name} | {pct(row['success_rate'])} | [{pct(ci[0])}, {pct(ci[1])}] | "
            f"{row['quality_delta_vs_strong'] * 100:+.2f} yp | {pct(row['strong_selection_rate'])} | "
            f"${row['total_cost_usd']:.6f} | {pct(row['savings_vs_always_strong']) if row['savings_vs_always_strong'] is not None else '—'} | "
            f"{row['latency_p50_ms']:.0f} / {row['latency_p95_ms']:.0f} ms |"
        )
    lines += [
        "",
        "## Yönlendirme hata anatomisi",
        "",
        f"- İki model de doğru: {cases.get('both_correct', 0)}",
        f"- Yalnız Sol doğru: {cases.get('only_strong_correct', 0)}",
        f"- Yalnız Luna doğru: {cases.get('only_cheap_correct', 0)}",
        f"- İkisi de yanlış: {cases.get('neither_correct', 0)}",
        f"- Jev Luna seçti ve yalnız Sol doğruydu: {cases.get('unsafe_cheap', 0)}",
        f"- Jev Sol seçerek Luna hatasını kurtardı: {cases.get('recovered_by_strong', 0)}",
        f"- Jev Sol seçti ama Luna da doğruydu: {cases.get('needless_strong', 0)}",
        f"- Jev servis hatası sonrası güvenli Sol fallback: {cases.get('router_error_fallback', 0)}",
        f"- Güçlü-gereksinim sınıflandırması precision/recall: {pct(analysis['routing_classifier']['precision'])} / {pct(analysis['routing_classifier']['recall'])}.",
        f"- Kusursuz karşı-olgusal seçici üst sınırı: kalite {pct(analysis['oracle']['quality'])}, hedef maliyeti ${analysis['oracle']['target_cost_usd']:.6f}; aynı Jev ek yüküyle ${analysis['oracle']['cost_with_observed_jev_overhead_usd']:.6f}.",
        "",
        "## Görev ailesi kırılımı",
        "",
        "| Grup | n | Sol | Luna | Jev | Jev maliyeti | Jev p50 / p95 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for group, values in sorted(analysis["groups"].items()):
        lines.append(
            f"| {group} | {values['jev']['n']} | {pct(values['always_strong']['accuracy'])} | "
            f"{pct(values['always_cheap']['accuracy'])} | {pct(values['jev']['accuracy'])} | "
            f"${values['jev']['cost_usd']:.6f} | {values['jev']['latency_p50_ms']:.0f} / {values['jev']['latency_p95_ms']:.0f} ms |"
        )
    probability = analysis["probability_calibration"]
    selected = analysis["threshold_diagnostic"]["selected_under_max_loss"]
    paired = analysis["paired"]
    lines += [
        "",
        "## İstatistik ve olasılık kalibrasyonu",
        "",
        f"- Jev−Sol eşleştirilmiş bootstrap %95 GA: [{paired['jev_minus_strong_bootstrap_95ci'][0] * 100:+.2f}, {paired['jev_minus_strong_bootstrap_95ci'][1] * 100:+.2f}] yüzde puanı.",
        f"- Jev/Sol McNemar iki yönlü p: {paired['jev_vs_strong_mcnemar']['p_value_two_sided']:.6g}.",
        f"- Jev−rastgele-eşleşmiş eşleştirilmiş bootstrap %95 GA: [{paired['jev_minus_random_matched_bootstrap_95ci'][0] * 100:+.2f}, {paired['jev_minus_random_matched_bootstrap_95ci'][1] * 100:+.2f}] yüzde puanı.",
        f"- Jev güçlü-gereksinim olasılığı Brier skoru: {probability['brier_score']:.4f}; ECE: {probability['expected_calibration_error']:.4f}.",
        f"- Bu veri üzerinde ≤2 yp kayıp şartıyla tanısal en düşük maliyetli eşik: {selected['threshold']:.2f}; kalite {pct(selected['quality'])}, güçlü oranı {pct(selected['strong_rate'])}, maliyet ${selected['total_cost_usd']:.6f}.",
        "",
        "Eşik eğrisi test koşusunda yalnız tanısaldır; birincil test sonucunu değiştirmek için kullanılmaz.",
    ]
    if calibration:
        dev_selected = calibration["threshold_diagnostic"]["selected_under_max_loss"]
        lines += [
            "",
            "## Ayrı kalibrasyon koşusu",
            "",
            f"200 dev sorusunda seçilen eşik {dev_selected['threshold']:.2f}; dev kalitesi {pct(dev_selected['quality'])}, Sol'a kayıp {dev_selected['quality_loss_pp_vs_strong']:.2f} yp, güçlü kullanım {pct(dev_selected['strong_rate'])}. Bu eşik kilitli test başlamadan önce donduruldu.",
        ]
    (directory / "DETAILED_REPORT_TR.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results")
    parser.add_argument("--max-loss-pp", type=float, default=2.0)
    parser.add_argument("--dev-only", action="store_true")
    parser.add_argument("--calibration-results")
    args = parser.parse_args()
    directory = Path(args.results)
    analysis = analyze(directory, args.max_loss_pp)
    calibration = None
    if args.calibration_results:
        calibration_path = Path(args.calibration_results) / "detailed_analysis.json"
        calibration = json.loads(calibration_path.read_text())
        analysis["external_calibration"] = {
            "directory": args.calibration_results,
            "run": calibration["run"],
            "selected": calibration["threshold_diagnostic"]["selected_under_max_loss"],
        }
    (directory / "detailed_analysis.json").write_text(json.dumps(analysis, indent=2) + "\n")
    report(analysis, directory, args.dev_only, calibration)
    print(json.dumps(analysis["threshold_diagnostic"]["selected_under_max_loss"], indent=2))


if __name__ == "__main__":
    main()
