from __future__ import annotations

import io
import json

import pytest

from jev_router.benchmark_catalog import fetch_huggingface_rows, plan_official_split


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_fetch_rows_paginates_and_drops_oracle_fields():
    calls = []

    def opener(url, timeout):
        calls.append(url)
        offset = 0 if "offset=0" in url else 1
        row = {
            "instance_id": f"task-{offset}",
            "repo": "owner/repo",
            "problem_statement": "Fix it",
            "patch": "SECRET GOLD PATCH",
            "test_patch": "HIDDEN TEST",
        }
        return Response(
            json.dumps({"rows": [{"row": row}], "num_rows_total": 2}).encode()
        )

    rows = fetch_huggingface_rows("owner/data", opener=opener)

    assert [row["instance_id"] for row in rows] == ["task-0", "task-1"]
    assert "patch" not in rows[0]
    assert "test_patch" not in rows[0]
    assert len(calls) == 2


def test_official_split_is_deterministic_and_disjoint():
    rows = [{"instance_id": f"task-{index}"} for index in range(20)]
    first = plan_official_split(rows, dev_count=4, test_count=10, seed=7)
    second = plan_official_split(rows, dev_count=4, test_count=10, seed=7)

    assert first == second
    assert {row["instance_id"] for row in first["dev"]}.isdisjoint(
        row["instance_id"] for row in first["test"]
    )


def test_split_rejects_more_rows_than_official_source():
    with pytest.raises(ValueError):
        plan_official_split([{"instance_id": "one"}], dev_count=1, test_count=1, seed=1)
