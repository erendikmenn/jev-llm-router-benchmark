from __future__ import annotations

import hashlib
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

from .evidence import infer_risk_flags, is_sensitive_path


TrajectoryProfile = Literal["quality-first", "balanced"]
GateAction = Literal["review", "escalate", "block"]

CRITICAL_PROGRESS_FLAGS = frozenset(
    {"destructive", "secret_exposure", "sensitive_path_change"}
)
HIGH_STAKES_PROGRESS_FLAGS = frozenset(
    {
        "authentication",
        "authorization",
        "payment",
        "data_isolation",
        "database_migration",
        "security_boundary",
    }
)


@dataclass(frozen=True)
class ProgressSnapshot:
    """Locally observed progress after one worker round."""

    dispatch_returncode: int
    changed_files: tuple[str, ...]
    diff_sha256: str
    diff_bytes: int
    lines_added: int
    lines_deleted: int
    verifier_total: int
    verifier_passed: int
    verifier_failed: int
    verifier_failure_sha256: str | None
    risk_flags: tuple[str, ...]
    sensitive_paths_excluded: int
    repeated_diff: bool
    repeated_failure: bool

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_files) and self.diff_bytes > 0

    def to_dict(self) -> dict:
        return asdict(self) | {"has_changes": self.has_changes}


@dataclass(frozen=True)
class EvidenceGate:
    action: GateAction
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise RuntimeError(message)
    return result.stdout


def _untracked_text(repo: Path, paths: Iterable[str]) -> str:
    sections: list[str] = []
    for path in paths:
        target = (repo / path).resolve()
        try:
            target.relative_to(repo)
        except ValueError:
            continue
        if not target.is_file():
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = f"<binary-or-unreadable:{target.stat().st_size}>"
        sections.append(f"untracked:{path}\n{content}")
    return "\n".join(sections)


def _numstat_totals(raw: str, repo: Path, untracked: tuple[str, ...]) -> tuple[int, int]:
    added = 0
    deleted = 0
    for line in raw.splitlines():
        fields = line.split("\t", 2)
        if len(fields) < 2:
            continue
        if fields[0].isdigit():
            added += int(fields[0])
        if fields[1].isdigit():
            deleted += int(fields[1])
    for path in untracked:
        target = repo / path
        try:
            with target.open(encoding="utf-8") as handle:
                added += sum(1 for _ in handle)
        except (OSError, UnicodeDecodeError):
            continue
    return added, deleted


def collect_progress_snapshot(
    repository: str | Path,
    *,
    dispatch_returncode: int,
    verifiers: Iterable[object],
    previous: ProgressSnapshot | None = None,
) -> ProgressSnapshot:
    """Collect a content-free progress receipt from Git and verifier results."""

    repo = Path(repository).resolve()
    raw_tracked_files = tuple(
        path
        for path in _git(
            repo, "diff", "--name-only", "--diff-filter=ACDMRT", "HEAD", "--"
        ).splitlines()
        if path
    )
    raw_untracked = tuple(
        path
        for path in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if path
    )
    sensitive_paths = tuple(
        path
        for path in (*raw_tracked_files, *raw_untracked)
        if is_sensitive_path(path)
    )
    tracked_files = tuple(
        path for path in raw_tracked_files if not is_sensitive_path(path)
    )
    untracked = tuple(path for path in raw_untracked if not is_sensitive_path(path))
    changed_files = tuple(dict.fromkeys((*tracked_files, *untracked)))
    tracked_diff = (
        _git(repo, "diff", "--no-ext-diff", "--binary", "HEAD", "--", *tracked_files)
        if tracked_files
        else ""
    )
    untracked_state = _untracked_text(repo, untracked)
    fingerprint_state = f"{tracked_diff}\n{untracked_state}"
    diff_bytes = len(tracked_diff.encode("utf-8")) + sum(
        (repo / path).stat().st_size for path in untracked if (repo / path).is_file()
    )
    diff_sha256 = hashlib.sha256(fingerprint_state.encode("utf-8")).hexdigest()
    lines_added, lines_deleted = _numstat_totals(
        (
            _git(repo, "diff", "--numstat", "HEAD", "--", *tracked_files)
            if tracked_files
            else ""
        ),
        repo,
        untracked,
    )

    verifier_items = tuple(verifiers)
    failed = tuple(item for item in verifier_items if not bool(getattr(item, "passed")))
    failure_state = "\n".join(
        "|".join(
            (
                " ".join(getattr(item, "command")),
                str(getattr(item, "returncode")),
                str(getattr(item, "stdout_tail")),
                str(getattr(item, "stderr_tail")),
            )
        )
        for item in failed
    )
    failure_sha256 = (
        hashlib.sha256(failure_state.encode("utf-8")).hexdigest()
        if failure_state
        else None
    )
    untracked_added_lines = "\n".join(
        f"+{line}" for line in untracked_state.splitlines()
    )
    risk_source = f"{tracked_diff}\n{untracked_added_lines}"
    risk_flags = set(infer_risk_flags(changed_files, risk_source))
    if sensitive_paths:
        risk_flags.add("sensitive_path_change")
    return ProgressSnapshot(
        dispatch_returncode=dispatch_returncode,
        changed_files=changed_files,
        diff_sha256=diff_sha256,
        diff_bytes=diff_bytes,
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        verifier_total=len(verifier_items),
        verifier_passed=len(verifier_items) - len(failed),
        verifier_failed=len(failed),
        verifier_failure_sha256=failure_sha256,
        risk_flags=tuple(sorted(risk_flags)),
        sensitive_paths_excluded=len(sensitive_paths),
        repeated_diff=(
            previous is not None
            and bool(changed_files)
            and diff_sha256 == previous.diff_sha256
        ),
        repeated_failure=(
            previous is not None
            and failure_sha256 is not None
            and failure_sha256 == previous.verifier_failure_sha256
        ),
    )


def decide_evidence_gate(
    snapshot: ProgressSnapshot, *, current_role: str = "luna"
) -> EvidenceGate:
    """Apply machine-evidence rules before spending a semantic judge call."""

    flags = set(snapshot.risk_flags)
    if flags & CRITICAL_PROGRESS_FLAGS:
        return EvidenceGate("block", ("critical_progress_risk",))
    if snapshot.dispatch_returncode != 0:
        return EvidenceGate("escalate", ("worker_dispatch_failed",))
    if not snapshot.has_changes:
        return EvidenceGate("escalate", ("no_worktree_change",))
    if snapshot.repeated_failure or (
        snapshot.repeated_diff and snapshot.verifier_failed > 0
    ):
        return EvidenceGate("escalate", ("worker_spinning",))
    if snapshot.verifier_failed > 0:
        return EvidenceGate("escalate", ("verifier_failed",))
    normalized_role = (
        "luna"
        if current_role == "cheap"
        else "sol"
        if current_role == "strong"
        else current_role
    )
    if flags & HIGH_STAKES_PROGRESS_FLAGS and normalized_role in {"luna", "terra"}:
        return EvidenceGate("escalate", ("high_stakes_change",))
    if snapshot.verifier_total == 0:
        return EvidenceGate("review", ("no_external_verifier",))
    return EvidenceGate("review", ("machine_evidence_passed",))
