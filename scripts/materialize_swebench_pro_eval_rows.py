#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


ENDPOINT = "https://datasets-server.huggingface.co/rows"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Materialize evaluator-only SWE-bench Pro rows for saved predictions"
    )
    root.add_argument("--predictions", required=True)
    root.add_argument("--output", required=True)
    root.add_argument("--dataset", default="ScaleAI/SWE-bench_Pro")
    return root


def wanted_ids(predictions: list[dict]) -> set[str]:
    ids = {str(item["instance_id"]) for item in predictions}
    if len(ids) != len(predictions):
        raise ValueError("prediction instance ids must be unique")
    return ids


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    predictions = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    wanted = wanted_ids(predictions)
    found: dict[str, dict] = {}
    offset = 0
    while wanted - found.keys():
        query = urlencode(
            {
                "dataset": args.dataset,
                "config": "default",
                "split": "test",
                "offset": offset,
                "length": 100,
            }
        )
        with urlopen(f"{ENDPOINT}?{query}", timeout=60) as response:
            payload = json.loads(response.read())
        page = payload.get("rows") or []
        for item in page:
            row = item["row"]
            instance_id = str(row["instance_id"])
            if instance_id in wanted:
                found[instance_id] = row
        offset += len(page)
        if not page or offset >= int(payload.get("num_rows_total", offset)):
            break
    missing = sorted(wanted - found.keys())
    if missing:
        raise ValueError(f"instances not found in official dataset: {missing[:5]}")
    destination = Path(args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for instance_id in sorted(wanted):
            handle.write(json.dumps(found[instance_id], ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(found), "output": str(destination)}, indent=2))


if __name__ == "__main__":
    main()
