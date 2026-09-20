from __future__ import annotations

import json
from pathlib import Path

from .judge_models import JudgeBenchmarkCase, ReviewPacket


def load_judge_cases(path: str | Path) -> list[JudgeBenchmarkCase]:
    cases: list[JudgeBenchmarkCase] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            try:
                packet = ReviewPacket(
                    id=raw["id"],
                    task=raw["task"],
                    acceptance_criteria=tuple(raw["acceptance_criteria"]),
                    diff=raw["diff"],
                    changed_files=tuple(raw.get("changed_files", [])),
                    relevant_code=raw.get("relevant_code", {}),
                    evidence=raw.get("evidence", {}),
                    risk_flags=tuple(raw.get("risk_flags", [])),
                    forbidden_changes=tuple(raw.get("forbidden_changes", [])),
                    metadata=raw.get("metadata", {}),
                )
                cases.append(
                    JudgeBenchmarkCase(
                        packet=packet,
                        split=raw["split"],
                        expected_action=raw["expected_action"],
                        oracle_reasons=tuple(raw.get("oracle_reasons", [])),
                        fixture=raw.get("fixture", {}),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid judge dataset row {line_number}: {exc}") from exc
    ids = [case.packet.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("judge dataset contains duplicate ids")
    return cases
