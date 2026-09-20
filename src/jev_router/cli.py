from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .calibrate import calibration_curve, select_threshold
from .benchmark_catalog import load_benchmark_registry, write_benchmark_plan
from .codex_dispatch import build_codex_dispatch_plan, run_codex_dispatch
from .config import AppConfig, load_config
from .control import run_control
from .dataset import find_cross_split_duplicates, load_tasks, split_tasks
from .demo import serve
from .evidence import collect_git_review_packet
from .evaluate import run_benchmark
from .judge_service import estimate_review_cost, run_review
from .judge_benchmark import regenerate_judge_report, run_judge_benchmark
from .judge_dataset import load_judge_cases
from .livecodebench_runner import (
    load_livecodebench_plan,
    load_livecodebench_tasks,
    run_livecodebench,
    write_livecodebench_plan,
)
from .manifest import build_manifest, write_manifest
from .models import GenerationRequest, Task
from .pipeline import run_coding_pipeline
from .pricing import estimate_request_cost
from .providers import (
    FixtureGenerator,
    FixtureJev,
    FixtureReviewJudge,
    OpenRouterChatProvider,
    OpenRouterJevProvider,
    OpenRouterReviewJudgeProvider,
    ProviderError,
    TypeSafeReviewJudgeProvider,
)
from .report import generate_report
from .routing_campaign import route_swebench_tasks
from .routers import jev_router, rule_router
from .swebench_runner import ARMS, generate_swebench_arm, load_swebench_plan
from .swebench_pro_runner import generate_swebench_pro_arm
from .swebench_analysis import (
    merge_evaluation_reports,
    merge_generation_summaries,
    write_swebench_analysis,
)
from .terminalbench_runner import (
    load_terminalbench_plan,
    load_terminalbench_tasks,
    run_terminalbench,
    write_terminalbench_plan,
)
from .tiered_routing import OpenRouterTieredJevProvider, decide_tiered_route


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "default.toml"
DEFAULT_DATA = ROOT / "data" / "demo_pilot.jsonl"
DEFAULT_JUDGE_DATA = ROOT / "data" / "code_judge_synthetic_v1.jsonl"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="jev-router", description="Jev router and honest benchmark CLI")
    root.add_argument("--config", default=str(DEFAULT_CONFIG))
    sub = root.add_subparsers(dest="command", required=True)

    sub.add_parser("environment", help="Show key presence without revealing values")

    sub.add_parser("benchmark-catalog", help="List pinned official coding benchmarks")
    benchmark_plan = sub.add_parser(
        "benchmark-plan", help="Create a deterministic dev/test plan from an official dataset"
    )
    benchmark_plan.add_argument("--suite", default="swebench-verified")
    benchmark_plan.add_argument("--dev", type=int, default=20)
    benchmark_plan.add_argument("--test", type=int, default=100)
    benchmark_plan.add_argument("--seed", type=int, default=20260920)
    benchmark_plan.add_argument(
        "--output",
        default=str(ROOT / "results" / "benchmark-plans" / "swebench-verified.json"),
    )

    swebench = sub.add_parser(
        "swebench-generate",
        help="Generate patches for a pinned official SWE-bench plan",
    )
    swebench.add_argument(
        "--plan",
        default=str(ROOT / "results" / "benchmark-plans" / "swebench-verified.json"),
    )
    swebench.add_argument("--split", choices=["dev", "test"], default="dev")
    swebench.add_argument("--limit", type=int, default=1)
    swebench.add_argument("--offset", type=int, default=0)
    swebench.add_argument("--arm", choices=ARMS, required=True)
    swebench.add_argument(
        "--workspace-root",
        default=str(ROOT / "results" / "tmp" / "swebench-workspaces"),
    )
    swebench.add_argument("--output")
    swebench.add_argument("--max-rounds", type=int, default=3)
    swebench.add_argument("--max-review-usd", type=float, default=0.05)
    swebench.add_argument("--timeout-seconds", type=float, default=900.0)
    swebench.add_argument("--execute", action="store_true")

    swebench_pro = sub.add_parser(
        "swebench-pro-generate",
        help="Generate official-format SWE-bench Pro patches with local Codex auth",
    )
    swebench_pro.add_argument(
        "--plan",
        default=str(ROOT / "results" / "benchmark-plans" / "swebench-pro-public-full.json"),
    )
    swebench_pro.add_argument("--limit", type=int, default=1)
    swebench_pro.add_argument("--offset", type=int, default=0)
    swebench_pro.add_argument("--arm", choices=ARMS, required=True)
    swebench_pro.add_argument(
        "--workspace-root",
        default=str(ROOT / "results" / "tmp" / "swebench-pro-workspaces"),
    )
    swebench_pro.add_argument("--output")
    swebench_pro.add_argument("--max-rounds", type=int, default=3)
    swebench_pro.add_argument("--max-review-usd", type=float, default=0.05)
    swebench_pro.add_argument("--timeout-seconds", type=float, default=900.0)
    swebench_pro.add_argument("--execute", action="store_true")

    swebench_report = sub.add_parser(
        "swebench-report",
        help="Join generation receipts with official SWE-bench evaluator reports",
    )
    swebench_report.add_argument(
        "--generation", action="append", required=True, metavar="ARM=PATH"
    )
    swebench_report.add_argument(
        "--evaluation", action="append", required=True, metavar="ARM=PATH"
    )
    swebench_report.add_argument("--output", required=True)

    swebench_merge = sub.add_parser(
        "swebench-merge", help="Merge resumable SWE-bench run segments"
    )
    swebench_merge.add_argument("--kind", choices=["generation", "evaluation"], required=True)
    swebench_merge.add_argument("--input", action="append", required=True)
    swebench_merge.add_argument("--output", required=True)

    swebench_route = sub.add_parser(
        "swebench-route-plan",
        help="Route every task in a locked SWE-bench or SWE-bench Pro plan",
    )
    swebench_route.add_argument("--plan", required=True)
    swebench_route.add_argument("--suite", required=True)
    swebench_route.add_argument("--split", choices=["dev", "test"], default="test")
    swebench_route.add_argument("--offset", type=int, default=0)
    swebench_route.add_argument("--limit", type=int)
    swebench_route.add_argument("--max-jev-usd", type=float, default=5.0)
    swebench_route.add_argument("--output", required=True)

    lcb_plan = sub.add_parser(
        "livecodebench-plan",
        help="Build an oracle-free plan from pinned LiveCodeBench JSONL files",
    )
    lcb_plan.add_argument("--dataset-dir", required=True)
    lcb_plan.add_argument("--release", default="release_v6")
    lcb_plan.add_argument(
        "--output",
        default=str(ROOT / "results" / "benchmark-plans" / "livecodebench-release-v6.json"),
    )
    lcb_run = sub.add_parser(
        "livecodebench-run",
        help="Route and generate LiveCodeBench pass@1 candidates with local Codex auth",
    )
    lcb_run.add_argument(
        "--plan",
        default=str(ROOT / "results" / "benchmark-plans" / "livecodebench-release-v6.json"),
    )
    lcb_run.add_argument("--repo", default=".")
    lcb_run.add_argument("--offset", type=int, default=0)
    lcb_run.add_argument("--limit", type=int)
    lcb_run.add_argument("--role", choices=["luna", "terra", "sol", "astra"])
    lcb_run.add_argument("--timeout-seconds", type=float, default=900.0)
    lcb_run.add_argument("--max-jev-usd", type=float, default=5.0)
    lcb_run.add_argument("--route-only", action="store_true")
    lcb_run.add_argument(
        "--output", default=str(ROOT / "results" / "livecodebench-generation")
    )

    tb_plan = sub.add_parser(
        "terminalbench-plan",
        help="Build an oracle-free plan from a pinned Terminal-Bench 2 checkout",
    )
    tb_plan.add_argument("--dataset-root", required=True)
    tb_plan.add_argument(
        "--output",
        default=str(ROOT / "results" / "benchmark-plans" / "terminal-bench-2.json"),
    )
    tb_run = sub.add_parser(
        "terminalbench-run",
        help="Route Terminal-Bench 2 tasks and run them with Harbor and local Codex auth",
    )
    tb_run.add_argument(
        "--plan",
        default=str(ROOT / "results" / "benchmark-plans" / "terminal-bench-2.json"),
    )
    tb_run.add_argument("--dataset-root", required=True)
    tb_run.add_argument("--offset", type=int, default=0)
    tb_run.add_argument("--limit", type=int)
    tb_run.add_argument("--role", choices=["luna", "terra", "sol", "astra"])
    tb_run.add_argument("--timeout-seconds", type=float, default=3600.0)
    tb_run.add_argument("--route-only", action="store_true")
    tb_run.add_argument(
        "--output", default=str(ROOT / "results" / "terminalbench-generation")
    )

    route = sub.add_parser("route", help="Route one request without generating an answer")
    route.add_argument("--prompt", required=True)
    route.add_argument("--mode", choices=["rule", "live-jev"], default="rule")
    route.add_argument("--threshold", type=float, default=None)

    codex_route = sub.add_parser(
        "codex-route", help="Route a task and optionally dispatch it through local Codex auth"
    )
    codex_route.add_argument("--task", required=True)
    codex_route.add_argument("--repo", default=".")
    codex_route.add_argument(
        "--mode", choices=["rule", "live-jev", "live-jev-tiered"], default="rule"
    )
    codex_route.add_argument(
        "--role",
        choices=["auto", "cheap", "strong", "luna", "terra", "sol", "astra"],
        default="auto",
        help="Use auto routing or force one Codex role for a baseline",
    )
    codex_route.add_argument("--threshold", type=float, default=None)
    codex_route.add_argument(
        "--sandbox", choices=["read-only", "workspace-write"], default="workspace-write"
    )
    codex_route.add_argument("--execute", action="store_true")
    codex_route.add_argument("--timeout-seconds", type=float, default=900.0)
    codex_route.add_argument("--receipt")

    pipeline = sub.add_parser(
        "pipeline", help="Route, dispatch, verify, judge, and retry or escalate a coding task"
    )
    pipeline.add_argument("--task", required=True)
    pipeline.add_argument("--repo", default=".")
    pipeline.add_argument("--criterion", action="append", default=[])
    pipeline.add_argument(
        "--role",
        choices=["auto", "luna", "terra", "sol", "astra"],
        default="auto",
    )
    pipeline.add_argument("--verify-json", action="append", default=[])
    pipeline.add_argument("--max-rounds", type=int, default=3)
    pipeline.add_argument("--max-review-usd", type=float, default=0.05)
    pipeline.add_argument(
        "--sandbox", choices=["read-only", "workspace-write"], default="workspace-write"
    )
    pipeline.add_argument("--execute", action="store_true")
    pipeline.add_argument("--output")

    review = sub.add_parser("review", help="Judge a local Git change using task, diff, code, and evidence")
    review.add_argument("--repo", default=".")
    review.add_argument("--task", required=True)
    review.add_argument("--criterion", action="append", default=[])
    review.add_argument("--forbid", action="append", default=[])
    review.add_argument("--risk-flag", action="append", default=[])
    review.add_argument("--base", default="HEAD")
    review.add_argument("--head", default="WORKTREE")
    review.add_argument("--evidence-json")
    review.add_argument("--provider", choices=["openrouter", "typesafe"], default="openrouter")
    review.add_argument("--max-usd", type=float, default=0.01)
    review.add_argument("--allow-path", action="append", default=[])
    review.add_argument("--deny-path", action="append", default=[])
    review.add_argument("--dry-run", action="store_true")

    control = sub.add_parser("control", help="Run Jev routing and post-change judging together")
    control.add_argument("--repo", default=".")
    control.add_argument("--task", required=True)
    control.add_argument("--criterion", action="append", default=[])
    control.add_argument("--forbid", action="append", default=[])
    control.add_argument("--risk-flag", action="append", default=[])
    control.add_argument("--base", default="HEAD")
    control.add_argument("--head", default="WORKTREE")
    control.add_argument("--evidence-json")
    control.add_argument("--threshold", type=float, default=None)
    control.add_argument("--max-usd", type=float, default=0.02)

    judge_benchmark = sub.add_parser("judge-benchmark", help="Measure Jev code-judge decisions")
    judge_benchmark.add_argument("--data", default=str(DEFAULT_JUDGE_DATA))
    judge_benchmark.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    judge_benchmark.add_argument("--split", choices=["dev", "test", "all"], default="test")
    judge_benchmark.add_argument("--provider", choices=["openrouter", "typesafe"], default="openrouter")
    judge_benchmark.add_argument("--max-usd", type=float, default=None)
    judge_benchmark.add_argument("--output", default=str(ROOT / "results" / "judge-fixture"))

    judge_report = sub.add_parser(
        "judge-report", help="Recompute judge metrics from saved measurements without API calls"
    )
    judge_report.add_argument("--results", required=True)

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
    benchmark.add_argument("--split", choices=["dev", "test"], default="test")
    benchmark.add_argument("--output", default=str(ROOT / "results" / "fixture-test"))

    report = sub.add_parser("report", help="Regenerate report and SVG charts")
    report.add_argument("--results", default=str(ROOT / "results" / "fixture-test"))

    demo = sub.add_parser("demo", help="Start privacy-conscious local demo")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8765)
    return root


def _anonymous_task(prompt: str) -> Task:
    return Task("adhoc", "adhoc", "unknown", "unknown", prompt, "contains_all", [], {"modality": "text", "requires_tools": False}, {}, {})


def _arm_paths(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        arm, separator, path = value.partition("=")
        if not separator or arm not in ARMS or not path:
            raise SystemExit(f"expected ARM=PATH with an official arm, got: {value}")
        if arm in parsed:
            raise SystemExit(f"duplicate arm: {arm}")
        parsed[arm] = path
    return parsed


def _calibrated_threshold(config: AppConfig, tasks: list[Task]) -> float:
    points = calibration_curve(split_tasks(tasks, "dev"))
    chosen = select_threshold(points, float(config.experiment["quality_loss_limit_pp"]))
    return chosen.threshold


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    config = load_config(args.config)
    if args.command == "environment":
        print(json.dumps({
            "OPENROUTER_API_KEY": bool(os.getenv("OPENROUTER_API_KEY")),
            "TYPESAFE_API_KEY": bool(os.getenv("TYPESAFE_API_KEY")),
        }, indent=2))
        return
    if args.command == "benchmark-catalog":
        print(json.dumps(load_benchmark_registry(), ensure_ascii=False, indent=2))
        return
    if args.command == "benchmark-plan":
        manifest = write_benchmark_plan(
            args.suite,
            args.output,
            dev_count=args.dev,
            test_count=args.test,
            seed=args.seed,
        )
        print(
            json.dumps(
                {
                    "suite": manifest["suite"],
                    "source_rows": manifest["source_rows"],
                    "dev": len(manifest["dev"]),
                    "test": len(manifest["test"]),
                    "selection_sha256": manifest["selection_sha256"],
                    "output": str(Path(args.output).resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.command == "swebench-generate":
        tasks = load_swebench_plan(args.plan, args.split, args.limit, args.offset)
        output = Path(
            args.output or ROOT / "results" / "swebench-generation" / args.arm
        ).resolve()
        preview = {
            "executed": args.execute,
            "arm": args.arm,
            "split": args.split,
            "offset": args.offset,
            "tasks": [task.instance_id for task in tasks],
            "workspace_root": str(Path(args.workspace_root).resolve()),
            "output": str(output),
            "gold_fields_exposed_to_codex": False,
        }
        if not args.execute:
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return
        review_provider = (
            OpenRouterReviewJudgeProvider(config)
            if args.arm == "router-judge"
            else None
        )
        result = generate_swebench_arm(
            tasks,
            arm=args.arm,
            workspace_root=args.workspace_root,
            output_dir=output,
            config=config,
            review_provider=review_provider,
            max_rounds=args.max_rounds,
            max_review_usd=args.max_review_usd,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps({**preview, **result}, ensure_ascii=False, indent=2))
        return
    if args.command == "swebench-pro-generate":
        tasks = load_swebench_plan(args.plan, "test", args.limit, args.offset)
        output = Path(
            args.output or ROOT / "results" / "swebench-pro-generation" / args.arm
        ).resolve()
        preview = {
            "executed": args.execute,
            "suite": "swebench-pro-public",
            "arm": args.arm,
            "offset": args.offset,
            "tasks": [task.instance_id for task in tasks],
            "workspace_root": str(Path(args.workspace_root).resolve()),
            "output": str(output),
            "gold_fields_exposed_to_codex": False,
        }
        if not args.execute:
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return
        review_provider = (
            OpenRouterReviewJudgeProvider(config)
            if args.arm == "router-judge"
            else None
        )
        result = generate_swebench_pro_arm(
            tasks,
            arm=args.arm,
            workspace_root=args.workspace_root,
            output_dir=output,
            config=config,
            review_provider=review_provider,
            max_rounds=args.max_rounds,
            max_review_usd=args.max_review_usd,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps({**preview, **result}, ensure_ascii=False, indent=2))
        return
    if args.command == "swebench-report":
        report = write_swebench_analysis(
            _arm_paths(args.generation),
            _arm_paths(args.evaluation),
            args.output,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if args.command == "swebench-merge":
        merger = (
            merge_generation_summaries
            if args.kind == "generation"
            else merge_evaluation_reports
        )
        print(json.dumps(merger(args.input, args.output), ensure_ascii=False, indent=2))
        return
    if args.command == "swebench-route-plan":
        tasks = load_swebench_plan(args.plan, args.split, args.limit, args.offset)
        summary = route_swebench_tasks(
            tasks,
            suite=args.suite,
            output_dir=args.output,
            config=config,
            max_jev_usd=args.max_jev_usd,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.command == "livecodebench-plan":
        tasks = load_livecodebench_tasks(args.dataset_dir, release=args.release)
        registry = load_benchmark_registry()
        revision = registry["suites"]["livecodebench"]["dataset_revision"]
        manifest = write_livecodebench_plan(tasks, args.output, source_revision=revision)
        print(
            json.dumps(
                {
                    "suite": manifest["suite"],
                    "release": args.release,
                    "task_count": manifest["task_count"],
                    "oracle_fields_excluded": manifest["oracle_fields_excluded"],
                    "selection_sha256": manifest["selection_sha256"],
                    "output": str(Path(args.output).resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.command == "livecodebench-run":
        tasks = load_livecodebench_plan(args.plan, offset=args.offset, limit=args.limit)
        summary = run_livecodebench(
            tasks,
            repository=args.repo,
            output_dir=args.output,
            config=config,
            forced_role=args.role,
            execute=not args.route_only,
            timeout_seconds=args.timeout_seconds,
            max_jev_usd=args.max_jev_usd,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.command == "terminalbench-plan":
        tasks = load_terminalbench_tasks(args.dataset_root)
        registry = load_benchmark_registry()
        revision = registry["suites"]["terminal-bench-2"]["dataset_revision"]
        manifest = write_terminalbench_plan(tasks, args.output, source_revision=revision)
        print(
            json.dumps(
                {
                    "suite": manifest["suite"],
                    "task_count": manifest["task_count"],
                    "oracle_paths_excluded": manifest["oracle_paths_excluded"],
                    "selection_sha256": manifest["selection_sha256"],
                    "output": str(Path(args.output).resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.command == "terminalbench-run":
        tasks = load_terminalbench_plan(args.plan, offset=args.offset, limit=args.limit)
        summary = run_terminalbench(
            tasks,
            dataset_root=args.dataset_root,
            output_dir=args.output,
            config=config,
            forced_role=args.role,
            execute=not args.route_only,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
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
    if args.command == "codex-route":
        task = _anonymous_task(args.task)
        threshold = (
            args.threshold
            if args.threshold is not None
            else float(config.experiment["default_threshold"])
        )
        decision = None
        tiered_decision = None
        if args.role == "auto":
            if args.mode == "live-jev-tiered":
                tiered_provider = OpenRouterTieredJevProvider(config)
                tiered_decision = decide_tiered_route(task, tiered_provider.judge(task))
                selected_role = tiered_decision.selected
            else:
                decision = (
                    rule_router(task, config)
                    if args.mode == "rule"
                    else jev_router(task, config, OpenRouterJevProvider(config), threshold)
                )
                if decision.selected is None:
                    raise SystemExit(f"task rejected before dispatch: {decision.rejected_reason}")
                selected_role = decision.selected
        else:
            selected_role = args.role
        plan = build_codex_dispatch_plan(args.repo, selected_role, sandbox=args.sandbox)
        payload = {
            "route": {
                "selected_role": selected_role,
                "codex_role": plan.role.name,
                "codex_model": plan.role.model,
                "reasoning_effort": plan.role.reasoning_effort,
                "rule": (
                    tiered_decision.rule
                    if tiered_decision is not None
                    else decision.rule if decision is not None else "forced_baseline"
                ),
                "task_type": decision.task_type if decision is not None else None,
                "confidence": (
                    tiered_decision.judgment.confidence
                    if tiered_decision is not None
                    else decision.confidence if decision is not None else None
                ),
                "strong_probability": (
                    decision.strong_probability if decision is not None else None
                ),
                "tier_probabilities": (
                    tiered_decision.judgment.probabilities
                    if tiered_decision is not None
                    else None
                ),
                "hard_guards": (
                    tiered_decision.hard_guards if tiered_decision is not None else ()
                ),
            },
            "executed": args.execute,
            "plan": plan.to_dict(),
        }
        if args.execute:
            receipt = run_codex_dispatch(
                plan,
                args.task,
                timeout_seconds=args.timeout_seconds,
            )
            payload["receipt"] = receipt.to_dict()
            if args.receipt:
                Path(args.receipt).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            if receipt.returncode != 0:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                raise SystemExit(receipt.returncode)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.command == "pipeline":
        task = _anonymous_task(args.task)
        route_metadata: dict = {"source": "forced"}
        if args.role == "auto":
            try:
                tiered_provider = OpenRouterTieredJevProvider(config)
                tiered = decide_tiered_route(task, tiered_provider.judge(task))
                selected_role = tiered.selected
                route_metadata = tiered.to_dict()
            except ProviderError as exc:
                selected_role = "astra"
                route_metadata = {
                    "selected": "astra",
                    "rule": f"jev_error_fallback:{exc.kind}",
                    "source": "fail_safe",
                }
        else:
            selected_role = args.role
        commands: list[tuple[str, ...]] = []
        for raw in args.verify_json:
            parsed = json.loads(raw)
            if not isinstance(parsed, list) or not parsed or not all(
                isinstance(item, str) and item for item in parsed
            ):
                raise SystemExit("--verify-json must be a non-empty JSON string array")
            commands.append(tuple(parsed))
        if not args.execute:
            plan = build_codex_dispatch_plan(args.repo, selected_role, sandbox=args.sandbox)
            print(
                json.dumps(
                    {"executed": False, "route": route_metadata, "plan": plan.to_dict()},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        result = run_coding_pipeline(
            args.repo,
            task=args.task,
            acceptance_criteria=args.criterion,
            initial_role=selected_role,
            review_provider=OpenRouterReviewJudgeProvider(config),
            config=config,
            verifier_commands=commands,
            max_rounds=args.max_rounds,
            max_review_usd=args.max_review_usd,
            sandbox=args.sandbox,
        )
        payload = {"executed": True, "route": route_metadata, "pipeline": result.to_dict()}
        if args.output:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.command == "review":
        evidence = {}
        if args.evidence_json:
            evidence = json.loads(Path(args.evidence_json).read_text(encoding="utf-8"))
            if not isinstance(evidence, dict):
                raise SystemExit("--evidence-json must contain a JSON object")
        packet = collect_git_review_packet(
            args.repo,
            packet_id="local-review",
            task=args.task,
            acceptance_criteria=args.criterion or [args.task],
            base=args.base,
            head=args.head,
            evidence=evidence,
            risk_flags=args.risk_flag,
            forbidden_changes=args.forbid,
            max_diff_chars=int(config.judge["max_diff_chars"]),
            max_file_chars=int(config.judge["max_file_chars"]),
            max_context_chars=int(config.judge["max_context_chars"]),
            allow_paths=args.allow_path,
            deny_paths=args.deny_path,
        )
        estimated_cost = estimate_review_cost(packet, config)
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "provider_called": False,
                        "packet": {
                            "changed_files": packet.changed_files,
                            "privacy_excluded_files": packet.metadata[
                                "privacy_excluded_files"
                            ],
                            "risk_flags": packet.risk_flags,
                            "context_truncated": packet.metadata["context_truncated"],
                            "state_characters": packet.metadata["state_characters"],
                            "redactions_applied": packet.metadata["redactions_applied"],
                        },
                        "estimated_cost_usd": estimated_cost,
                        "within_budget": estimated_cost <= args.max_usd,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        if estimated_cost > args.max_usd:
            raise SystemExit(
                f"estimated Jev review cost ${estimated_cost:.6f} exceeds --max-usd ${args.max_usd:.6f}"
            )
        provider = (
            OpenRouterReviewJudgeProvider(config)
            if args.provider == "openrouter"
            else TypeSafeReviewJudgeProvider(config)
        )
        result = run_review(packet, provider, config)
        print(json.dumps({
            "packet": {
                "id": packet.id,
                "changed_files": packet.changed_files,
                "risk_flags": packet.risk_flags,
                "context_truncated": packet.metadata["context_truncated"],
            },
            "estimated_cost_usd": estimated_cost,
            **result.to_dict(),
        }, ensure_ascii=False, indent=2))
        return
    if args.command == "judge-benchmark":
        all_cases = load_judge_cases(args.data)
        cases = (
            all_cases
            if args.split == "all"
            else [case for case in all_cases if case.split == args.split]
        )
        if not cases:
            raise SystemExit(f"no judge cases for split: {args.split}")
        if args.mode == "fixture":
            provider = FixtureReviewJudge(config, cases)
        elif args.provider == "openrouter":
            provider = OpenRouterReviewJudgeProvider(config)
        else:
            provider = TypeSafeReviewJudgeProvider(config)
        _, summary = run_judge_benchmark(
            cases,
            provider,
            config,
            args.output,
            mode=args.mode,
            max_budget_usd=args.max_usd,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.command == "judge-report":
        summary = regenerate_judge_report(args.results)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.command == "control":
        evidence = {}
        if args.evidence_json:
            evidence = json.loads(Path(args.evidence_json).read_text(encoding="utf-8"))
            if not isinstance(evidence, dict):
                raise SystemExit("--evidence-json must contain a JSON object")
        packet = collect_git_review_packet(
            args.repo,
            packet_id="local-control",
            task=args.task,
            acceptance_criteria=args.criterion or [args.task],
            base=args.base,
            head=args.head,
            evidence=evidence,
            risk_flags=args.risk_flag,
            forbidden_changes=args.forbid,
            max_diff_chars=int(config.judge["max_diff_chars"]),
            max_file_chars=int(config.judge["max_file_chars"]),
            max_context_chars=int(config.judge["max_context_chars"]),
        )
        review_estimate = estimate_review_cost(packet, config)
        if review_estimate > args.max_usd:
            raise SystemExit(
                f"estimated review cost ${review_estimate:.6f} exceeds --max-usd ${args.max_usd:.6f}"
            )
        threshold = (
            args.threshold
            if args.threshold is not None
            else float(config.experiment["default_threshold"])
        )
        result = run_control(
            _anonymous_task(args.task),
            packet,
            OpenRouterJevProvider(config),
            OpenRouterReviewJudgeProvider(config),
            config,
            threshold,
        )
        if result.total_control_cost_usd > args.max_usd:
            raise SystemExit(
                f"control spend ${result.total_control_cost_usd:.6f} exceeded --max-usd ${args.max_usd:.6f}"
            )
        print(json.dumps({
            "packet": {
                "changed_files": packet.changed_files,
                "risk_flags": packet.risk_flags,
                "context_truncated": packet.metadata["context_truncated"],
            },
            **result.to_dict(),
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
        should_fixture_calibrate = (
            getattr(args, "threshold", None) is None
            and dev_tasks
            and all("strong" in task.fixture and "cheap" in task.fixture and task.jev_fixture for task in dev_tasks)
        )
        curve = calibration_curve(dev_tasks) if should_fixture_calibrate else []
        chosen = select_threshold(curve, float(config.experiment["quality_loss_limit_pp"])) if curve else None
        if getattr(args, "threshold", None) is not None:
            threshold = args.threshold
        elif chosen is not None:
            threshold = chosen.threshold
        else:
            threshold = float(config.experiment["default_threshold"])
        selected_split = "test" if args.command == "smoke" else args.split
        tasks = split_tasks(all_tasks, selected_split)
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
