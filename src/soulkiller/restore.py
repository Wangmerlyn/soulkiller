from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from .config import Config


@dataclass(frozen=True)
class RestoreResult:
    staging_dir: Path
    copied_files: int


def _copy_tree(source: Path, dest: Path) -> int:
    copied = 0
    if not source.exists():
        return copied
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(source)
        if ".git" in rel.parts:
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def restore_to_staging(config: Config, staging_dir: Path) -> RestoreResult:
    staging_dir.mkdir(parents=True, exist_ok=True)
    copied = _copy_tree(config.extra_backup.repo_path, staging_dir)
    return RestoreResult(staging_dir=staging_dir, copied_files=copied)


def restore_dry_run(config: Config) -> list[str]:
    repo = config.extra_backup.repo_path
    if not repo.exists():
        return [f"extra backup repo does not exist: {repo}"]
    return [str(path.relative_to(repo)) for path in sorted(repo.rglob("*")) if path.is_file() and ".git" not in path.parts]
