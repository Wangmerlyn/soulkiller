from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
import fcntl
import json
import shutil
import tempfile

from .config import Config
from .git_ops import (
    PushResult,
    branch_exists,
    commit_all_if_changed,
    ensure_branch_worktree,
    ensure_git_repo,
    is_git_repo,
    push_branch_if_configured,
    remove_worktree,
    run_git,
)
from .scanner import ScanResult, scan_tree


@dataclass(frozen=True)
class RepoSyncResult:
    name: str
    path: Path
    scan: ScanResult
    committed: bool
    commit_hash: str | None
    commit_message: str
    pushed: bool
    push_message: str
    scan_skipped: bool = False
    skipped: bool = False
    error: str | None = None


@dataclass(frozen=True)
class SyncResult:
    codex: RepoSyncResult
    extra: RepoSyncResult


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def default_lock_path() -> Path:
    return Path("~/.local/state/soulkiller/sync.lock").expanduser()


@contextmanager
def _sync_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _disabled_result(name: str, path: Path) -> RepoSyncResult:
    return RepoSyncResult(
        name=name,
        path=path,
        scan=ScanResult(root=path, issues=[]),
        committed=False,
        commit_hash=None,
        commit_message="disabled",
        pushed=False,
        push_message="disabled",
        scan_skipped=True,
        skipped=True,
    )


def _failed_scan_result(name: str, path: Path, scan: ScanResult) -> RepoSyncResult:
    return RepoSyncResult(
        name=name,
        path=path,
        scan=scan,
        committed=False,
        commit_hash=None,
        commit_message="safety scan failed",
        pushed=False,
        push_message="not pushed",
        error="safety scan failed",
    )


def _busy_result(name: str, path: Path) -> RepoSyncResult:
    return RepoSyncResult(
        name=name,
        path=path,
        scan=ScanResult(root=path, issues=[]),
        committed=False,
        commit_hash=None,
        commit_message="sync lock busy",
        pushed=False,
        push_message="not pushed",
        error="another sync is already running",
    )


def _missing_backup_repo_result(name: str, path: Path, repo: Path) -> RepoSyncResult:
    return RepoSyncResult(
        name=name,
        path=path,
        scan=ScanResult(root=path, issues=[]),
        committed=False,
        commit_hash=None,
        commit_message="repo missing",
        pushed=False,
        push_message="not pushed",
        scan_skipped=True,
        error=f"repo missing: {repo}",
    )


def _ensure_repo_head(repo: Path) -> None:
    ensure_git_repo(repo)
    head = run_git(repo, "rev-parse", "--verify", "HEAD", check=False)
    if head.returncode != 0:
        run_git(repo, "commit", "--allow-empty", "-m", "init: soulkiller backup repo")


def _remove_non_git_contents(path: Path) -> None:
    for child in path.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def _combine_push_results(results: list[PushResult]) -> PushResult:
    if not results:
        return PushResult(False, "no changes")
    return PushResult(
        pushed=any(result.pushed for result in results),
        message="; ".join(result.message for result in results),
    )


def _push_branch_if_configured(repo: Path, branch: str, auto_push: bool, force_with_lease: bool) -> PushResult:
    result = push_branch_if_configured(repo, branch, auto_push, force_with_lease=force_with_lease)
    return PushResult(result.pushed, f"{branch}: {result.message}")


def sync_codex_memories(config: Config) -> RepoSyncResult:
    section = config.codex_memories
    if not section.enabled:
        return _disabled_result("codex memories", section.path)
    if not section.path.exists() or not is_git_repo(section.path):
        return RepoSyncResult(
            name="codex memories",
            path=section.path,
            scan=ScanResult(root=section.path, issues=[]),
            committed=False,
            commit_hash=None,
            commit_message="not a git repository",
            pushed=False,
            push_message="not pushed",
            error=f"not a git repository: {section.path}",
        )

    backup_repo = config.extra_backup.repo_path
    if not backup_repo.exists() and not config.extra_backup.init_if_missing:
        return _missing_backup_repo_result("codex memories", section.path, backup_repo)

    _ensure_repo_head(backup_repo)

    source_branch_updated = False
    source_head = run_git(section.path, "rev-parse", "--verify", "HEAD", check=False)
    if source_head.returncode == 0:
        source_ref = source_head.stdout.strip()
        previous_source_ref = None
        if branch_exists(backup_repo, section.source_branch):
            previous_source_ref = run_git(backup_repo, "rev-parse", section.source_branch).stdout.strip()
        run_git(backup_repo, "fetch", str(section.path), f"+{source_ref}:refs/heads/{section.source_branch}")
        source_branch_updated = previous_source_ref != source_ref

    current_branch = run_git(backup_repo, "branch", "--show-current", check=False).stdout.strip()
    use_current_snapshot_worktree = current_branch == section.snapshots_branch
    with tempfile.TemporaryDirectory(prefix="soulkiller-codex-snapshot-") as tmp:
        snapshot_worktree = backup_repo if use_current_snapshot_worktree else Path(tmp) / "snapshot"
        try:
            if not use_current_snapshot_worktree:
                ensure_branch_worktree(backup_repo, section.snapshots_branch, snapshot_worktree)
            _remove_non_git_contents(snapshot_worktree)
            _copy_tree(section.path, snapshot_worktree)
            commit = commit_all_if_changed(snapshot_worktree, f"snapshot: codex memories {_timestamp()}")
        finally:
            if not use_current_snapshot_worktree and snapshot_worktree.exists():
                remove_worktree(backup_repo, snapshot_worktree)

    push_results: list[PushResult] = []
    if source_branch_updated:
        push_results.append(
            _push_branch_if_configured(
                backup_repo,
                section.source_branch,
                section.auto_push,
                force_with_lease=True,
            )
        )
    if commit.committed:
        push_results.append(
            _push_branch_if_configured(
                backup_repo,
                section.snapshots_branch,
                section.auto_push,
                force_with_lease=False,
            )
        )
    push = _combine_push_results(push_results)
    return RepoSyncResult(
        name="codex memories",
        path=section.path,
        scan=ScanResult(root=section.path, issues=[]),
        committed=commit.committed,
        commit_hash=commit.commit_hash,
        commit_message=commit.message,
        pushed=push.pushed,
        push_message=push.message,
        scan_skipped=True,
    )


def _copy_tree(source: Path, dest: Path) -> int:
    copied = 0
    if not source.exists():
        return copied
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(source)
        if any(part in {".git", "__pycache__"} for part in rel.parts):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def mirror_extra_sources(config: Config, target_root: Path | None = None) -> dict[str, object]:
    repo = target_root or config.extra_backup.repo_path
    copied_skills = 0
    copied_claude = 0
    skipped: list[str] = []

    codex_skills_dest = repo / "codex" / "skills"
    claude_dest = repo / "claude" / "project-memories"
    shutil.rmtree(codex_skills_dest, ignore_errors=True)
    shutil.rmtree(claude_dest, ignore_errors=True)
    codex_skills_dest.mkdir(parents=True, exist_ok=True)
    claude_dest.mkdir(parents=True, exist_ok=True)

    skills_root = config.backup_sources.codex_custom_skills
    if skills_root.exists():
        for skill in sorted(skills_root.iterdir()):
            if not skill.is_dir():
                continue
            if skill.name == ".system":
                skipped.append(str(skill))
                continue
            copied_skills += _copy_tree(skill, codex_skills_dest / skill.name)
    else:
        skipped.append(str(skills_root))

    claude_root = config.backup_sources.claude_projects
    if claude_root.exists():
        for project in sorted(claude_root.iterdir()):
            memory = project / "memory"
            if project.is_dir() and memory.is_dir():
                copied_claude += _copy_tree(memory, claude_dest / project.name / "memory")
    else:
        skipped.append(str(claude_root))

    manifest = {
        "extra_backup_repo": str(config.extra_backup.repo_path),
        "sources": {
            "codex_custom_skills": str(skills_root),
            "claude_projects": str(claude_root),
        },
        "copied": {
            "codex_skill_files": copied_skills,
            "claude_memory_files": copied_claude,
        },
        "skipped": skipped,
    }
    manifest_path = repo / "manifests" / "snapshot.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def sync_extra_backup(config: Config) -> RepoSyncResult:
    section = config.extra_backup
    if not section.enabled:
        return _disabled_result("extra backup", section.repo_path)
    if not section.repo_path.exists() and not section.init_if_missing:
        return RepoSyncResult(
            name="extra backup",
            path=section.repo_path,
            scan=ScanResult(root=section.repo_path, issues=[]),
            committed=False,
            commit_hash=None,
            commit_message="repo missing",
            pushed=False,
            push_message="not pushed",
            error=f"repo does not exist: {section.repo_path}",
        )

    _ensure_repo_head(section.repo_path)
    with tempfile.TemporaryDirectory(prefix="soulkiller-extra-") as tmp:
        tmp_root = Path(tmp)
        staged_root = tmp_root / "staged"
        mirror_extra_sources(config, staged_root)
        scan = scan_tree(staged_root)
        if not scan.ok:
            return _failed_scan_result("extra backup", section.repo_path, scan)

        current_branch = run_git(section.repo_path, "branch", "--show-current", check=False).stdout.strip()
        use_current_worktree = current_branch == section.main_branch
        sync_root = section.repo_path if use_current_worktree else tmp_root / "repo"
        try:
            if not use_current_worktree:
                ensure_branch_worktree(section.repo_path, section.main_branch, sync_root)

            for name in ("codex", "claude", "manifests"):
                destination = sync_root / name
                shutil.rmtree(destination, ignore_errors=True)
                source = staged_root / name
                if source.exists():
                    shutil.copytree(source, destination)
            repo_scan = scan_tree(sync_root)
            if not repo_scan.ok:
                return _failed_scan_result("extra backup", section.repo_path, repo_scan)

            commit = commit_all_if_changed(sync_root, f"backup: extra memory {_timestamp()}")
        finally:
            if not use_current_worktree and sync_root.exists():
                remove_worktree(section.repo_path, sync_root)

    if commit.committed:
        push = push_branch_if_configured(section.repo_path, section.main_branch, section.auto_push)
    else:
        push = PushResult(False, "no changes")
    return RepoSyncResult(
        name="extra backup",
        path=section.repo_path,
        scan=scan,
        committed=commit.committed,
        commit_hash=commit.commit_hash,
        commit_message=commit.message,
        pushed=push.pushed,
        push_message=push.message,
    )


def sync_all(config: Config, lock_path: Path | None = None) -> SyncResult:
    with _sync_lock(lock_path or default_lock_path()) as acquired:
        if not acquired:
            return SyncResult(
                codex=_busy_result("codex memories", config.codex_memories.path),
                extra=_busy_result("extra backup", config.extra_backup.repo_path),
            )
        return SyncResult(codex=sync_codex_memories(config), extra=sync_extra_backup(config))
