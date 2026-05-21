import json
import subprocess
import fcntl

from soulkiller.config import BackupSourcesConfig, CodexMemoriesConfig, Config, ExtraBackupConfig
from soulkiller.git_ops import commit_all_if_changed, ensure_git_repo, run_git
from soulkiller.sync import sync_all


def configure_identity(path):
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test User"], check=True)


def make_config(tmp_path):
    codex_memories = tmp_path / "codex-memories"
    extra_repo = tmp_path / "extra-repo"
    codex_skills = tmp_path / "codex-skills"
    claude_projects = tmp_path / "claude-projects"
    return Config(
        codex_memories=CodexMemoriesConfig(enabled=True, path=codex_memories, auto_push=False),
        extra_backup=ExtraBackupConfig(enabled=True, repo_path=extra_repo, auto_push=False, init_if_missing=True),
        backup_sources=BackupSourcesConfig(codex_custom_skills=codex_skills, claude_projects=claude_projects),
    )


def test_sync_all_snapshots_codex_memories_and_extra_backup(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    ensure_git_repo(config.extra_backup.repo_path)
    configure_identity(config.extra_backup.repo_path)
    (config.codex_memories.path / "MEMORY.md").write_text("codex memory\n", encoding="utf-8")

    (config.backup_sources.codex_custom_skills / ".system" / "ignored").mkdir(parents=True)
    custom_skill = config.backup_sources.codex_custom_skills / "custom-skill"
    custom_skill.mkdir(parents=True)
    (custom_skill / "SKILL.md").write_text("custom skill\n", encoding="utf-8")

    project_memory = config.backup_sources.claude_projects / "-home-user-project" / "memory"
    project_memory.mkdir(parents=True)
    (project_memory / "notes.md").write_text("claude memory\n", encoding="utf-8")

    result = sync_all(config)

    assert result.codex.committed is True
    assert run_git(config.codex_memories.path, "status", "--porcelain").stdout.strip() == "?? MEMORY.md"
    assert result.extra.committed is True
    assert (config.extra_backup.repo_path / "codex" / "skills" / "custom-skill" / "SKILL.md").exists()
    assert not (config.extra_backup.repo_path / "codex" / "skills" / ".system").exists()
    assert (config.extra_backup.repo_path / "claude" / "project-memories" / "-home-user-project" / "memory" / "notes.md").exists()
    manifest = json.loads((config.extra_backup.repo_path / "manifests" / "snapshot.json").read_text(encoding="utf-8"))
    assert manifest["sources"]["codex_custom_skills"].endswith("codex-skills")
    assert manifest["extra_backup_repo"].endswith("extra-repo")


def test_sync_all_second_run_is_noop_when_sources_unchanged(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    ensure_git_repo(config.extra_backup.repo_path)
    configure_identity(config.extra_backup.repo_path)
    (config.codex_memories.path / "MEMORY.md").write_text("codex memory\n", encoding="utf-8")
    custom_skill = config.backup_sources.codex_custom_skills / "custom-skill"
    custom_skill.mkdir(parents=True)
    (custom_skill / "SKILL.md").write_text("custom skill\n", encoding="utf-8")

    first = sync_all(config)
    second = sync_all(config)

    assert first.extra.committed is True
    assert second.codex.committed is False
    assert second.extra.committed is False


def test_sync_all_does_not_scan_codex_memories_repo(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    ensure_git_repo(config.extra_backup.repo_path)
    configure_identity(config.extra_backup.repo_path)
    (config.codex_memories.path / "auth.json").write_text("{}", encoding="utf-8")
    (config.codex_memories.path / "note.md").write_text("OPENAI_API_KEY=sk-abc123456789\n", encoding="utf-8")

    result = sync_all(config)

    assert result.codex.scan.ok
    assert result.codex.scan_skipped is True
    assert result.codex.committed is True


def test_sync_all_does_not_leave_blocked_extra_source_in_repo(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    ensure_git_repo(config.extra_backup.repo_path)
    configure_identity(config.extra_backup.repo_path)
    unsafe_skill = config.backup_sources.codex_custom_skills / "unsafe"
    unsafe_skill.mkdir(parents=True)
    (unsafe_skill / "auth.json").write_text("{}", encoding="utf-8")

    result = sync_all(config)

    assert not result.extra.scan.ok
    assert result.extra.committed is False
    assert not (config.extra_backup.repo_path / "codex" / "skills" / "unsafe" / "auth.json").exists()


def test_sync_all_rejects_existing_unsafe_extra_repo_file(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    config.extra_backup.repo_path.mkdir()
    ensure_git_repo(config.extra_backup.repo_path)
    configure_identity(config.extra_backup.repo_path)
    (config.extra_backup.repo_path / ".env.local").write_text("OPENAI_API_KEY=sk-abc123456789\n", encoding="utf-8")

    result = sync_all(config)

    assert not result.extra.scan.ok
    assert result.extra.committed is False
    assert any(".env.local" in issue.path for issue in result.extra.scan.issues)


def test_sync_codex_snapshots_do_not_commit_source_repo(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    ensure_git_repo(config.extra_backup.repo_path)
    configure_identity(config.extra_backup.repo_path)
    (config.codex_memories.path / "MEMORY.md").write_text("initial memory\n", encoding="utf-8")
    commit_all_if_changed(config.codex_memories.path, "init: codex memories")
    source_head = run_git(config.codex_memories.path, "rev-parse", "HEAD").stdout.strip()

    (config.codex_memories.path / "MEMORY.md").write_text("dirty memory\n", encoding="utf-8")

    result = sync_all(config)

    assert run_git(config.codex_memories.path, "rev-list", "--count", "HEAD").stdout.strip() == "1"
    assert run_git(config.codex_memories.path, "rev-parse", "HEAD").stdout.strip() == source_head
    assert run_git(config.codex_memories.path, "status", "--porcelain").stdout.rstrip() == " M MEMORY.md"
    assert result.codex.committed is True
    assert result.codex.commit_message.startswith("snapshot:")


def test_sync_codex_writes_source_and_snapshot_branches(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    ensure_git_repo(config.extra_backup.repo_path)
    configure_identity(config.extra_backup.repo_path)
    note = config.codex_memories.path / "nested" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("codex memory\n", encoding="utf-8")
    commit_all_if_changed(config.codex_memories.path, "init: codex memories")

    sync_all(config)

    source_files = run_git(config.extra_backup.repo_path, "ls-tree", "-r", "--name-only", "codex/source").stdout.splitlines()
    snapshot_files = run_git(config.extra_backup.repo_path, "ls-tree", "-r", "--name-only", "codex/snapshots").stdout.splitlines()
    assert source_files == ["nested/note.md"]
    assert snapshot_files == ["nested/note.md"]


def test_sync_codex_second_run_does_not_create_empty_snapshot(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    ensure_git_repo(config.extra_backup.repo_path)
    configure_identity(config.extra_backup.repo_path)
    (config.codex_memories.path / "MEMORY.md").write_text("codex memory\n", encoding="utf-8")
    commit_all_if_changed(config.codex_memories.path, "init: codex memories")

    first = sync_all(config)
    snapshot_rev = run_git(config.extra_backup.repo_path, "rev-parse", "codex/snapshots").stdout.strip()
    second = sync_all(config)

    assert first.codex.committed is True
    assert second.codex.committed is False
    assert run_git(config.extra_backup.repo_path, "rev-parse", "codex/snapshots").stdout.strip() == snapshot_rev


def test_sync_all_reports_busy_when_lock_is_held(tmp_path):
    config = make_config(tmp_path)
    lock_path = tmp_path / "sync.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        result = sync_all(config, lock_path=lock_path)

        assert result.codex.error == "another sync is already running"
        assert result.extra.error == "another sync is already running"
