from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .models import Task


def load_tasks(path: str | Path) -> list[Task]:
    tasks: list[Task] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                tasks.append(Task(**json.loads(line)))
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset contains duplicate task ids")
    return tasks


def normalized_fingerprint(text: str) -> str:
    normalized = re.sub(r"\W+", " ", text.casefold()).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def find_cross_split_duplicates(tasks: list[Task]) -> list[tuple[str, str]]:
    seen: dict[str, tuple[str, str]] = {}
    collisions: list[tuple[str, str]] = []
    for task in tasks:
        fingerprint = normalized_fingerprint(task.prompt)
        previous = seen.get(fingerprint)
        if previous and previous[0] != task.split:
            collisions.append((previous[1], task.id))
        seen[fingerprint] = (task.split, task.id)
    return collisions


def split_tasks(tasks: list[Task], split: str) -> list[Task]:
    return [task for task in tasks if task.split == split]

