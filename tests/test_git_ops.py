import subprocess

import pytest

import soulkiller.git_ops as git_ops
from soulkiller.git_ops import (
    branch_exists,
    commit_all_if_changed,
    ensure_branch_worktree,
    ensure_git_repo,
    has_remote,
    remove_worktree,
    push_branch_if_configured,
    push_if_configured,
    update_branch_to_ref,
)


def run_git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True, text=True, capture_output=True)


def configure_identity(path):
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test User")


def test_commit_all_if_changed_commits_only_when_needed(tmp_path):
    ensure_git_repo(tmp_path)
    configure_identity(tmp_path)
    (tmp_path / "MEMORY.md").write_text("hello\n", encoding="utf-8")

    first = commit_all_if_changed(tmp_path, "backup: test")
    second = commit_all_if_changed(tmp_path, "backup: test")

    assert first.committed is True
    assert first.commit_hash
    assert second.committed is False


def test_has_remote_false_for_new_repo(tmp_path):
    ensure_git_repo(tmp_path)

    assert has_remote(tmp_path) is False


def test_update_branch_to_ref_creates_or_moves_branch(tmp_path):
    ensure_git_repo(tmp_path)
    configure_identity(tmp_path)
    (tmp_path / "MEMORY.md").write_text("first\n", encoding="utf-8")
    commit_all_if_changed(tmp_path, "backup: first")
    first_commit = run_git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    (tmp_path / "MEMORY.md").write_text("second\n", encoding="utf-8")
    commit_all_if_changed(tmp_path, "backup: second")
    second_commit = run_git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    update_branch_to_ref(tmp_path, "codex/source", first_commit)

    assert branch_exists(tmp_path, "codex/source") is True
    assert run_git(tmp_path, "rev-parse", "codex/source").stdout.strip() == first_commit

    update_branch_to_ref(tmp_path, "codex/source", second_commit)

    assert run_git(tmp_path, "rev-parse", "codex/source").stdout.strip() == second_commit


def test_ensure_branch_worktree_creates_or_reuses_branch(tmp_path):
    repo = tmp_path / "repo"
    worktree_path = tmp_path / "snapshots"
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("source\n", encoding="utf-8")
    commit_all_if_changed(repo, "backup: source")

    ensure_branch_worktree(repo, "codex/snapshots", worktree_path)
    (worktree_path / "snapshot.txt").write_text("snapshot\n", encoding="utf-8")
    commit_all_if_changed(worktree_path, "backup: snapshot")

    ensure_branch_worktree(repo, "codex/snapshots", worktree_path)

    assert run_git(worktree_path, "branch", "--show-current").stdout.strip() == "codex/snapshots"
    assert (worktree_path / "snapshot.txt").read_text(encoding="utf-8") == "snapshot\n"


def test_ensure_branch_worktree_creates_missing_branch_from_origin_branch(tmp_path):
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    fresh = tmp_path / "fresh"
    worktree_path = tmp_path / "fresh-snapshots"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)],
        check=True,
        text=True,
        capture_output=True,
    )
    ensure_git_repo(seed)
    configure_identity(seed)
    (seed / "README.md").write_text("main\n", encoding="utf-8")
    commit_all_if_changed(seed, "init: main")
    run_git(seed, "remote", "add", "origin", str(remote))
    run_git(seed, "push", "-u", "origin", "main")
    run_git(seed, "checkout", "-b", "codex/snapshots")
    (seed / "snapshot.txt").write_text("remote snapshot\n", encoding="utf-8")
    commit_all_if_changed(seed, "snapshot: remote")
    run_git(seed, "push", "-u", "origin", "codex/snapshots")
    subprocess.run(
        ["git", "clone", str(remote), str(fresh)],
        check=True,
        text=True,
        capture_output=True,
    )
    configure_identity(fresh)

    assert branch_exists(fresh, "codex/snapshots") is False

    ensure_branch_worktree(fresh, "codex/snapshots", worktree_path)
    (worktree_path / "next.txt").write_text("next snapshot\n", encoding="utf-8")
    commit_all_if_changed(worktree_path, "snapshot: next")

    run_git(fresh, "merge-base", "--is-ancestor", "origin/codex/snapshots", "codex/snapshots")


def test_ensure_branch_worktree_replaces_plain_directory(tmp_path):
    repo = tmp_path / "repo"
    worktree_path = tmp_path / "snapshots"
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("source\n", encoding="utf-8")
    commit_all_if_changed(repo, "backup: source")
    worktree_path.mkdir()
    stale_file = worktree_path / "stale.txt"
    stale_file.write_text("old plain directory\n", encoding="utf-8")

    ensure_branch_worktree(repo, "codex/snapshots", worktree_path)

    assert run_git(worktree_path, "branch", "--show-current").stdout.strip() == "codex/snapshots"
    assert stale_file.exists() is False


def test_ensure_branch_worktree_rejects_unregistered_git_repo_on_branch(tmp_path):
    repo = tmp_path / "repo"
    worktree_path = tmp_path / "snapshots"
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("source\n", encoding="utf-8")
    commit_all_if_changed(repo, "backup: source")
    ensure_git_repo(worktree_path)
    configure_identity(worktree_path)
    (worktree_path / "README.md").write_text("unrelated repo\n", encoding="utf-8")
    commit_all_if_changed(worktree_path, "initial unrelated")
    run_git(worktree_path, "checkout", "-b", "codex/snapshots")
    marker = worktree_path / "do-not-delete.txt"
    marker.write_text("keep this\n", encoding="utf-8")

    with pytest.raises(ValueError):
        ensure_branch_worktree(repo, "codex/snapshots", worktree_path)

    assert marker.read_text(encoding="utf-8") == "keep this\n"


def test_ensure_branch_worktree_rejects_unregistered_bare_git_repo(tmp_path):
    repo = tmp_path / "repo"
    worktree_path = tmp_path / "snapshots.git"
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("source\n", encoding="utf-8")
    commit_all_if_changed(repo, "backup: source")
    subprocess.run(
        ["git", "init", "--bare", str(worktree_path)],
        check=True,
        text=True,
        capture_output=True,
    )

    with pytest.raises(ValueError):
        ensure_branch_worktree(repo, "codex/snapshots", worktree_path)

    assert (worktree_path / "config").exists()


def test_remove_worktree_raises_on_git_failure_even_when_path_missing(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    worktree_path = tmp_path / "missing"

    def fake_run_git(actual_repo, *args, check=True):
        assert actual_repo == repo
        assert args == ("worktree", "remove", "--force", str(worktree_path))
        assert check is False
        return subprocess.CompletedProcess(
            args=["git"],
            returncode=128,
            stdout="stdout detail",
            stderr="stderr detail",
        )

    monkeypatch.setattr(git_ops, "run_git", fake_run_git)

    with pytest.raises(RuntimeError, match="stderr detail"):
        remove_worktree(repo, worktree_path)


def test_push_if_configured_skips_without_remote(tmp_path):
    ensure_git_repo(tmp_path)

    result = push_if_configured(tmp_path, auto_push=True)

    assert result.pushed is False
    assert "no git remote" in result.message


def test_push_branch_if_configured_skips_without_remote(tmp_path):
    ensure_git_repo(tmp_path)
    configure_identity(tmp_path)
    (tmp_path / "MEMORY.md").write_text("hello\n", encoding="utf-8")
    commit_all_if_changed(tmp_path, "backup: test")

    result = push_branch_if_configured(
        tmp_path,
        "codex/snapshots",
        auto_push=True,
        force_with_lease=False,
    )

    assert result.pushed is False
    assert "no git remote" in result.message


def test_push_if_configured_rejects_detached_head(tmp_path):
    ensure_git_repo(tmp_path)
    configure_identity(tmp_path)
    (tmp_path / "MEMORY.md").write_text("hello\n", encoding="utf-8")
    commit_all_if_changed(tmp_path, "backup: test")
    run_git(tmp_path, "checkout", "--detach", "HEAD")

    result = push_if_configured(tmp_path, auto_push=True)

    assert result.pushed is False
    assert "detached HEAD" in result.message
