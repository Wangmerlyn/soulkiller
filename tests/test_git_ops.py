import subprocess

from soulkiller.git_ops import (
    branch_exists,
    commit_all_if_changed,
    ensure_branch_worktree,
    ensure_git_repo,
    has_remote,
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
