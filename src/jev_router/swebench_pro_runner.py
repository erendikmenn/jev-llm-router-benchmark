from __future__ import annotations

import json
from pathlib import Path

from .config import AppConfig
from .providers.base import ReviewJudgeProvider
from .swebench_runner import SWEbenchTask, generate_swebench_arm


def generate_swebench_pro_arm(
    tasks: list[SWEbenchTask],
    *,
    arm: str,
    workspace_root: str | Path,
    output_dir: str | Path,
    config: AppConfig,
    review_provider: ReviewJudgeProvider | None = None,
    max_rounds: int = 3,
    max_review_usd: float = 0.05,
    timeout_seconds: float = 900.0,
) -> dict:
    """Generate patches with the shared Codex runner and emit SWE-bench Pro format."""
    result = generate_swebench_arm(
        tasks,
        arm=arm,
        workspace_root=workspace_root,
        output_dir=output_dir,
        config=config,
        review_provider=review_provider,
        max_rounds=max_rounds,
        max_review_usd=max_review_usd,
        timeout_seconds=timeout_seconds,
    )
    source = Path(result["predictions"])
    pro_predictions = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pro_predictions.append(
            {
                "instance_id": row["instance_id"],
                "patch": row["model_patch"],
                "prefix": f"jev-router-{arm}",
            }
        )
    destination = Path(output_dir).resolve() / "swebench-pro-predictions.json"
    destination.write_text(
        json.dumps(pro_predictions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **result,
        "pro_predictions": str(destination),
        "pro_prediction_count": len(pro_predictions),
        "official_evaluation_required": True,
    }
