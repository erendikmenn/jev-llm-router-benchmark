from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .judge_models import ReviewPacket


_SENSITIVE_PATH_PARTS = {
    ".env",
    ".npmrc",
    ".pypirc",
    "credentials",
    "id_rsa",
    "id_ed25519",
}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
_BINARY_SUFFIXES = {
    ".7z",
    ".a",
    ".avi",
    ".bin",
    ".class",
    ".dylib",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".so",
    ".tar",
    ".webm",
    ".woff",
    ".woff2",
    ".zip",
}
_SECRET_PATTERNS = (
    (
        re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)((?:api[_-]?key|secret|token|password)\s*[=:]\s*)(['\"])[^'\"]{6,}\2"
        ),
        r"\1\2[REDACTED]\2",
    ),
    (
        re.compile(
            r"(?im)^(\s*(?:api[_-]?key|secret|token|password)\s*=\s*)[^\s#'\"]{6,}\s*$"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"\b(?:sk|ghp|gho|github_pat)_[A-Za-z0-9_\-]{12,}\b"),
        "[REDACTED]",
    ),
)


class EvidenceError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise EvidenceError(message)
    return result.stdout


def _is_sensitive_path(path: str) -> bool:
    candidate = Path(path)
    lowered = {part.casefold() for part in candidate.parts}
    return bool(lowered & _SENSITIVE_PATH_PARTS) or candidate.suffix.casefold() in _SENSITIVE_SUFFIXES


def _is_text_path(path: str) -> bool:
    return Path(path).suffix.casefold() not in _BINARY_SUFFIXES


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def infer_risk_flags(changed_files: Iterable[str], diff: str) -> tuple[str, ...]:
    joined_paths = "\n".join(changed_files).casefold()
    diff_folded = diff.casefold()
    flags: set[str] = set()
    if any(word in joined_paths for word in ("auth", "login", "session", "oauth")):
        flags.add("authentication")
    if any(word in joined_paths for word in ("permission", "authorization", "rbac", "acl")):
        flags.add("authorization")
    if any(word in joined_paths for word in ("billing", "payment", "invoice", "checkout")):
        flags.add("payment")
    if any(word in joined_paths for word in ("migration", "schema", "alembic")):
        flags.add("database_migration")
    if any(word in joined_paths for word in ("tenant", "organization", "workspace")):
        flags.add("data_isolation")
    if any(word in joined_paths for word in ("security", "crypto", "sandbox")):
        flags.add("security_boundary")
    if re.search(r"(?im)^\+.*\b(drop\s+table|rm\s+-rf|truncate\s+table)\b", diff_folded):
        flags.add("destructive")
    if "[redacted]" in diff_folded:
        flags.add("secret_exposure")
    return tuple(sorted(flags))


def _truncate(text: str, limit: int, label: str) -> str:
    if len(text) <= limit:
        return text
    marker = f"\n... [{label} truncated at {limit} characters] ...\n"
    keep = max(0, limit - len(marker))
    return text[:keep] + marker


def _worktree_file(repo: Path, path: str) -> str | None:
    target = (repo / path).resolve()
    try:
        target.relative_to(repo.resolve())
    except ValueError as exc:
        raise EvidenceError(f"changed path escapes repository: {path}") from exc
    if not target.is_file() or _is_sensitive_path(path) or not _is_text_path(path):
        return None
    try:
        return target.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def collect_git_review_packet(
    repo: str | Path,
    *,
    packet_id: str,
    task: str,
    acceptance_criteria: Iterable[str],
    base: str = "HEAD",
    head: str = "WORKTREE",
    evidence: dict[str, Any] | None = None,
    risk_flags: Iterable[str] = (),
    forbidden_changes: Iterable[str] = (),
    max_diff_chars: int = 70_000,
    max_file_chars: int = 20_000,
    max_context_chars: int = 100_000,
    include_paths: Iterable[str] | None = None,
) -> ReviewPacket:
    repository = Path(repo).resolve()
    if not (repository / ".git").exists():
        raise EvidenceError(f"not a Git repository: {repository}")

    if head == "WORKTREE":
        diff_args = ("diff", "--no-ext-diff", "--unified=40", base, "--")
        names_args = ("diff", "--name-only", "--diff-filter=ACMRT", base, "--")
        stats_args = ("diff", "--numstat", base, "--")
    else:
        diff_args = ("diff", "--no-ext-diff", "--unified=40", base, head, "--")
        names_args = ("diff", "--name-only", "--diff-filter=ACMRT", base, head, "--")
        stats_args = ("diff", "--numstat", base, head, "--")

    all_changed_files = tuple(
        path
        for path in _git(repository, *names_args).splitlines()
        if path and not _is_sensitive_path(path)
    )
    requested_paths = set(include_paths) if include_paths is not None else None
    changed_files = tuple(
        path
        for path in all_changed_files
        if requested_paths is None or path in requested_paths
    )
    if changed_files:
        raw_diff = redact_secrets(_git(repository, *diff_args, *changed_files))
    else:
        raw_diff = ""
    diff_budget = min(max_diff_chars, max_context_chars // 2)
    diff = _truncate(raw_diff, diff_budget, "diff")

    relevant_code: dict[str, str] = {}
    remaining = max(0, max_context_chars - len(diff))
    for path in changed_files:
        if remaining <= 0:
            break
        if head == "WORKTREE":
            content = _worktree_file(repository, path)
        else:
            if _is_sensitive_path(path) or not _is_text_path(path):
                content = None
            else:
                try:
                    content = _git(repository, "show", f"{head}:{path}")
                except EvidenceError:
                    content = None
        if content is None:
            continue
        content = redact_secrets(content)
        content = _truncate(content, min(max_file_chars, remaining), path)
        relevant_code[path] = content
        remaining -= len(content)

    inferred = set(infer_risk_flags(changed_files, diff))
    inferred.update(risk_flags)
    collected_evidence = dict(evidence or {})
    collected_evidence["git_numstat"] = (
        _git(repository, *stats_args, *changed_files).strip() if changed_files else ""
    )
    collected_evidence["evidence_source"] = "local_git"
    collected_evidence["agent_authored_tests_are_independent"] = False

    return ReviewPacket(
        id=packet_id,
        task=task,
        acceptance_criteria=tuple(acceptance_criteria),
        diff=diff,
        changed_files=changed_files,
        relevant_code=relevant_code,
        evidence=collected_evidence,
        risk_flags=tuple(sorted(inferred)),
        forbidden_changes=tuple(forbidden_changes),
        metadata={
            "repository": repository.name,
            "base": base,
            "head": head,
            "context_truncated": remaining <= 0 or len(raw_diff) > diff_budget,
            "changed_files_total": len(all_changed_files),
            "changed_files_in_packet": len(changed_files),
            "omitted_changed_files": tuple(
                path for path in all_changed_files if path not in changed_files
            ),
        },
    )


def collect_git_review_packet_chunks(
    repo: str | Path,
    *,
    packet_id: str,
    task: str,
    acceptance_criteria: Iterable[str],
    base: str = "HEAD",
    head: str = "WORKTREE",
    evidence: dict[str, Any] | None = None,
    risk_flags: Iterable[str] = (),
    forbidden_changes: Iterable[str] = (),
    max_diff_chars: int = 40_000,
    max_file_chars: int = 20_000,
    max_context_chars: int = 72_000,
    max_files_per_packet: int = 8,
) -> tuple[ReviewPacket, ...]:
    if max_files_per_packet < 1:
        raise ValueError("max_files_per_packet must be positive")
    initial = collect_git_review_packet(
        repo,
        packet_id=packet_id,
        task=task,
        acceptance_criteria=acceptance_criteria,
        base=base,
        head=head,
        evidence=evidence,
        risk_flags=risk_flags,
        forbidden_changes=forbidden_changes,
        max_diff_chars=max_diff_chars,
        max_file_chars=max_file_chars,
        max_context_chars=max_context_chars,
    )
    files = initial.changed_files
    if len(files) <= max_files_per_packet and not initial.metadata["context_truncated"]:
        return (initial,)
    chunks: list[ReviewPacket] = []
    for index in range(0, len(files), max_files_per_packet):
        selected = files[index : index + max_files_per_packet]
        chunks.append(
            collect_git_review_packet(
                repo,
                packet_id=f"{packet_id}-chunk-{index // max_files_per_packet + 1}",
                task=task,
                acceptance_criteria=acceptance_criteria,
                base=base,
                head=head,
                evidence={
                    **(evidence or {}),
                    "review_chunk": index // max_files_per_packet + 1,
                    "review_chunk_count": (len(files) + max_files_per_packet - 1)
                    // max_files_per_packet,
                },
                risk_flags=risk_flags,
                forbidden_changes=forbidden_changes,
                max_diff_chars=max_diff_chars,
                max_file_chars=max_file_chars,
                max_context_chars=max_context_chars,
                include_paths=selected,
            )
        )
    return tuple(chunks) or (initial,)
