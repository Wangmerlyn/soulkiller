from pathlib import Path

import pytest

from soulkiller.config import default_config_path, load_config, write_default_config


def test_write_and_load_default_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = default_config_path()

    write_default_config(path)
    config = load_config(path)

    assert config.codex_memories.enabled is True
    assert config.codex_memories.path == tmp_path / ".codex" / "memories"
    assert config.codex_memories.auto_push is True
    assert config.extra_backup.repo_path == tmp_path / ".local" / "share" / "soulkiller" / "extra-memory-backup"
    assert config.extra_backup.init_if_missing is True
    assert config.backup_sources.codex_custom_skills == tmp_path / ".codex" / "skills"
    assert config.backup_sources.claude_projects == tmp_path / ".claude" / "projects"


def test_load_config_rejects_missing_file(tmp_path):
    missing = tmp_path / "missing.toml"

    with pytest.raises(FileNotFoundError, match=str(missing)):
        load_config(missing)


def test_load_config_expands_user_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / "config.toml"
    path.write_text(
        """
[codex_memories]
enabled = false
path = "~/.codex/memories"
auto_push = false

[extra_backup]
enabled = true
repo_path = "~/extra"
auto_push = false
init_if_missing = false

[backup_sources]
codex_custom_skills = "~/.codex/skills"
claude_projects = "~/.claude/projects"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.codex_memories.enabled is False
    assert config.codex_memories.path == tmp_path / ".codex" / "memories"
    assert config.extra_backup.repo_path == tmp_path / "extra"
    assert config.extra_backup.init_if_missing is False


def test_load_config_rejects_string_booleans(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[codex_memories]
enabled = true
path = "~/.codex/memories"
auto_push = "false"

[extra_backup]
enabled = true
repo_path = "~/extra"
auto_push = false
init_if_missing = true

[backup_sources]
codex_custom_skills = "~/.codex/skills"
claude_projects = "~/.claude/projects"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(TypeError, match="codex_memories.auto_push"):
        load_config(path)
