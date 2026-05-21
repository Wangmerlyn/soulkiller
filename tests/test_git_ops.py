import subprocess

from soulkiller.git_ops import commit_all_if_changed, ensure_git_repo, has_remote, push_if_configured


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


def test_push_if_configured_skips_without_remote(tmp_path):
    ensure_git_repo(tmp_path)

    result = push_if_configured(tmp_path, auto_push=True)

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
