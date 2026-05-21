from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path
import shutil
import subprocess
import tarfile

from .config import Config
from .git_ops import run_git


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


def list_codex_snapshots(config: Config) -> list[str]:
    result = run_git(
        config.extra_backup.repo_path,
        "rev-list",
        "--max-count=20",
        "--abbrev-commit",
        config.codex_memories.snapshots_branch,
        check=False,
    )
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def _clear_directory(path: Path) -> None:
    if path.exists():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.mkdir(parents=True, exist_ok=True)


def _copy_archive_to_staging(archive_bytes: bytes, staging_dir: Path) -> int:
    copied = 0
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        for member in archive.getmembers():
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts:
                raise RuntimeError(f"unsafe archive path: {member.name}")
            if ".git" in rel.parts:
                continue
            target = staging_dir / rel
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                source = archive.extractfile(member)
                if source is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                copied += 1
    return copied


def restore_codex_snapshot_to_staging(config: Config, snapshot: str, staging_dir: Path) -> RestoreResult:
    ref = config.codex_memories.snapshots_branch if snapshot == "latest" else snapshot
    result = subprocess.run(
        ["git", "-C", str(config.extra_backup.repo_path), "archive", "--format=tar", ref],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        reason = result.stderr.decode("utf-8", errors="replace").strip() or "unknown git archive error"
        raise RuntimeError(f"failed to archive codex snapshot {ref}: {reason}")

    _clear_directory(staging_dir)
    copied = _copy_archive_to_staging(result.stdout, staging_dir)
    return RestoreResult(staging_dir=staging_dir, copied_files=copied)


def restore_dry_run(config: Config) -> list[str]:
    repo = config.extra_backup.repo_path
    if not repo.exists():
        return [f"extra backup repo does not exist: {repo}"]
    return [str(path.relative_to(repo)) for path in sorted(repo.rglob("*")) if path.is_file() and ".git" not in path.parts]
