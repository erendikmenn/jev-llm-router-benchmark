#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DATA_FILES = tuple(f"test{suffix}.jsonl" for suffix in ("", "2", "3", "4", "5", "6"))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Evaluate saved generations with the pinned official LiveCodeBench checker"
    )
    root.add_argument("--harness-root", required=True)
    root.add_argument("--dataset-dir", required=True)
    root.add_argument("--predictions", required=True)
    root.add_argument("--output", required=True)
    root.add_argument("--workers", type=int, default=4)
    root.add_argument("--timeout", type=int, default=6)
    return root


def _load_rows(dataset_dir: Path, wanted: set[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for name in DATA_FILES:
        with (dataset_dir / name).open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                question_id = str(row["question_id"])
                if question_id in wanted:
                    found[question_id] = row
    missing = sorted(wanted - found.keys())
    if missing:
        raise ValueError(f"predictions reference unknown question ids: {missing[:5]}")
    return found


def _candidate_passed(results: dict, index: int) -> bool:
    candidates = results[index]
    return bool(candidates) and bool(candidates[0]) and all(item is True for item in candidates[0])


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    sys.path.insert(0, str(Path(args.harness_root).resolve()))
    from lcb_runner.benchmarks.code_generation import CodeGenerationProblem
    from lcb_runner.evaluation.compute_code_generation_metrics import codegen_metrics

    predictions = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    if not predictions:
        raise SystemExit("no predictions to evaluate")
    ids = [str(item["question_id"]) for item in predictions]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate prediction question ids")
    rows = _load_rows(Path(args.dataset_dir).resolve(), set(ids))
    problems = [CodeGenerationProblem(**rows[question_id]) for question_id in ids]
    samples = [problem.get_evaluation_sample() for problem in problems]
    generations = [item["code_list"] for item in predictions]
    metrics, results, metadata = codegen_metrics(
        samples,
        generations,
        k_list=[1],
        num_process_evaluate=args.workers,
        timeout=args.timeout,
        debug=False,
    )
    per_task = []
    for index, question_id in enumerate(ids):
        per_task.append(
            {
                "question_id": question_id,
                "passed": _candidate_passed(results, index),
                "test_results": results[index][0],
                "metadata": [json.loads(item) for item in metadata[index]],
            }
        )
    output = {
        "suite": "livecodebench",
        "official_checker": True,
        "tasks_evaluated": len(per_task),
        "tasks_passed": sum(item["passed"] for item in per_task),
        "pass_at_1": metrics["pass@1"],
        "per_task": per_task,
    }
    destination = Path(args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in output.items() if key != "per_task"}, indent=2))


if __name__ == "__main__":
    main()
