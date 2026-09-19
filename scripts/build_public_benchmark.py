#!/usr/bin/env python3
"""Build a deterministic English benchmark through the HF Dataset Viewer API.

The generated task file is intentionally a local artifact. The repository keeps
the builder and source manifest, not copies of third-party benchmark questions.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import re
import time
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://datasets-server.huggingface.co"
SEED = 20260919
PAGE_SIZE = 100
SOURCES = {
    "global_mmlu": {
        "dataset": "CohereLabs/Global-MMLU",
        "revision": "0e619dbeb34206cd48705a1a0ea7fb21cae09993",
        "license": "Apache-2.0",
        "config": "en",
        "dev_split": "dev",
        "test_split": "test",
    },
    "belebele": {
        "dataset": "facebook/belebele",
        "revision": "7899cdfa4e1e0d733fd77c848e2c273cb1d32be2",
        "license": "CC-BY-SA-4.0",
        "config": "eng_Latn",
        "dev_split": "test",
        "test_split": "test",
    },
    "gsm8k": {
        "dataset": "openai/gsm8k",
        "revision": "740312add88f781978c0658806c59bc2815b9866",
        "license": "MIT",
        "config": "main",
        "dev_split": "train",
        "test_split": "test",
    },
    "arc_challenge": {
        "dataset": "allenai/ai2_arc",
        "revision": "210d026faf9955653af8916fad021475a3f00453",
        "license": "CC-BY-SA-4.0",
        "config": "ARC-Challenge",
        "dev_split": "validation",
        "test_split": "test",
    },
}


def _get_json(path: str, params: dict[str, object]) -> dict:
    url = f"{API}/{path}?{urlencode(params)}"
    for attempt in range(8):
        request = Request(url, headers={"User-Agent": "jev-llm-router-benchmark/0.1"})
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            if exc.code != 429 and exc.code < 500:
                raise
            retry_after = float(exc.headers.get("Retry-After", 0) or 0)
            time.sleep(max(retry_after, min(20.0, 0.75 * (2**attempt))))
        except (TimeoutError, URLError):
            if attempt == 7:
                raise
            time.sleep(min(20.0, 0.75 * (2**attempt)))
    raise RuntimeError(f"Dataset Viewer retries exhausted: {url}")


@lru_cache(maxsize=None)
def _parquet_files(dataset: str) -> tuple[dict, ...]:
    return tuple(_get_json("parquet", {"dataset": dataset})["parquet_files"])


def _download(url: str) -> bytes:
    for attempt in range(6):
        request = Request(url, headers={"User-Agent": "jev-llm-router-benchmark/0.1"})
        try:
            with urlopen(request, timeout=120) as response:
                return response.read()
        except (HTTPError, TimeoutError, URLError):
            if attempt == 5:
                raise
            time.sleep(min(20.0, 0.75 * (2**attempt)))
    raise RuntimeError(f"download retries exhausted: {url}")


def _fetch_split(dataset: str, config: str, split: str) -> list[dict]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise RuntimeError("Data preparation requires pyarrow: uv pip install pyarrow") from exc
    files = [
        item for item in _parquet_files(dataset)
        if item["config"] == config and item["split"] == split
    ]
    if not files:
        raise ValueError(f"missing split: {dataset}/{config}/{split}")
    rows: list[dict] = []
    for item in files:
        rows.extend(parquet.read_table(io.BytesIO(_download(item["url"]))).to_pylist())
    return rows


def _sample(rows: list[dict], count: int, namespace: str) -> list[dict]:
    shuffled = list(rows)
    random.Random(f"{SEED}:{namespace}").shuffle(shuffled)
    if len(shuffled) < count:
        raise ValueError(f"{namespace} only has {len(shuffled)} rows; need {count}")
    return shuffled[:count]


def _stratified(rows: list[dict], count: int, namespace: str, key: str) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(str(row.get(key) or "unknown"), []).append(row)
    rng = random.Random(f"{SEED}:{namespace}")
    for bucket in buckets.values():
        rng.shuffle(bucket)
    names = sorted(buckets)
    rng.shuffle(names)
    selected: list[dict] = []
    while len(selected) < count:
        progressed = False
        for name in names:
            if buckets[name] and len(selected) < count:
                selected.append(buckets[name].pop())
                progressed = True
        if not progressed:
            break
    if len(selected) != count:
        raise ValueError(f"could not stratify {namespace} to {count} rows")
    return selected


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or "unknown"


def _task(task_id: str, split: str, group: str, prompt: str, metric: str, expected: str, source: dict) -> dict:
    return {
        "id": task_id,
        "split": split,
        "language": "en",
        "group": group,
        "prompt": prompt,
        "metric": metric,
        "expected": expected,
        "constraints": {
            "modality": "text",
            "requires_tools": False,
            "max_output_tokens": 16,
        },
        "fixture": {"source": source},
        "jev_fixture": {},
        "tests": [],
    }


def _choice_prompt(question: str, choices: list[str]) -> str:
    labels = "ABCD"
    rendered = "\n".join(f"{labels[index]}. {text}" for index, text in enumerate(choices))
    return f"Choose the correct answer. Return only one letter: A, B, C, or D.\n\n{question}\n\n{rendered}"


def _mmlu_task(row: dict, split: str, index: int) -> dict:
    category = _slug(row["subject_category"])
    return _task(
        f"global-mmlu-{split}-{index:04d}", split, f"global_mmlu_{category}",
        _choice_prompt(row["question"], [row[f"option_{letter}"] for letter in "abcd"]),
        "choice_exact", row["answer"],
        {"dataset": "CohereLabs/Global-MMLU", "sample_id": row["sample_id"], "subject": row["subject"], "category": row["subject_category"]},
    )


def _belebele_task(row: dict, split: str, index: int) -> dict:
    question = f"Passage:\n{row['flores_passage']}\n\nQuestion: {row['question']}"
    expected = "ABCD"[int(row["correct_answer_num"]) - 1]
    return _task(
        f"belebele-{split}-{index:04d}", split, "belebele_reading",
        _choice_prompt(question, [row[f"mc_answer{number}"] for number in range(1, 5)]),
        "choice_exact", expected,
        {"dataset": "facebook/belebele", "link": row["link"], "question_number": row["question_number"]},
    )


def _gsm8k_task(row: dict, split: str, index: int) -> dict:
    expected = row["answer"].rsplit("####", 1)[-1].strip()
    prompt = f"Solve this problem. Return only the final numeric answer, with no explanation.\n\n{row['question']}"
    return _task(
        f"gsm8k-{split}-{index:04d}", split, "gsm8k_math", prompt,
        "numeric_exact", expected,
        {"dataset": "openai/gsm8k", "source_split": "train" if split == "dev" else "test"},
    )


def _arc_task(row: dict, split: str, index: int) -> dict:
    texts = row["choices"]["text"]
    labels = row["choices"]["label"]
    answer_index = labels.index(row["answerKey"])
    if len(texts) != 4:
        raise ValueError(f"ARC row {row['id']} does not have four choices")
    return _task(
        f"arc-challenge-{split}-{index:04d}", split, "arc_challenge_science",
        _choice_prompt(row["question"], texts), "choice_exact", "ABCD"[answer_index],
        {"dataset": "allenai/ai2_arc", "sample_id": row["id"]},
    )


def build() -> tuple[list[dict], dict]:
    fetched: dict[tuple[str, str], list[dict]] = {}
    for name, source in SOURCES.items():
        for split in {source["dev_split"], source["test_split"]}:
            fetched[(name, split)] = _fetch_split(source["dataset"], source["config"], split)

    tasks: list[dict] = []
    selections: dict[str, dict[str, list[dict]]] = {}
    for name, source in SOURCES.items():
        dev_rows = fetched[(name, source["dev_split"])]
        test_rows = fetched[(name, source["test_split"])]
        if name == "arc_challenge":
            dev_rows = [row for row in dev_rows if len(row["choices"]["text"]) == 4]
            test_rows = [row for row in test_rows if len(row["choices"]["text"]) == 4]
        if name == "global_mmlu":
            dev = _stratified(dev_rows, 50, f"{name}:dev", "subject_category")
            test = _stratified(test_rows, 250, f"{name}:test", "subject_category")
        elif source["dev_split"] == source["test_split"]:
            combined = _sample(test_rows, 300, f"{name}:heldout")
            dev, test = combined[:50], combined[50:]
        else:
            dev = _sample(dev_rows, 50, f"{name}:dev")
            test = _sample(test_rows, 250, f"{name}:test")
        selections[name] = {"dev": dev, "test": test}

    builders = {
        "global_mmlu": _mmlu_task,
        "belebele": _belebele_task,
        "gsm8k": _gsm8k_task,
        "arc_challenge": _arc_task,
    }
    for split in ("dev", "test"):
        for name in SOURCES:
            for index, row in enumerate(selections[name][split], 1):
                tasks.append(builders[name](row, split, index))

    serialized = "".join(json.dumps(task, ensure_ascii=False, sort_keys=True) + "\n" for task in tasks)
    manifest = {
        "name": "public-benchmark-en-v1",
        "seed": SEED,
        "task_count": len(tasks),
        "dev_count": sum(task["split"] == "dev" for task in tasks),
        "test_count": sum(task["split"] == "test" for task in tasks),
        "tasks_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
        "sources": SOURCES,
        "sampling": "50 calibration and 250 locked test rows per source; Global-MMLU stratified by subject_category; all other sampling deterministic without replacement",
    }
    return tasks, manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/public_benchmark_en_v1.jsonl")
    parser.add_argument("--manifest", default="data/public_benchmark_en_v1.manifest.json")
    args = parser.parse_args()
    tasks, manifest = build()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(task, ensure_ascii=False) + "\n" for task in tasks), encoding="utf-8")
    Path(args.manifest).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
