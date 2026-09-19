from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .calibrate import calibration_curve, select_threshold
from .config import AppConfig, load_config
from .dataset import find_cross_split_duplicates, load_tasks, split_tasks
from .demo import serve
from .evaluate import run_benchmark
from .manifest import build_manifest, write_manifest
from .models import GenerationRequest, Task
from .pricing import estimate_request_cost
from .providers import FixtureGenerator, FixtureJev, OpenRouterChatProvider, OpenRouterJevProvider
from .report import generate_report
from .routers import jev_router, rule_router


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "default.toml"
DEFAULT_DATA = ROOT / "data" / "demo_pilot.jsonl"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="jev-router", description="Jev router and honest benchmark CLI")
    root.add_argument("--config", default=str(DEFAULT_CONFIG))
    sub = root.add_subparsers(dest="command", required=True)

    sub.add_parser("environment", help="Show key presence without revealing values")

    route = sub.add_parser("route", help="Route one request without generating an answer")
    route.add_argument("--prompt", required=True)
    route.add_argument("--mode", choices=["rule", "live-jev"], default="rule")
    route.add_argument("--threshold", type=float, default=None)

    run_model = sub.add_parser("run-model", help="Run one candidate directly")
    run_model.add_argument("--task-id", required=True)
    run_model.add_argument("--role", choices=["cheap", "strong"], required=True)
    run_model.add_argument("--mode", choices=["fixture", "live"], default="fixture")

    calibrate = sub.add_parser("calibrate", help="Choose Jev threshold on dev only")
    calibrate.add_argument("--data", default=str(DEFAULT_DATA))

    estimate = sub.add_parser("estimate", help="Preflight worst-case live cost estimate")
    estimate.add_argument("--data", default=str(DEFAULT_DATA))
    estimate.add_argument("--split", choices=["dev", "test", "all"], default="test")

    smoke = sub.add_parser("smoke", help="Run five fixture test tasks")
    smoke.add_argument("--output", default=str(ROOT / "results" / "smoke"))

    benchmark = sub.add_parser("benchmark", help="Run A-E baselines on the locked test split")
    benchmark.add_argument("--data", default=str(DEFAULT_DATA))
    benchmark.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    benchmark.add_argument("--threshold", type=float, default=None)
    benchmark.add_argument("--max-usd", type=float, default=None)
    benchmark.add_argument("--output", default=str(ROOT / "results" / "fixture-test"))

    report = sub.add_parser("report", help="Regenerate report and SVG charts")
    report.add_argument("--results", default=str(ROOT / "results" / "fixture-test"))

    demo = sub.add_parser("demo", help="Start privacy-conscious local demo")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8765)
    return root


def _anonymous_task(prompt: str) -> Task:
    return Task("adhoc", "adhoc", "unknown", "unknown", prompt, "contains_all", [], {"modality": "text", "requires_tools": False}, {}, {})


def _calibrated_threshold(config: AppConfig, tasks: list[Task]) -> float:
    points = calibration_curve(split_tasks(tasks, "dev"))
    chosen = select_threshold(points, float(config.experiment["quality_loss_limit_pp"]))
    return chosen.threshold


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    config = load_config(args.config)
    if args.command == "environment":
        print(json.dumps({"OPENROUTER_API_KEY": bool(os.getenv("OPENROUTER_API_KEY"))}, indent=2))
        return
    if args.command == "route":
        task = _anonymous_task(args.prompt)
        threshold = args.threshold if args.threshold is not None else float(config.experiment["default_threshold"])
        decision = rule_router(task, config) if args.mode == "rule" else jev_router(task, config, OpenRouterJevProvider(config), threshold)
        print(json.dumps({
            "selected_role": decision.selected,
            "selected_model": getattr(config, decision.selected).model_id if decision.selected else None,
            "task_type": decision.task_type,
            "confidence": decision.confidence,
            "strong_probability": decision.strong_probability,
            "applied_rule": decision.rule,
            "rejected_reason": decision.rejected_reason,
        }, ensure_ascii=False, indent=2))
        return
    if args.command == "run-model":
        tasks = load_tasks(DEFAULT_DATA)
        task = next(item for item in tasks if item.id == args.task_id)
        provider = FixtureGenerator(config) if args.mode == "fixture" else OpenRouterChatProvider(config)
        result = provider.generate(GenerationRequest(task.id, task.prompt, "Answer directly.", 256, {"fixture": task.fixture}), args.role)
        print(json.dumps({"model": result.model_id, "text": result.text, "usage": result.usage.__dict__, "latency_ms": result.latency_ms}, ensure_ascii=False, indent=2))
        return
    if args.command in {"calibrate", "estimate"}:
        tasks = load_tasks(args.data)
        duplicates = find_cross_split_duplicates(tasks)
        if duplicates:
            raise SystemExit(f"cross-split exact duplicates: {duplicates}")
        if args.command == "calibrate":
            points = calibration_curve(split_tasks(tasks, "dev"))
            chosen = select_threshold(points, float(config.experiment["quality_loss_limit_pp"]))
            print(json.dumps({"selected": chosen.__dict__, "curve": [point.__dict__ for point in points]}, indent=2))
        else:
            selected = tasks if args.split == "all" else split_tasks(tasks, args.split)
            # Full matrix plus Jev, retries at their configured maximum: conservative preflight.
            per_task = sum(
                estimate_request_cost(task.prompt, int(config.experiment["max_output_tokens"]), config.cheap)
                + estimate_request_cost(task.prompt, int(config.experiment["max_output_tokens"]), config.strong)
                for task in selected
            )
            multiplier = int(config.experiment["max_retries"]) + 1
            print(json.dumps({"tasks": len(selected), "full_matrix_max_retry_estimate_usd": per_task * multiplier, "required_live_limit_recommendation_usd": per_task * multiplier * 1.10, "note": "Estimate excludes Jev because exact TypeSafe tokenization is unknown; add headroom."}, indent=2))
        return
    if args.command in {"smoke", "benchmark"}:
        data = DEFAULT_DATA if args.command == "smoke" else Path(args.data)
        all_tasks = load_tasks(data)
        dev_tasks = split_tasks(all_tasks, "dev")
        curve = calibration_curve(dev_tasks) if dev_tasks else []
        chosen = select_threshold(curve, float(config.experiment["quality_loss_limit_pp"])) if curve else None
        if getattr(args, "threshold", None) is not None:
            threshold = args.threshold
        elif chosen is not None:
            threshold = chosen.threshold
        else:
            threshold = float(config.experiment["default_threshold"])
        tasks = split_tasks(all_tasks, "test")
        if args.command == "smoke":
            tasks = tasks[:5]
            mode = "fixture"
            max_usd = None
        else:
            mode = args.mode
            max_usd = args.max_usd
        generator = FixtureGenerator(config) if mode == "fixture" else OpenRouterChatProvider(config)
        jev = FixtureJev(config) if mode == "fixture" else OpenRouterJevProvider(config)
        output = Path(args.output)
        _, summary = run_benchmark(tasks, generator, jev, config, threshold, output, mode, max_usd)
        if chosen is not None:
            (output / "calibration.json").write_text(
                json.dumps(
                    {"selected": chosen.__dict__, "curve": [point.__dict__ for point in curve]},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        write_manifest(output, build_manifest(config, data, mode, threshold))
        report_path = generate_report(output)
        print(json.dumps({"summary": summary["run"], "report": str(report_path)}, ensure_ascii=False, indent=2))
        return
    if args.command == "report":
        print(generate_report(args.results))
        return
    if args.command == "demo":
        serve(config, args.host, args.port)


if __name__ == "__main__":
    main()
