from soulkiller.config import BackupSourcesConfig, CodexMemoriesConfig, Config, ExtraBackupConfig
from soulkiller.restore import restore_to_staging
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


def test_build_systemd_units_include_sync_command(tmp_path):
    config_path = tmp_path / "config.toml"
    service = build_service_unit(config_path)
    timer = build_timer_unit()

    assert "soulkiller sync" in service
    assert str(config_path) in service
    assert "OnBootSec=5min" in timer
    assert "OnUnitActiveSec=6h" in timer
    assert "Persistent=true" in timer


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
    staging = tmp_path / "staging"

    result = restore_to_staging(config, staging)

    assert result.copied_files == 1
    assert (staging / "claude" / "project-memories" / "project" / "memory" / "notes.md").exists()

