import subprocess

import pytest

from soulkiller.config import BackupSourcesConfig, CodexMemoriesConfig, Config, ExtraBackupConfig
from soulkiller.git_ops import commit_all_if_changed, ensure_git_repo, run_git, update_branch_to_ref
from soulkiller.restore import list_codex_snapshots, restore_codex_snapshot_to_staging, restore_to_staging
from soulkiller.timer import build_service_unit, build_timer_unit, install_timer


def make_config(tmp_path):
    return Config(
        codex_memories=CodexMemoriesConfig(enabled=True, path=tmp_path / "codex-memories", auto_push=False),
        extra_backup=ExtraBackupConfig(
            enabled=True,
            repo_path=tmp_path / "extra-repo",
            auto_push=False,
            init_if_missing=True,
        ),
        backup_sources=BackupSourcesConfig(
            codex_custom_skills=tmp_path / "codex-skills",
            claude_projects=tmp_path / "claude-projects",
        ),
    )


def configure_identity(path):
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test User"], check=True)


def test_build_systemd_units_include_sync_command(tmp_path):
    config_path = tmp_path / "config.toml"
    service = build_service_unit(config_path)
    timer = build_timer_unit()

    assert "soulkiller sync" in service
    assert str(config_path) in service
    assert "OnBootSec=5min" in timer
    assert "OnUnitActiveSec=6h" in timer
    assert "Persistent=true" in timer


def test_build_service_unit_quotes_paths_with_spaces(tmp_path, monkeypatch):
    config_path = tmp_path / "config dir" / "config.toml"
    command = tmp_path / "bin dir" / "soulkiller"
    monkeypatch.setenv("SOULKILLER_COMMAND", str(command))

    service = build_service_unit(config_path)

    assert f"ExecStart='{command}' sync --config '{config_path}'" in service


def test_build_service_unit_prefers_running_soulkiller_script(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    fake_script = tmp_path / ".venv" / "bin" / "soulkiller"
    fake_script.parent.mkdir(parents=True)
    fake_script.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", [str(fake_script), "install-timer"])

    service = build_service_unit(config_path)

    assert f"ExecStart={fake_script} sync --config {config_path}" in service


def test_build_service_unit_prefers_soulkiller_command_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    command = tmp_path / "bin" / "soulkiller"
    monkeypatch.setenv("SOULKILLER_COMMAND", str(command))

    service = build_service_unit(config_path)

    assert f"ExecStart={command} sync --config {config_path}" in service


def test_install_timer_writes_units_without_enabling(tmp_path):
    config_path = tmp_path / "config.toml"
    unit_dir = tmp_path / "systemd"

    result = install_timer(config_path=config_path, unit_dir=unit_dir, enable=False)

    assert result.enabled is False
    assert (unit_dir / "soulkiller.service").exists()
    assert (unit_dir / "soulkiller.timer").exists()


def test_restore_to_staging_copies_extra_backup(tmp_path):
    config = make_config(tmp_path)
    source = config.extra_backup.repo_path / "claude" / "project-memories" / "project" / "memory"
    source.mkdir(parents=True)
    (source / "notes.md").write_text("memory\n", encoding="utf-8")
    git_dir = config.extra_backup.repo_path / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text("private git metadata\n", encoding="utf-8")
    staging = tmp_path / "staging"

    result = restore_to_staging(config, staging)

    assert result.copied_files == 1
    assert (staging / "claude" / "project-memories" / "project" / "memory" / "notes.md").exists()
    assert not (staging / ".git" / "config").exists()


def test_list_codex_snapshots_returns_snapshot_commits(tmp_path):
    config = make_config(tmp_path)
    repo = config.extra_backup.repo_path
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("codex memory\n", encoding="utf-8")
    commit = commit_all_if_changed(repo, "snapshot: codex memories")
    assert commit.commit_hash is not None
    update_branch_to_ref(repo, "codex/snapshots", commit.commit_hash)

    snapshots = list_codex_snapshots(config)

    assert snapshots == [commit.commit_hash]


def test_restore_codex_snapshot_to_staging_copies_selected_ref(tmp_path):
    config = make_config(tmp_path)
    repo = config.extra_backup.repo_path
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("codex memory\n", encoding="utf-8")
    commit = commit_all_if_changed(repo, "snapshot: codex memories")
    assert commit.commit_hash is not None
    update_branch_to_ref(repo, "codex/snapshots", commit.commit_hash)
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "stale.txt").write_text("old staging content\n", encoding="utf-8")

    result = restore_codex_snapshot_to_staging(config, "latest", staging)

    assert result.copied_files == 1
    assert (staging / "MEMORY.md").read_text(encoding="utf-8") == "codex memory\n"
    assert not (staging / "stale.txt").exists()


def test_restore_codex_snapshot_to_staging_accepts_specific_commit_ref(tmp_path):
    config = make_config(tmp_path)
    repo = config.extra_backup.repo_path
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("first codex memory\n", encoding="utf-8")
    first = commit_all_if_changed(repo, "snapshot: first codex memories")
    assert first.commit_hash is not None
    first_commit = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    update_branch_to_ref(repo, "codex/snapshots", first_commit)
    (repo / "MEMORY.md").write_text("second codex memory\n", encoding="utf-8")
    second = commit_all_if_changed(repo, "snapshot: second codex memories")
    assert second.commit_hash is not None
    update_branch_to_ref(repo, "codex/snapshots", second.commit_hash)
    staging = tmp_path / "staging"

    result = restore_codex_snapshot_to_staging(config, first_commit, staging)

    assert result.copied_files == 1
    assert (staging / "MEMORY.md").read_text(encoding="utf-8") == "first codex memory\n"


def test_restore_codex_snapshot_to_staging_rejects_dash_prefixed_ref_without_clearing(tmp_path):
    config = make_config(tmp_path)
    repo = config.extra_backup.repo_path
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("codex memory\n", encoding="utf-8")
    commit = commit_all_if_changed(repo, "snapshot: codex memories")
    assert commit.commit_hash is not None
    update_branch_to_ref(repo, "codex/snapshots", commit.commit_hash)
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "existing.txt").write_text("keep me\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        restore_codex_snapshot_to_staging(config, "--list", staging)

    assert (staging / "existing.txt").read_text(encoding="utf-8") == "keep me\n"


def test_restore_codex_snapshot_to_staging_invalid_ref_does_not_clear_staging(tmp_path):
    config = make_config(tmp_path)
    repo = config.extra_backup.repo_path
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("codex memory\n", encoding="utf-8")
    commit = commit_all_if_changed(repo, "snapshot: codex memories")
    assert commit.commit_hash is not None
    update_branch_to_ref(repo, "codex/snapshots", commit.commit_hash)
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "existing.txt").write_text("keep me\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        restore_codex_snapshot_to_staging(config, "missing-ref", staging)

    assert (staging / "existing.txt").read_text(encoding="utf-8") == "keep me\n"
