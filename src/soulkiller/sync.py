from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import tempfile

from .config import Config
from .git_ops import CommitResult, PushResult, commit_all_if_changed, ensure_git_repo, is_git_repo, push_if_configured
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
    skipped: bool = False
    error: str | None = None


@dataclass(frozen=True)
class SyncResult:
    codex: RepoSyncResult
    extra: RepoSyncResult


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


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

    scan = scan_tree(section.path)
    if not scan.ok:
        return _failed_scan_result("codex memories", section.path, scan)

    commit = commit_all_if_changed(section.path, f"backup: codex memories {_timestamp()}")
    push = push_if_configured(section.path, section.auto_push) if commit.committed else PushResult(False, "no changes")
    return RepoSyncResult(
        name="codex memories",
        path=section.path,
        scan=scan,
        committed=commit.committed,
        commit_hash=commit.commit_hash,
        commit_message=commit.message,
        pushed=push.pushed,
        push_message=push.message,
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

    ensure_git_repo(section.repo_path)
    with tempfile.TemporaryDirectory(prefix="soulkiller-extra-") as tmp:
        staged_root = Path(tmp)
        mirror_extra_sources(config, staged_root)
        scan = scan_tree(staged_root)
        if not scan.ok:
            return _failed_scan_result("extra backup", section.repo_path, scan)

        for name in ("codex", "claude", "manifests"):
            destination = section.repo_path / name
            shutil.rmtree(destination, ignore_errors=True)
            source = staged_root / name
            if source.exists():
                shutil.copytree(source, destination)

    commit = commit_all_if_changed(section.repo_path, f"backup: extra memory {_timestamp()}")
    push = push_if_configured(section.repo_path, section.auto_push) if commit.committed else PushResult(False, "no changes")
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


def sync_all(config: Config) -> SyncResult:
    return SyncResult(codex=sync_codex_memories(config), extra=sync_extra_backup(config))
