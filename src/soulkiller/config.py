from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class CodexMemoriesConfig:
    enabled: bool
    path: Path
    auto_push: bool


@dataclass(frozen=True)
class ExtraBackupConfig:
    enabled: bool
    repo_path: Path
    auto_push: bool
    init_if_missing: bool


@dataclass(frozen=True)
class BackupSourcesConfig:
    codex_custom_skills: Path
    claude_projects: Path


@dataclass(frozen=True)
class Config:
    codex_memories: CodexMemoriesConfig
    extra_backup: ExtraBackupConfig
    backup_sources: BackupSourcesConfig


def expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def default_config_path() -> Path:
    return Path("~/.config/soulkiller/config.toml").expanduser()


def _get_bool(section: dict[str, object], key: str, default: bool, section_name: str) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"{section_name}.{key} must be a boolean")
    return value


def load_config(path: Path | None = None) -> Config:
    config_path = path or default_config_path()
    if not config_path.exists():
        raise FileNotFoundError(f"config file does not exist: {config_path}")

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    codex = data.get("codex_memories", {})
    extra = data.get("extra_backup", {})
    sources = data.get("backup_sources", {})

    return Config(
        codex_memories=CodexMemoriesConfig(
            enabled=_get_bool(codex, "enabled", True, "codex_memories"),
            path=expand_path(str(codex.get("path", "~/.codex/memories"))),
            auto_push=_get_bool(codex, "auto_push", True, "codex_memories"),
        ),
        extra_backup=ExtraBackupConfig(
            enabled=_get_bool(extra, "enabled", True, "extra_backup"),
            repo_path=expand_path(str(extra.get("repo_path", "~/.local/share/soulkiller/extra-memory-backup"))),
            auto_push=_get_bool(extra, "auto_push", True, "extra_backup"),
            init_if_missing=_get_bool(extra, "init_if_missing", True, "extra_backup"),
        ),
        backup_sources=BackupSourcesConfig(
            codex_custom_skills=expand_path(str(sources.get("codex_custom_skills", "~/.codex/skills"))),
            claude_projects=expand_path(str(sources.get("claude_projects", "~/.claude/projects"))),
        ),
    )


def default_config_text() -> str:
    return """[codex_memories]
enabled = true
path = "~/.codex/memories"
auto_push = true

[extra_backup]
enabled = true
repo_path = "~/.local/share/soulkiller/extra-memory-backup"
auto_push = true
init_if_missing = true

[backup_sources]
codex_custom_skills = "~/.codex/skills"
claude_projects = "~/.claude/projects"
"""


def write_default_config(path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config_text(), encoding="utf-8")
    return config_path
