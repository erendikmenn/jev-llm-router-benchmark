from __future__ import annotations

import subprocess
from types import SimpleNamespace

from jev_router.trajectory import collect_progress_snapshot, decide_evidence_gate


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def repository(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / "value.txt").write_text("before\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


def verifier(returncode=0, stderr=""):
    return SimpleNamespace(
        command=("pytest", "-q"),
        returncode=returncode,
        stdout_tail="",
        stderr_tail=stderr,
        passed=returncode == 0,
    )


def test_snapshot_records_tracked_and_untracked_progress(tmp_path):
    repo = repository(tmp_path)
    (repo / "value.txt").write_text("after\n", encoding="utf-8")
    (repo / "new.py").write_text("answer = 42\n", encoding="utf-8")

    snapshot = collect_progress_snapshot(
        repo,
        dispatch_returncode=0,
        verifiers=(verifier(),),
    )

    assert snapshot.changed_files == ("value.txt", "new.py")
    assert snapshot.has_changes
    assert snapshot.lines_added == 2
    assert snapshot.lines_deleted == 1
    assert snapshot.verifier_passed == 1
    assert decide_evidence_gate(snapshot).action == "review"


def test_failed_verifier_escalates_without_semantic_review(tmp_path):
    repo = repository(tmp_path)
    (repo / "value.txt").write_text("wrong\n", encoding="utf-8")

    snapshot = collect_progress_snapshot(
        repo,
        dispatch_returncode=0,
        verifiers=(verifier(1, "expected after"),),
    )
    gate = decide_evidence_gate(snapshot)

    assert gate.action == "escalate"
    assert gate.reason_codes == ("verifier_failed",)


def test_repeated_failure_is_labeled_as_spinning(tmp_path):
    repo = repository(tmp_path)
    (repo / "value.txt").write_text("wrong\n", encoding="utf-8")
    first = collect_progress_snapshot(
        repo,
        dispatch_returncode=0,
        verifiers=(verifier(1, "same failure"),),
    )
    second = collect_progress_snapshot(
        repo,
        dispatch_returncode=0,
        verifiers=(verifier(1, "same failure"),),
        previous=first,
    )

    assert second.repeated_diff
    assert second.repeated_failure
    assert decide_evidence_gate(second).reason_codes == ("worker_spinning",)


def test_high_stakes_change_promotes_cheap_but_allows_strong_review(tmp_path):
    repo = repository(tmp_path)
    auth = repo / "auth.py"
    auth.write_text("def allowed(user):\n    return user.is_admin\n", encoding="utf-8")
    snapshot = collect_progress_snapshot(
        repo,
        dispatch_returncode=0,
        verifiers=(verifier(),),
    )

    assert "authentication" in snapshot.risk_flags
    assert decide_evidence_gate(snapshot, current_role="luna").action == "escalate"
    assert decide_evidence_gate(snapshot, current_role="sol").action == "review"


def test_destructive_change_blocks_before_judge(tmp_path):
    repo = repository(tmp_path)
    migration = repo / "migrations" / "001.sql"
    migration.parent.mkdir()
    migration.write_text("DROP TABLE users;\n", encoding="utf-8")
    snapshot = collect_progress_snapshot(
        repo,
        dispatch_returncode=0,
        verifiers=(verifier(),),
    )

    gate = decide_evidence_gate(snapshot)
    assert gate.action == "block"
    assert gate.reason_codes == ("critical_progress_risk",)


def test_sensitive_path_is_not_exposed_in_progress_receipt(tmp_path):
    repo = repository(tmp_path)
    (repo / ".env").write_text("API_KEY=do-not-send\n", encoding="utf-8")
    snapshot = collect_progress_snapshot(
        repo,
        dispatch_returncode=0,
        verifiers=(verifier(),),
    )

    assert ".env" not in snapshot.changed_files
    assert snapshot.sensitive_paths_excluded == 1
    assert "sensitive_path_change" in snapshot.risk_flags
    assert decide_evidence_gate(snapshot).action == "block"


def test_deleted_file_counts_as_real_progress(tmp_path):
    repo = repository(tmp_path)
    (repo / "value.txt").unlink()
    snapshot = collect_progress_snapshot(
        repo,
        dispatch_returncode=0,
        verifiers=(verifier(),),
    )

    assert snapshot.changed_files == ("value.txt",)
    assert snapshot.lines_deleted == 1
    assert snapshot.has_changes
    assert decide_evidence_gate(snapshot).action == "review"


def test_generated_test_cache_is_excluded_from_progress(tmp_path):
    repo = repository(tmp_path)
    (repo / "value.txt").write_text("after\n", encoding="utf-8")
    cache = repo / "__pycache__" / "value.cpython-314.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"generated")
    snapshot = collect_progress_snapshot(
        repo,
        dispatch_returncode=0,
        verifiers=(verifier(),),
    )

    assert snapshot.changed_files == ("value.txt",)
    assert snapshot.non_source_paths_excluded == 1
    assert decide_evidence_gate(snapshot).action == "review"
