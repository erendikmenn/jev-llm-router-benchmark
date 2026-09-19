from __future__ import annotations

import html
import json
from pathlib import Path


COLORS = {
    "always_strong": "#3b4cc0",
    "always_cheap": "#89a7d8",
    "rule": "#f49b45",
    "random_matched": "#a6a6a6",
    "jev": "#0b8f6a",
}


def generate_report(result_dir: str | Path) -> Path:
    directory = Path(result_dir)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    measurements = [
        json.loads(line)
        for line in (directory / "measurements.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    calibration_path = directory / "calibration.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf-8")) if calibration_path.exists() else None
    _write_cost_quality_svg(summary, directory / "cost-quality.svg")
    _write_latency_quality_svg(summary, directory / "latency-quality.svg")
    report_path = directory / "REPORT_TR.md"
    run = summary["run"]
    baselines = summary["baselines"]
    jev = baselines["jev"]
    strong = baselines["always_strong"]
    cheap_failures = [
        row for row in measurements
        if row["baseline"] == "jev" and row["selected_role"] == "cheap" and row["quality"] < 0.999
    ]
    needless_strong = [
        row for row in measurements
        if row["baseline"] == "jev" and row["selected_role"] == "strong"
        and _find_quality(measurements, "always_cheap", row["task_id"]) >= row["quality"]
    ]
    jev_rows = [row for row in measurements if row["baseline"] == "jev"]
    strong_rows = [row for row in measurements if row["baseline"] == "always_strong"]
    cheap_rows = [row for row in measurements if row["baseline"] == "always_cheap"]
    avg_router_cost = sum(row["router_cost_usd"] for row in jev_rows) / max(1, len(jev_rows))
    avg_strong_target = sum(row["target_cost_usd"] for row in strong_rows) / max(1, len(strong_rows))
    avg_cheap_target = sum(row["target_cost_usd"] for row in cheap_rows) / max(1, len(cheap_rows))
    saving_per_cheap = avg_strong_target - avg_cheap_target
    min_cheap_rate = avg_router_cost / saving_per_cheap if saving_per_cheap > 0 else None
    evidence_label = (
        "fixture/simülasyon; gerçek sağlayıcı sonucu değildir"
        if run["mode"] == "fixture"
        else "canlı OpenRouter usage/cost verisi; sağlayıcı faturasıyla ayrıca mutabakat gerekir"
    )
    lines = [
        "# Jev LLM Router Benchmark — Türkçe Sonuç Raporu",
        "",
        f"> Kanıt durumu: **{evidence_label}**. Bu rapor tasarrufu kanıtlanmış üretim sonucu olarak sunmaz.",
        "",
        "## Koşu özeti",
        "",
        f"- Koşu: `{run['run_id']}`",
        f"- Mod: `{run['mode']}`",
        f"- Örnek sayısı: {run['task_count']}",
        f"- Jev eşiği: {run['threshold']:.3f}",
        f"- Jev güçlü model seçim oranı: %{run['jev_strong_rate'] * 100:.1f}",
        f"- Maliyet türü: `{run['cost_kind']}`",
        f"- Gerçek benzersiz çağrı harcaması (ledger): `${run['ledger_spend_usd']:.6f}`",
        f"- Benzersiz hedef/Jev çağrısı: {run.get('unique_live_target_calls') or '—'} / {run.get('unique_live_jev_calls') or '—'}",
        "",
        "## Ana karşılaştırma",
        "",
        "| Politika | Kalite | Güçlüye fark | %95 eşleştirilmiş GA | Güçlü kullanım | Toplam USD | Tasarruf | E2E p50 / p95 ms | TTFT p50 / p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ["always_strong", "always_cheap", "rule", "random_matched", "jev"]:
        row = baselines[name]
        ci = row["quality_delta_95ci"]
        savings = row["savings_vs_always_strong"]
        lines.append(
            f"| {name} | {row['quality_mean']:.3f} | {row['quality_delta_vs_strong'] * 100:+.2f} yp | "
            f"[{ci[0] * 100:+.2f}, {ci[1] * 100:+.2f}] | %{row['strong_selection_rate'] * 100:.1f} | "
            f"${row['total_cost_usd']:.6f} | {('—' if savings is None else f'%{savings * 100:.1f}')} | "
            f"{row['latency_p50_ms']:.1f} / {row['latency_p95_ms']:.1f} | "
            f"{row['ttft_p50_ms']:.1f} / {row['ttft_p95_ms']:.1f} |"
        )
    loss_pp = (strong["quality_mean"] - jev["quality_mean"]) * 100
    lines.extend([
        "",
        "## Önceden tanımlı hedef",
        "",
        f"Hedef, güçlü baseline'a göre toplam başarı/kalite kaybını en fazla 2 yüzde puanında tutarken maliyeti azaltmaktı. Bu koşuda ölçülen kayıp **{loss_pp:.2f} yüzde puanı**. Küçük ve sentetik fixture kümesi kalite korumasını kanıtlamak için yeterli değildir; güven aralığı ve alt gruplar kararın parçasıdır.",
        "",
        "## Hata analizi",
        "",
        f"- Jev ucuz modeli seçtiği halde tam başarı sağlanamayan örnek: {len(cheap_failures)}",
        f"- Ucuz model aynı kaliteyi sağlayabilecekken güçlü model seçilen örnek: {len(needless_strong)}",
        f"- Fallback oranı: %{jev['fallback_rate'] * 100:.1f}",
        f"- Hata oranı: %{jev['error_rate'] * 100:.1f}",
        f"- Fixture iş yükünde Jev ek maliyetini karşılamak için gereken asgari ucuz-model oranı: {('hesaplanamadı' if min_cheap_rate is None else f'%{min_cheap_rate * 100:.1f}')}",
        "",
    ])
    if run["mode"] == "live":
        lines.extend([
            "## Görev bazında canlı tam matris ve Jev yolu",
            "",
            "Her Luna/Sol hücresi bir canlı çağrıdır. Jev politikasının seçtiği hedef yanıt tam matristen yeniden kullanılmıştır; böylece yönlendirilmiş yolun kalite ve hedef gecikmesi aynı canlı yanıta dayanırken gereksiz ikinci ücret oluşmamıştır.",
            "",
            "| Görev | Dil / grup | Luna kalite · USD · ms · TTFT | Sol kalite · USD · ms · TTFT | Jev seçim · P(strong) · güven | Jev ms · USD | Yönlendirilmiş E2E ms |",
            "|---|---|---:|---:|---|---:|---:|",
        ])
        task_ids = sorted({row["task_id"] for row in measurements})
        for task_id in task_ids:
            cheap_row = next(row for row in measurements if row["baseline"] == "always_cheap" and row["task_id"] == task_id)
            strong_row = next(row for row in measurements if row["baseline"] == "always_strong" and row["task_id"] == task_id)
            jev_row = next(row for row in measurements if row["baseline"] == "jev" and row["task_id"] == task_id)
            cheap_ttft = "—" if cheap_row["ttft_ms"] is None else f"{cheap_row['ttft_ms']:.0f}"
            strong_ttft = "—" if strong_row["ttft_ms"] is None else f"{strong_row['ttft_ms']:.0f}"
            probability = "—" if jev_row["jev_strong_probability"] is None else f"{jev_row['jev_strong_probability']:.2f}"
            confidence = "—" if jev_row["jev_confidence"] is None else f"{jev_row['jev_confidence']:.2f}"
            lines.append(
                f"| `{task_id}` | {jev_row['language']} / {jev_row['group']} | "
                f"{cheap_row['quality']:.2f} · ${cheap_row['target_cost_usd']:.6f} · {cheap_row['target_latency_ms']:.0f} · {cheap_ttft} | "
                f"{strong_row['quality']:.2f} · ${strong_row['target_cost_usd']:.6f} · {strong_row['target_latency_ms']:.0f} · {strong_ttft} | "
                f"{jev_row['selected_role']} · {probability} · {confidence} | "
                f"{jev_row['router_latency_ms']:.0f} · ${jev_row['router_cost_usd']:.6f} | {jev_row['latency_ms']:.0f} |"
            )
        lines.append("")
    if cheap_failures:
        lines.append("### Ucuz modelde başarısız seçilmiş örnekler")
        lines.append("")
        for row in cheap_failures[:10]:
            lines.append(f"- `{row['task_id']}` — {row['group']} / {row['language']}, kalite {row['quality']:.2f}, kural `{row['route_rule']}`")
        lines.append("")
    if calibration:
        lines.extend([
            "## Eşik duyarlılığı — yalnız dev",
            "",
            "Bu tablo test sonucuna bakmadan üretilen tüm kalibrasyon eğrisidir; yalnız en iyi görünen tek nokta seçilip saklanmamıştır.",
            "",
            "| Eşik | Dev kalite | Güçlüye kayıp | Güçlü kullanım |",
            "|---:|---:|---:|---:|",
        ])
        for point in calibration["curve"]:
            lines.append(
                f"| {point['threshold']:.3f} | {point['quality']:.3f} | {point['quality_loss_pp']:.2f} yp | %{point['strong_rate'] * 100:.1f} |"
            )
        lines.append("")
    lines.extend([
        "## Alt gruplar",
        "",
        "### Dil",
        "",
        _subgroup_table(summary["subgroups"]["language"]),
        "",
        "### Görev grubu",
        "",
        _subgroup_table(summary["subgroups"]["group"]),
        "",
        "## Grafikler",
        "",
        "![Maliyet–kalite](cost-quality.svg)",
        "",
        "![Gecikme–kalite](latency-quality.svg)",
        "",
        "## Yorum sınırları",
        "",
        (
            "Fixture gecikmeleri ölçülmüş canlı routing gecikmesi değildir. USD değerleri fixture usage alanlarından sabitlenmiş fiyat tablosuyla hesaplanır."
            if run["mode"] == "fixture"
            else "Bu 10 görevlik kontrollü smoke istatistiksel güç veya üretim garantisi sağlamaz. OpenRouter tarafından usage.cost döndürülen çağrılarda bu değer, aksi halde doğrulanmış katalog fiyatı ile token hesabı kullanılmıştır. TTFT ilk boş olmayan streaming metin parçasına kadar istemci duvar saatidir."
        ),
    ])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _find_quality(measurements: list[dict], baseline: str, task_id: str) -> float:
    return next(row["quality"] for row in measurements if row["baseline"] == baseline and row["task_id"] == task_id)


def _subgroup_table(groups: dict) -> str:
    baselines = ["always_strong", "always_cheap", "rule", "random_matched", "jev"]
    lines = ["| Grup | " + " | ".join(baselines) + " |", "|---|" + "---:|" * len(baselines)]
    for name, values in sorted(groups.items()):
        lines.append("| " + name + " | " + " | ".join(f"{values.get(base, 0):.3f}" for base in baselines) + " |")
    return "\n".join(lines)


def _write_cost_quality_svg(summary: dict, path: Path) -> None:
    _write_scatter_svg(summary, path, "total_cost_usd", "Toplam hesaplanan maliyet (USD)", "Maliyet–kalite")


def _write_latency_quality_svg(summary: dict, path: Path) -> None:
    _write_scatter_svg(summary, path, "latency_p50_ms", "Uçtan uca p50 (ms)", "Gecikme–kalite")


def _write_scatter_svg(summary: dict, path: Path, x_key: str, x_label: str, title: str) -> None:
    rows = summary["baselines"]
    width, height = 760, 430
    left, right, top, bottom = 80, 30, 52, 66
    xs = [float(row[x_key]) for row in rows.values()]
    ys = [float(row["quality_mean"]) for row in rows.values()]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax == xmin:
        xmax += 1
    if ymax == ymin:
        ymax += 0.01
    ymin = max(0.0, ymin - 0.03)
    ymax = min(1.0, ymax + 0.03)
    plot_w, plot_h = width - left - right, height - top - bottom
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f9fc"/>',
        f'<text x="{left}" y="30" font-family="system-ui" font-size="20" font-weight="700" fill="#172033">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#667085"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#667085"/>',
        f'<text x="{left + plot_w / 2}" y="{height - 18}" text-anchor="middle" font-family="system-ui" font-size="13" fill="#344054">{html.escape(x_label)}</text>',
        f'<text x="18" y="{top + plot_h / 2}" transform="rotate(-90 18 {top + plot_h / 2})" text-anchor="middle" font-family="system-ui" font-size="13" fill="#344054">Ortalama kalite</text>',
    ]
    for name, row in rows.items():
        x = left + (float(row[x_key]) - xmin) / (xmax - xmin) * plot_w
        y = top + (ymax - float(row["quality_mean"])) / (ymax - ymin) * plot_h
        color = COLORS.get(name, "#333333")
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}"/>')
        svg.append(f'<text x="{x + 10:.1f}" y="{y - 9:.1f}" font-family="ui-monospace,monospace" font-size="11" fill="#172033">{html.escape(name)}</text>')
    svg.append("</svg>")
    path.write_text("\n".join(svg), encoding="utf-8")
