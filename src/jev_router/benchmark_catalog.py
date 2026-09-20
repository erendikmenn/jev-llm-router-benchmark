from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "benchmarks" / "registry.json"
HF_ROWS_ENDPOINT = "https://datasets-server.huggingface.co/rows"
_SAFE_FIELDS = (
    "instance_id",
    "repo",
    "base_commit",
    "problem_statement",
    "difficulty",
    "image",
    "eval_type",
    "created_at",
    "version",
)


def load_benchmark_registry(path: str | Path = DEFAULT_REGISTRY) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("registry_version") != 1 or not isinstance(payload.get("suites"), dict):
        raise ValueError("unsupported benchmark registry")
    return payload


def fetch_huggingface_rows(
    dataset: str,
    *,
    config: str = "default",
    split: str = "test",
    opener: Callable = urlopen,
) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        query = urlencode(
            {
                "dataset": dataset,
                "config": config,
                "split": split,
                "offset": offset,
                "length": 100,
            }
        )
        url = f"{HF_ROWS_ENDPOINT}?{query}"
        payload = None
        for attempt in range(4):
            try:
                with opener(url, timeout=60) as response:
                    payload = json.loads(response.read())
                break
            except (HTTPError, URLError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(0.5 * (2**attempt))
        assert payload is not None
        page = payload.get("rows") or []
        for item in page:
            row = item.get("row") or {}
            rows.append({key: row.get(key) for key in _SAFE_FIELDS if key in row})
        offset += len(page)
        total = int(payload.get("num_rows_total", offset))
        if not page or offset >= total:
            break
    return rows


def plan_official_split(
    rows: list[dict],
    *,
    dev_count: int,
    test_count: int,
    seed: int,
) -> dict:
    if dev_count < 0 or test_count < 1 or dev_count + test_count > len(rows):
        raise ValueError("requested split sizes do not fit the official dataset")
    ranked = sorted(
        rows,
        key=lambda row: hashlib.sha256(
            f"{seed}:{row['instance_id']}".encode("utf-8")
        ).hexdigest(),
    )
    selected = ranked[: dev_count + test_count]
    dev = selected[:dev_count]
    test = selected[dev_count:]
    return {
        "seed": seed,
        "source_rows": len(rows),
        "dev": dev,
        "test": test,
        "selection_sha256": hashlib.sha256(
            "\n".join(row["instance_id"] for row in selected).encode("utf-8")
        ).hexdigest(),
    }


def write_benchmark_plan(
    suite_name: str,
    output: str | Path,
    *,
    dev_count: int,
    test_count: int,
    seed: int,
    registry_path: str | Path = DEFAULT_REGISTRY,
) -> dict:
    registry = load_benchmark_registry(registry_path)
    suite = registry["suites"].get(suite_name)
    if suite is None:
        raise ValueError(f"unknown benchmark suite: {suite_name}")
    if not str(suite.get("dataset", "")).count("/"):
        raise ValueError(f"suite is not available through Hugging Face rows: {suite_name}")
    rows = fetch_huggingface_rows(
        str(suite["dataset"]), split=str(suite.get("split", "test"))
    )
    split_plan = plan_official_split(
        rows, dev_count=dev_count, test_count=test_count, seed=seed
    )
    manifest = {
        "schema_version": 1,
        "suite": suite_name,
        "source": suite,
        **split_plan,
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
