import json
import subprocess
import fcntl

from soulkiller.config import BackupSourcesConfig, CodexMemoriesConfig, Config, ExtraBackupConfig
from soulkiller.git_ops import ensure_git_repo
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


def test_sync_all_commits_codex_memories_and_extra_backup(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
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
    (config.codex_memories.path / "MEMORY.md").write_text("codex memory\n", encoding="utf-8")
    custom_skill = config.backup_sources.codex_custom_skills / "custom-skill"
    custom_skill.mkdir(parents=True)
    (custom_skill / "SKILL.md").write_text("custom skill\n", encoding="utf-8")

    first = sync_all(config)
    second = sync_all(config)

    assert first.extra.committed is True
    assert second.codex.committed is False
    assert second.extra.committed is False


def test_sync_all_fails_before_commit_when_secret_detected(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    (config.codex_memories.path / "auth.json").write_text("{}", encoding="utf-8")

    result = sync_all(config)

    assert not result.codex.scan.ok
    assert result.codex.committed is False


def test_sync_all_does_not_leave_blocked_extra_source_in_repo(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    unsafe_skill = config.backup_sources.codex_custom_skills / "unsafe"
    unsafe_skill.mkdir(parents=True)
    (unsafe_skill / "auth.json").write_text("{}", encoding="utf-8")

    result = sync_all(config)

    assert not result.extra.scan.ok
    assert result.extra.committed is False
    assert not (config.extra_backup.repo_path / "codex" / "skills" / "unsafe" / "auth.json").exists()


def test_sync_all_reports_busy_when_lock_is_held(tmp_path):
    config = make_config(tmp_path)
    lock_path = tmp_path / "sync.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        result = sync_all(config, lock_path=lock_path)

        assert result.codex.error == "another sync is already running"
        assert result.extra.error == "another sync is already running"
