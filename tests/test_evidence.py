from __future__ import annotations

import subprocess

from jev_router.evidence import (
    collect_git_review_packet,
    collect_git_review_packet_chunks,
    infer_risk_flags,
    redact_secrets,
)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_collects_diff_code_and_infers_risk(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    auth = repo / "auth.py"
    auth.write_text("def allowed(user):\n    return True\n", encoding="utf-8")
    git(repo, "add", "auth.py")
    git(repo, "commit", "-qm", "initial")
    auth.write_text("def allowed(user):\n    return user.is_admin\n", encoding="utf-8")

    packet = collect_git_review_packet(
        repo,
        packet_id="auth-change",
        task="Require admin access.",
        acceptance_criteria=["Non-admin users are rejected."],
    )

    assert packet.changed_files == ("auth.py",)
    assert "+    return user.is_admin" in packet.diff
    assert packet.relevant_code["auth.py"].endswith("return user.is_admin\n")
    assert "authentication" in packet.risk_flags
    assert packet.evidence["agent_authored_tests_are_independent"] is False


def test_sensitive_files_are_excluded_and_values_are_redacted(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "app.py").write_text("TOKEN = 'safe-placeholder'\n", encoding="utf-8")
    (repo / ".env").write_text("API_KEY=initial\n", encoding="utf-8")
    git(repo, "add", "app.py", ".env")
    git(repo, "commit", "-qm", "initial")
    fake_token = "ghp_" + "abcdefghijklmnop"
    (repo / "app.py").write_text(f"API_KEY={fake_token}\n", encoding="utf-8")
    (repo / ".env").write_text("API_KEY=secret-value\n", encoding="utf-8")

    packet = collect_git_review_packet(
        repo,
        packet_id="secret-change",
        task="Update configuration.",
        acceptance_criteria=["Do not expose secrets."],
    )

    assert ".env" not in packet.changed_files
    assert "secret-value" not in packet.diff
    assert fake_token not in packet.diff
    assert "[REDACTED]" in packet.diff
    assert "secret_exposure" in packet.risk_flags


def test_redaction_and_destructive_inference_are_deterministic():
    value = "Authorization: " + "Bearer " + "abc.def"
    assert redact_secrets(value) == "Authorization: Bearer [REDACTED]"
    flags = infer_risk_flags(["migrations/001.sql"], "+DROP TABLE users;")
    assert flags == ("database_migration", "destructive")


def test_total_diff_and_code_context_respects_budget(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    source = repo / "large.py"
    source.write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "large.py")
    git(repo, "commit", "-qm", "initial")
    source.write_text("x = 2\n" + "# context\n" * 1000, encoding="utf-8")

    packet = collect_git_review_packet(
        repo,
        packet_id="bounded",
        task="Change x.",
        acceptance_criteria=["x is two"],
        max_diff_chars=300,
        max_file_chars=1000,
        max_context_chars=500,
    )

    assert len(packet.diff) + sum(map(len, packet.relevant_code.values())) <= 500


def test_large_change_is_split_without_omitting_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    for index in range(5):
        (repo / f"file_{index}.py").write_text("value = 1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "initial")
    for index in range(5):
        (repo / f"file_{index}.py").write_text("value = 2\n", encoding="utf-8")

    packets = collect_git_review_packet_chunks(
        repo,
        packet_id="chunked",
        task="Change values.",
        acceptance_criteria=["Values are two."],
        max_files_per_packet=2,
    )

    assert len(packets) == 3
    assert {path for packet in packets for path in packet.changed_files} == {
        f"file_{index}.py" for index in range(5)
    }
    assert all(len(packet.changed_files) <= 2 for packet in packets)
