from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

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


def _remove_path(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def _clear_directory(path: Path) -> None:
    _remove_path(path)
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


def _codex_snapshot_ref(config: Config, snapshot: str) -> str:
    return config.codex_memories.snapshots_branch if snapshot == "latest" else snapshot


def _git_error(result: subprocess.CompletedProcess[str]) -> str:
    details = [detail for detail in (result.stderr.strip(), result.stdout.strip()) if detail]
    return "\n".join(details) if details else "unknown git error"


def _resolve_codex_snapshot_tree(config: Config, snapshot: str) -> str:
    ref = _codex_snapshot_ref(config, snapshot)
    result = run_git(
        config.extra_backup.repo_path,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{ref}^{{tree}}",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"failed to resolve codex snapshot {ref}: {_git_error(result)}")
    return result.stdout.strip()


def _archive_tree(repo: Path, tree_oid: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", tree_oid],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        reason = result.stderr.decode("utf-8", errors="replace").strip() or "unknown git archive error"
        raise RuntimeError(f"failed to archive codex snapshot tree {tree_oid}: {reason}")
    return result.stdout


def restore_codex_dry_run(config: Config, snapshot: str) -> list[str]:
    tree_oid = _resolve_codex_snapshot_tree(config, snapshot)
    result = run_git(config.extra_backup.repo_path, "ls-tree", "-r", "--name-only", tree_oid)
    return result.stdout.splitlines()


def restore_codex_snapshot_to_staging(config: Config, snapshot: str, staging_dir: Path) -> RestoreResult:
    tree_oid = _resolve_codex_snapshot_tree(config, snapshot)
    archive = _archive_tree(config.extra_backup.repo_path, tree_oid)
    staging_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{staging_dir.name}.", dir=staging_dir.parent))
    try:
        copied = _copy_archive_to_staging(archive, temp_dir)
        if staging_dir.exists() or staging_dir.is_symlink():
            _remove_path(staging_dir)
        temp_dir.rename(staging_dir)
        temp_dir = staging_dir
    finally:
        if temp_dir != staging_dir and (temp_dir.exists() or temp_dir.is_symlink()):
            _remove_path(temp_dir)
    return RestoreResult(staging_dir=staging_dir, copied_files=copied)


def restore_dry_run(config: Config) -> list[str]:
    repo = config.extra_backup.repo_path
    if not repo.exists():
        return [f"extra backup repo does not exist: {repo}"]
    return [str(path.relative_to(repo)) for path in sorted(repo.rglob("*")) if path.is_file() and ".git" not in path.parts]
