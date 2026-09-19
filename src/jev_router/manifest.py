from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig
from .scoring import sandbox_backend


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def build_manifest(config: AppConfig, dataset_path: str | Path, mode: str, threshold: float) -> dict:
    root = Path(__file__).resolve().parents[2]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_commit": git_commit(root),
        "mode": mode,
        "models": {
            "cheap": config.cheap.model_id,
            "strong": config.strong.model_id,
            "router": config.router["jev_model"],
        },
        "dataset": {"path": str(dataset_path), "sha256": sha256(dataset_path)},
        "prompt_version": "router-questions-v1",
        "generation_prompt_version": "direct-answer-v1",
        "pricing": config.raw["pricing"],
        "seed": config.experiment["seed"],
        "threshold": threshold,
        "retry": {
            "max_retries": config.experiment["max_retries"],
            "timeout_seconds": config.experiment["request_timeout_seconds"],
        },
        "cache": config.experiment["cache"],
        "concurrency": config.experiment["concurrency"],
        "stream": config.experiment["stream"],
        "code_sandbox_backend": sandbox_backend(),
    }


def write_manifest(directory: str | Path, manifest: dict) -> Path:
    path = Path(directory) / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
