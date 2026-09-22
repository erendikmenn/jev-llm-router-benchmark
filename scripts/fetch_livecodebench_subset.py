#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


FILES = ("test.jsonl", "test2.jsonl", "test3.jsonl", "test4.jsonl", "test5.jsonl", "test6.jsonl")
DEFAULT_REVISION = "0fe84c3912ea0c4d4a78037083943e8f0c4dd505"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Stream only selected pinned LiveCodeBench rows from Hugging Face"
    )
    root.add_argument("--plan", required=True)
    root.add_argument("--output", required=True)
    root.add_argument("--offset", type=int, default=0)
    root.add_argument("--limit", type=int, required=True)
    root.add_argument("--revision", default=DEFAULT_REVISION)
    return root


def main() -> None:
    args = parser().parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    selected = plan["tasks"][args.offset : args.offset + args.limit]
    wanted = {str(row["question_id"]) for row in selected}
    if len(wanted) != len(selected):
        raise ValueError("selected plan contains duplicate question ids")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    found: dict[str, dict] = {}
    scanned: list[str] = []
    for name in FILES:
        if len(found) == len(wanted):
            break
        url = (
            "https://huggingface.co/datasets/livecodebench/code_generation_lite/"
            f"resolve/{args.revision}/{name}"
        )
        request = Request(url, headers={"User-Agent": "jev-router-benchmark/0.1"})
        with urlopen(request, timeout=120) as response:
            for raw_line in response:
                row = json.loads(raw_line)
                question_id = str(row["question_id"])
                if question_id in wanted:
                    found[question_id] = row
                    print(f"[found] {len(found)}/{len(wanted)} {question_id}", flush=True)
                    if len(found) == len(wanted):
                        break
        scanned.append(name)
    missing = sorted(wanted - found.keys())
    if missing:
        raise RuntimeError(f"missing selected rows after scanning {scanned}: {missing[:10]}")
    ordered = [found[str(row["question_id"])] for row in selected]
    for name in FILES:
        destination = output / name
        rows = ordered if name == "test.jsonl" else []
        with destination.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "dataset": "livecodebench/code_generation_lite",
        "revision": args.revision,
        "offset": args.offset,
        "limit": args.limit,
        "question_ids": [str(row["question_id"]) for row in selected],
        "source_files_scanned": scanned,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(ordered), "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
