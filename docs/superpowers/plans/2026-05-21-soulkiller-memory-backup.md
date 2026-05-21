# Codex Memory Snapshot Branches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Back up Codex memories into private backup repo branches without mutating the live `~/.codex/memories` source repo, and create snapshot commits only when content changes.

**Architecture:** The private backup repo becomes a multi-branch repo: `main` keeps the existing generated extra backup tree, `codex/source` mirrors the source Codex repo commit graph, and `codex/snapshots` stores append-only working-tree snapshots. Branch operations run through explicit git helpers and temporary worktrees so normal sync never leaves the backup repo checked out on the wrong branch.

**Tech Stack:** Python 3.12 standard library, pytest, git CLI, systemd/cron/tmux scheduler commands unchanged.

---

### Task 1: Config Schema And Status Output

**Files:**
- Modify: `src/soulkiller/config.py`
- Modify: `src/soulkiller/cli.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing config tests**

Add assertions to `tests/test_config.py` so default config exposes branch names:

```python
def test_write_and_load_default_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = default_config_path()

    write_default_config(path)
    config = load_config(path)

    assert config.codex_memories.enabled is True
    assert config.codex_memories.path == tmp_path / ".codex" / "memories"
    assert config.codex_memories.auto_push is True
    assert config.codex_memories.source_branch == "codex/source"
    assert config.codex_memories.snapshots_branch == "codex/snapshots"
    assert config.extra_backup.repo_path == tmp_path / ".local" / "share" / "soulkiller" / "extra-memory-backup"
    assert config.extra_backup.auto_push is True
    assert config.extra_backup.init_if_missing is True
    assert config.extra_backup.main_branch == "main"
    assert config.backup_sources.codex_custom_skills == tmp_path / ".codex" / "skills"
    assert config.backup_sources.claude_projects == tmp_path / ".claude" / "projects"
```

Extend `test_load_config_expands_user_paths` with:

```python
    assert config.codex_memories.source_branch == "codex/source"
    assert config.codex_memories.snapshots_branch == "codex/snapshots"
    assert config.extra_backup.main_branch == "main"
```

Add a custom branch-name case:

```python
def test_load_config_reads_branch_names(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[codex_memories]
enabled = true
path = "~/.codex/memories"
auto_push = false
source_branch = "backup/codex-source"
snapshots_branch = "backup/codex-snapshots"

[extra_backup]
enabled = true
repo_path = "~/extra"
auto_push = false
init_if_missing = true
main_branch = "backup/main"

[backup_sources]
codex_custom_skills = "~/.codex/skills"
claude_projects = "~/.claude/projects"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.codex_memories.source_branch == "backup/codex-source"
    assert config.codex_memories.snapshots_branch == "backup/codex-snapshots"
    assert config.extra_backup.main_branch == "backup/main"
```

- [ ] **Step 2: Write failing CLI status test**

Add to `tests/test_cli.py`:

```python
def test_cli_status_reports_backup_branches(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    init = run_cli("init-config")
    assert init.returncode == 0

    status = run_cli("status")

    assert status.returncode == 0
    assert "Codex source branch: codex/source" in status.stdout
    assert "Codex snapshots branch: codex/snapshots" in status.stdout
    assert "Extra backup main branch: main" in status.stdout
```

- [ ] **Step 3: Run failing tests**

Run: `pytest tests/test_config.py tests/test_cli.py -q`
Expected: FAIL because the dataclasses and status output do not expose branch names yet.

- [ ] **Step 4: Implement config fields**

Update `src/soulkiller/config.py`:

```python
@dataclass(frozen=True)
class CodexMemoriesConfig:
    enabled: bool
    path: Path
    auto_push: bool
    source_branch: str
    snapshots_branch: str


@dataclass(frozen=True)
class ExtraBackupConfig:
    enabled: bool
    repo_path: Path
    auto_push: bool
    init_if_missing: bool
    main_branch: str
```

Populate fields in `load_config()`:

```python
        codex_memories=CodexMemoriesConfig(
            enabled=_get_bool(codex, "enabled", True, "codex_memories"),
            path=expand_path(str(codex.get("path", "~/.codex/memories")), config_path.parent),
            auto_push=_get_bool(codex, "auto_push", True, "codex_memories"),
            source_branch=str(codex.get("source_branch", "codex/source")),
            snapshots_branch=str(codex.get("snapshots_branch", "codex/snapshots")),
        ),
        extra_backup=ExtraBackupConfig(
            enabled=_get_bool(extra, "enabled", True, "extra_backup"),
            repo_path=expand_path(str(extra.get("repo_path", "~/.local/share/soulkiller/extra-memory-backup")), config_path.parent),
            auto_push=_get_bool(extra, "auto_push", True, "extra_backup"),
            init_if_missing=_get_bool(extra, "init_if_missing", True, "extra_backup"),
            main_branch=str(extra.get("main_branch", "main")),
        ),
```

Update `default_config_text()` to include:

```toml
source_branch = "codex/source"
snapshots_branch = "codex/snapshots"
main_branch = "main"
```

- [ ] **Step 5: Implement status output**

Update `command_status()` in `src/soulkiller/cli.py`:

```python
    print(f"Codex source branch: {config.codex_memories.source_branch}")
    print(f"Codex snapshots branch: {config.codex_memories.snapshots_branch}")
    print(f"Extra backup main branch: {config.extra_backup.main_branch}")
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_config.py tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/soulkiller/config.py src/soulkiller/cli.py tests/test_config.py tests/test_cli.py
git commit -m "feat: configure backup branches"
```

### Task 2: Branch-Aware Git Helpers

**Files:**
- Modify: `src/soulkiller/git_ops.py`
- Modify: `tests/test_git_ops.py`

- [ ] **Step 1: Write failing helper tests**

Add to `tests/test_git_ops.py`:

```python
from soulkiller.git_ops import (
    branch_exists,
    commit_all_if_changed,
    ensure_branch_worktree,
    ensure_git_repo,
    has_remote,
    push_branch_if_configured,
    push_if_configured,
    update_branch_to_ref,
)
```

Add tests:

```python
def test_update_branch_to_ref_creates_or_moves_branch(tmp_path):
    ensure_git_repo(tmp_path)
    configure_identity(tmp_path)
    (tmp_path / "MEMORY.md").write_text("first\n", encoding="utf-8")
    first = commit_all_if_changed(tmp_path, "first")
    (tmp_path / "MEMORY.md").write_text("second\n", encoding="utf-8")
    second = commit_all_if_changed(tmp_path, "second")

    update_branch_to_ref(tmp_path, "codex/source", first.commit_hash)
    assert branch_exists(tmp_path, "codex/source")
    first_ref = run_git(tmp_path, "rev-parse", "codex/source").stdout.strip()

    update_branch_to_ref(tmp_path, "codex/source", second.commit_hash)
    second_ref = run_git(tmp_path, "rev-parse", "codex/source").stdout.strip()

    assert first_ref != second_ref
    assert second_ref == run_git(tmp_path, "rev-parse", second.commit_hash).stdout.strip()


def test_ensure_branch_worktree_creates_or_reuses_branch(tmp_path):
    ensure_git_repo(tmp_path)
    configure_identity(tmp_path)
    (tmp_path / "README.md").write_text("main\n", encoding="utf-8")
    commit_all_if_changed(tmp_path, "main")
    worktree_path = tmp_path.parent / "snapshot-worktree"

    ensure_branch_worktree(tmp_path, "codex/snapshots", worktree_path)
    (worktree_path / "MEMORY.md").write_text("snapshot\n", encoding="utf-8")
    commit_all_if_changed(worktree_path, "snapshot")
    ensure_branch_worktree(tmp_path, "codex/snapshots", worktree_path)

    assert run_git(worktree_path, "branch", "--show-current").stdout.strip() == "codex/snapshots"
    assert (worktree_path / "MEMORY.md").read_text(encoding="utf-8") == "snapshot\n"


def test_push_branch_if_configured_skips_without_remote(tmp_path):
    ensure_git_repo(tmp_path)
    configure_identity(tmp_path)
    (tmp_path / "MEMORY.md").write_text("hello\n", encoding="utf-8")
    commit_all_if_changed(tmp_path, "backup: test")

    result = push_branch_if_configured(tmp_path, "codex/snapshots", auto_push=True, force_with_lease=False)

    assert result.pushed is False
    assert "no git remote" in result.message
```

- [ ] **Step 2: Run failing tests**

Run: `pytest tests/test_git_ops.py -q`
Expected: FAIL because the new helpers do not exist.

- [ ] **Step 3: Implement helper functions**

Add to `src/soulkiller/git_ops.py`:

```python
def branch_exists(repo: Path, branch: str) -> bool:
    result = run_git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    return result.returncode == 0


def update_branch_to_ref(repo: Path, branch: str, ref: str) -> None:
    run_git(repo, "branch", "-f", branch, ref)


def ensure_branch_worktree(repo: Path, branch: str, worktree_path: Path) -> None:
    if worktree_path.exists():
        result = run_git(worktree_path, "branch", "--show-current", check=False)
        if result.returncode == 0 and result.stdout.strip() == branch:
            run_git(worktree_path, "reset", "--hard")
            run_git(worktree_path, "clean", "-fd")
            return
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], check=False, text=True, capture_output=True)
    if branch_exists(repo, branch):
        subprocess.run(["git", "-C", str(repo), "worktree", "add", str(worktree_path), branch], check=True, text=True, capture_output=True)
    else:
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-b", branch, str(worktree_path)], check=True, text=True, capture_output=True)


def remove_worktree(repo: Path, worktree_path: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree_path)], check=False, text=True, capture_output=True)


def push_branch_if_configured(repo: Path, branch: str, auto_push: bool, force_with_lease: bool = False) -> PushResult:
    if not auto_push:
        return PushResult(pushed=False, message="auto_push disabled")
    if not has_remote(repo):
        return PushResult(pushed=False, message="no git remote configured; push skipped")
    refspec = f"{branch}:{branch}"
    args = ["push", "origin", refspec]
    if force_with_lease:
        args.insert(1, "--force-with-lease")
    run_git(repo, *args)
    return PushResult(pushed=True, message=f"pushed {branch}")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_git_ops.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/soulkiller/git_ops.py tests/test_git_ops.py
git commit -m "feat: add branch git helpers"
```

### Task 3: Codex Snapshot Sync

**Files:**
- Modify: `src/soulkiller/sync.py`
- Modify: `tests/test_sync.py`

- [ ] **Step 1: Update test config factory**

Update `make_config()` in `tests/test_sync.py` so dataclasses include:

```python
codex_memories=CodexMemoriesConfig(
    enabled=True,
    path=codex_memories,
    auto_push=False,
    source_branch="codex/source",
    snapshots_branch="codex/snapshots",
),
extra_backup=ExtraBackupConfig(
    enabled=True,
    repo_path=extra_repo,
    auto_push=False,
    init_if_missing=True,
    main_branch="main",
),
```

- [ ] **Step 2: Write failing source-immutability test**

Add to `tests/test_sync.py`:

```python
def test_sync_codex_snapshots_do_not_commit_source_repo(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    (config.codex_memories.path / "MEMORY.md").write_text("original\n", encoding="utf-8")
    commit = subprocess.run(
        ["git", "-C", str(config.codex_memories.path), "add", "-A"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert commit.returncode == 0
    subprocess.run(["git", "-C", str(config.codex_memories.path), "commit", "-m", "initial"], check=True)
    source_head = subprocess.run(
        ["git", "-C", str(config.codex_memories.path), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    (config.codex_memories.path / "MEMORY.md").write_text("changed working tree\n", encoding="utf-8")

    result = sync_all(config)

    assert result.codex.committed is True
    assert result.codex.commit_message.startswith("snapshot:")
    assert subprocess.run(
        ["git", "-C", str(config.codex_memories.path), "rev-list", "--count", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip() == "1"
    assert subprocess.run(
        ["git", "-C", str(config.codex_memories.path), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip() == source_head
    assert subprocess.run(
        ["git", "-C", str(config.codex_memories.path), "status", "--porcelain"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip() == " M MEMORY.md"
```

- [ ] **Step 3: Write failing branch-layout and no-empty-snapshot tests**

Add to `tests/test_sync.py`:

```python
def test_sync_codex_writes_source_and_snapshot_branches(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    (config.codex_memories.path / "nested").mkdir()
    (config.codex_memories.path / "nested" / "note.md").write_text("note\n", encoding="utf-8")
    commit_all_if_changed(config.codex_memories.path, "initial")

    result = sync_all(config)

    assert result.codex.committed is True
    source_tree = subprocess.run(
        ["git", "-C", str(config.extra_backup.repo_path), "ls-tree", "-r", "--name-only", "codex/source"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    snapshot_tree = subprocess.run(
        ["git", "-C", str(config.extra_backup.repo_path), "ls-tree", "-r", "--name-only", "codex/snapshots"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    assert source_tree == ["nested/note.md"]
    assert snapshot_tree == ["nested/note.md"]


def test_sync_codex_second_run_does_not_create_empty_snapshot(tmp_path):
    config = make_config(tmp_path)
    config.codex_memories.path.mkdir()
    ensure_git_repo(config.codex_memories.path)
    configure_identity(config.codex_memories.path)
    (config.codex_memories.path / "MEMORY.md").write_text("same\n", encoding="utf-8")
    commit_all_if_changed(config.codex_memories.path, "initial")

    first = sync_all(config)
    first_snapshot = subprocess.run(
        ["git", "-C", str(config.extra_backup.repo_path), "rev-parse", "codex/snapshots"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    second = sync_all(config)
    second_snapshot = subprocess.run(
        ["git", "-C", str(config.extra_backup.repo_path), "rev-parse", "codex/snapshots"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()

    assert first.codex.committed is True
    assert second.codex.committed is False
    assert first_snapshot == second_snapshot
```

- [ ] **Step 4: Run failing tests**

Run: `pytest tests/test_sync.py -q`
Expected: FAIL because current code commits the source repo in place.

- [ ] **Step 5: Implement Codex snapshot sync**

Update imports in `src/soulkiller/sync.py` to include `subprocess`, and import:

```python
from .git_ops import branch_exists, ensure_branch_worktree, remove_worktree, run_git, update_branch_to_ref, push_branch_if_configured
```

Add helper functions:

```python
def _git_stdout(repo: Path, *args: str, check: bool = True) -> str:
    return run_git(repo, *args, check=check).stdout.strip()


def _source_branch(repo: Path) -> str:
    branch = _git_stdout(repo, "branch", "--show-current", check=False)
    return branch or "detached"


def _source_head(repo: Path) -> str:
    return _git_stdout(repo, "rev-parse", "HEAD")


def _source_dirty(repo: Path) -> bool:
    return bool(_git_stdout(repo, "status", "--porcelain"))


def _replace_tree_from_source(source: Path, dest: Path) -> int:
    copied = 0
    for child in dest.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    copied = _copy_tree(source, dest)
    return copied


def _snapshot_message(source: Path, source_head: str, source_branch: str, dirty: bool) -> str:
    now = _timestamp()
    return (
        f"snapshot: codex memories {now}\n\n"
        f"Source-Path: {source}\n"
        f"Source-Head: {source_head}\n"
        f"Source-Branch: {source_branch}\n"
        f"Source-Dirty: {str(dirty).lower()}\n"
        f"Snapshot-Time: {now}\n"
    )
```

Rewrite `sync_codex_memories()` so it ensures `extra_backup.repo_path` exists, creates the source mirror branch, snapshots through a temporary worktree, commits only on diff, pushes explicit branches, and never calls `commit_all_if_changed(section.path, ...)` on the source repo.

- [ ] **Step 6: Preserve extra backup on main branch**

In `sync_extra_backup()`, ensure work happens on `config.extra_backup.main_branch`. Use `ensure_branch_worktree()` with a temporary worktree for the main branch, run the existing mirror/scan/commit flow there, push the explicit main branch, and remove the temporary worktree in a `finally` block.

- [ ] **Step 7: Run sync tests**

Run: `pytest tests/test_sync.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/soulkiller/sync.py tests/test_sync.py
git commit -m "feat: snapshot codex memories to backup branches"
```

### Task 4: Ref-Aware Restore

**Files:**
- Modify: `src/soulkiller/restore.py`
- Modify: `src/soulkiller/cli.py`
- Modify: `tests/test_timer_restore.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing restore tests**

Add to `tests/test_timer_restore.py`:

```python
from soulkiller.restore import list_codex_snapshots, restore_codex_snapshot_to_staging
from soulkiller.git_ops import commit_all_if_changed, ensure_git_repo, update_branch_to_ref
```

Update `make_config()` with branch fields as in Task 3.

Add:

```python
def test_list_codex_snapshots_returns_snapshot_commits(tmp_path):
    config = make_config(tmp_path)
    repo = config.extra_backup.repo_path
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("snapshot\n", encoding="utf-8")
    commit = commit_all_if_changed(repo, "snapshot: codex memories")
    update_branch_to_ref(repo, "codex/snapshots", commit.commit_hash)

    snapshots = list_codex_snapshots(config)

    assert snapshots == [commit.commit_hash]


def test_restore_codex_snapshot_to_staging_copies_selected_ref(tmp_path):
    config = make_config(tmp_path)
    repo = config.extra_backup.repo_path
    ensure_git_repo(repo)
    configure_identity(repo)
    (repo / "MEMORY.md").write_text("snapshot\n", encoding="utf-8")
    commit = commit_all_if_changed(repo, "snapshot: codex memories")
    update_branch_to_ref(repo, "codex/snapshots", commit.commit_hash)
    staging = tmp_path / "staging"

    result = restore_codex_snapshot_to_staging(config, "latest", staging)

    assert result.copied_files == 1
    assert (staging / "MEMORY.md").read_text(encoding="utf-8") == "snapshot\n"
```

- [ ] **Step 2: Write failing CLI restore tests**

Add to `tests/test_cli.py`:

```python
def test_restore_parser_accepts_codex_snapshot_options():
    from soulkiller.cli import build_parser

    args = build_parser().parse_args(["restore", "--source", "codex", "--snapshot", "latest", "--staging-dir", "/tmp/stage"])

    assert args.source == "codex"
    assert args.snapshot == "latest"
    assert args.staging_dir == "/tmp/stage"
```

- [ ] **Step 3: Run failing tests**

Run: `pytest tests/test_timer_restore.py tests/test_cli.py -q`
Expected: FAIL because restore is not ref-aware yet.

- [ ] **Step 4: Implement ref-aware restore**

Add to `src/soulkiller/restore.py`:

```python
from .git_ops import run_git


def list_codex_snapshots(config: Config) -> list[str]:
    repo = config.extra_backup.repo_path
    branch = config.codex_memories.snapshots_branch
    result = run_git(repo, "rev-list", "--max-count=20", "--abbrev-commit", branch, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _clear_staging_dir(staging_dir: Path) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    for child in staging_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _archive_ref_to_staging(repo: Path, ref: str, staging_dir: Path) -> int:
    _clear_staging_dir(staging_dir)
    files = run_git(repo, "ls-tree", "-r", "--name-only", ref).stdout.splitlines()
    for rel in files:
        target = staging_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        content = run_git(repo, "show", f"{ref}:{rel}").stdout
        target.write_text(content, encoding="utf-8")
    return len(files)


def restore_codex_snapshot_to_staging(config: Config, snapshot: str, staging_dir: Path) -> RestoreResult:
    ref = config.codex_memories.snapshots_branch if snapshot == "latest" else snapshot
    copied = _archive_ref_to_staging(config.extra_backup.repo_path, ref, staging_dir)
    return RestoreResult(staging_dir=staging_dir, copied_files=copied)
```

- [ ] **Step 5: Implement CLI restore options**

Update restore parser with:

```python
    restore_parser.add_argument("--source", choices=["extra", "codex"], default="extra")
    restore_parser.add_argument("--snapshot", default="latest")
    restore_parser.add_argument("--list-snapshots", action="store_true")
```

Update `command_restore()` to list snapshots or stage Codex snapshot when `args.source == "codex"`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_timer_restore.py tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/soulkiller/restore.py src/soulkiller/cli.py tests/test_timer_restore.py tests/test_cli.py
git commit -m "feat: restore codex snapshots by ref"
```

### Task 5: Docs And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-21-soulkiller-memory-backup-design.md`
- Modify: `docs/superpowers/plans/2026-05-21-soulkiller-memory-backup.md`

- [ ] **Step 1: Update README**

Replace the README Codex memory section with wording that says Soulkiller reads `~/.codex/memories` as source, writes `codex/source` and `codex/snapshots` branches in the private backup repo, and creates no empty snapshot commits.

- [ ] **Step 2: Run full tests**

Run: `pytest -q`
Expected: PASS with all tests.

- [ ] **Step 3: Run CLI smoke tests**

Run:

```bash
./bin/soulkiller --help
./bin/soulkiller restore --help
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Commit docs**

```bash
git add README.md docs/superpowers/specs/2026-05-21-soulkiller-memory-backup-design.md docs/superpowers/plans/2026-05-21-soulkiller-memory-backup.md
git commit -m "docs: document snapshot branch backups"
```

- [ ] **Step 5: Final status**

Run:

```bash
git status --short --branch
git log --oneline --max-count=6
```

Expected: clean worktree on `siyuan/memory-snapshot-backups`, ahead of `origin/main` by the implementation commits.
