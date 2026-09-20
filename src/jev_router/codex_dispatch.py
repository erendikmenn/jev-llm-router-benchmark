from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class CodexRole:
    name: str
    model: str
    reasoning_effort: str


@dataclass(frozen=True)
class CodexDispatchPlan:
    role: CodexRole
    repository: str
    sandbox: str
    command: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "role": asdict(self.role),
            "repository": self.repository,
            "sandbox": self.sandbox,
            "command": list(self.command),
            "prompt_transport": "stdin",
        }


@dataclass(frozen=True)
class CodexDispatchReceipt:
    plan: CodexDispatchPlan
    prompt_sha256: str
    returncode: int
    elapsed_ms: float
    usage: dict
    final_message: str | None
    stderr: str
    stderr_line_count: int
    events_seen: int

    def to_dict(self) -> dict:
        return {
            "plan": self.plan.to_dict(),
            "prompt_sha256": self.prompt_sha256,
            "returncode": self.returncode,
            "elapsed_ms": self.elapsed_ms,
            "usage": self.usage,
            "final_message": self.final_message,
            "stderr": self.stderr,
            "stderr_line_count": self.stderr_line_count,
            "events_seen": self.events_seen,
        }


CODEX_ROLES = {
    "cheap": CodexRole("luna", "gpt-5.6-luna", "medium"),
    "luna": CodexRole("luna", "gpt-5.6-luna", "medium"),
    "terra": CodexRole("terra", "gpt-5.6-terra", "high"),
    "strong": CodexRole("sol", "gpt-5.6-sol", "high"),
    "sol": CodexRole("sol", "gpt-5.6-sol", "high"),
    "frontier": CodexRole("astra", "gpt-6-astra", "high"),
    "astra": CodexRole("astra", "gpt-6-astra", "high"),
}


def build_codex_dispatch_plan(
    repository: str | Path,
    role: str,
    *,
    sandbox: str = "workspace-write",
) -> CodexDispatchPlan:
    repo = Path(repository).resolve()
    if not (repo / ".git").exists():
        raise ValueError(f"not a Git repository: {repo}")
    if role not in CODEX_ROLES:
        raise ValueError(f"unknown Codex role: {role}")
    if sandbox not in {"read-only", "workspace-write"}:
        raise ValueError(f"unsupported sandbox: {sandbox}")
    spec = CODEX_ROLES[role]
    command = (
        "codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--ephemeral",
        "--json",
        "--model",
        spec.model,
        "--config",
        f'model_reasoning_effort="{spec.reasoning_effort}"',
        "--sandbox",
        sandbox,
        "--cd",
        str(repo),
        "-",
    )
    return CodexDispatchPlan(spec, str(repo), sandbox, command)


def _parse_events(stdout: str) -> tuple[list[dict], dict, str | None]:
    events: list[dict] = []
    usage: dict = {}
    final_message: str | None = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        events.append(event)
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
        item = event.get("item")
        if (
            event.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "agent_message"
            and isinstance(item.get("text"), str)
        ):
            final_message = item["text"]
    return events, usage, final_message


def run_codex_dispatch(
    plan: CodexDispatchPlan,
    prompt: str,
    *,
    timeout_seconds: float = 900.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> CodexDispatchReceipt:
    started = time.perf_counter()
    try:
        completed = runner(
            list(plan.command),
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        events, usage, final_message = _parse_events(stdout)
        elapsed_ms = (time.perf_counter() - started) * 1000
        message = f"Codex dispatch timed out after {timeout_seconds:.1f} seconds"
        if stderr.strip():
            message = f"{message}\n{stderr.strip()}"
        return CodexDispatchReceipt(
            plan=plan,
            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            returncode=124,
            elapsed_ms=elapsed_ms,
            usage=usage,
            final_message=final_message,
            stderr=message,
            stderr_line_count=len([line for line in message.splitlines() if line.strip()]),
            events_seen=len(events),
        )
    elapsed_ms = (time.perf_counter() - started) * 1000
    events, usage, final_message = _parse_events(completed.stdout)
    stderr_lines = [line for line in completed.stderr.splitlines() if line.strip()]
    return CodexDispatchReceipt(
        plan=plan,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        returncode=completed.returncode,
        elapsed_ms=elapsed_ms,
        usage=usage,
        final_message=final_message,
        stderr=completed.stderr.strip() if completed.returncode != 0 else "",
        stderr_line_count=len(stderr_lines),
        events_seen=len(events),
    )
