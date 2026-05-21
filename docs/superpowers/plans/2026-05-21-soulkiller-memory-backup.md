# Soulkiller Memory Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that commits and schedules backups for Codex memories plus extra Claude memory and custom Codex skills.

**Architecture:** The CLI reads a TOML config, performs safety scanning before commits, syncs Codex memories in place, mirrors extra memory sources into a private extra repo, and installs a systemd user timer. The code is split into small standard-library modules for config, git operations, safety scanning, sync orchestration, timer installation, restore, and CLI parsing.

**Tech Stack:** Python 3.12 standard library, pytest for tests, git CLI, systemd user units.

---

### Task 1: Project Skeleton And Config

**Files:**
- Create: `pyproject.toml`
- Create: `src/soulkiller/__init__.py`
- Create: `src/soulkiller/__main__.py`
- Create: `src/soulkiller/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

```python
from pathlib import Path

from soulkiller.config import Config, default_config_path, load_config, write_default_config


def test_write_and_load_default_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = default_config_path()

    write_default_config(path)
    config = load_config(path)

    assert config.codex_memories.enabled is True
    assert config.codex_memories.path == tmp_path / ".codex" / "memories"
    assert config.extra_backup.repo_path == tmp_path / ".local" / "share" / "soulkiller" / "extra-memory-backup"
    assert config.backup_sources.claude_projects == tmp_path / ".claude" / "projects"


def test_load_config_rejects_missing_file(tmp_path):
    missing = tmp_path / "missing.toml"

    try:
        load_config(missing)
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_config.py -q`
Expected: FAIL because `soulkiller.config` does not exist.

- [ ] **Step 3: Implement config module and package skeleton**

Implement dataclasses for config sections, TOML parsing with `tomllib`, TOML writing for defaults, and `~` expansion.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add pyproject.toml src tests docs/superpowers
git commit -m "docs: add memory backup design and plan"
git add pyproject.toml src/soulkiller tests/test_config.py
git commit -m "feat: add soulkiller config loading"
```

### Task 2: Safety Scanner

**Files:**
- Create: `src/soulkiller/scanner.py`
- Test: `tests/test_scanner.py`

- [ ] **Step 1: Write failing scanner tests**

```python
from pathlib import Path

from soulkiller.scanner import scan_tree


def test_scan_tree_rejects_secret_filename(tmp_path):
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("auth.json" in issue.path for issue in result.issues)


def test_scan_tree_rejects_secret_content(tmp_path):
    file_path = tmp_path / "note.md"
    file_path.write_text("api_key = 'abc123'\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert not result.ok
    assert any("api_key" in issue.message for issue in result.issues)


def test_scan_tree_allows_plain_memory_text(tmp_path):
    file_path = tmp_path / "MEMORY.md"
    file_path.write_text("remember this workflow preference\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert result.ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_scanner.py -q`
Expected: FAIL because `soulkiller.scanner` does not exist.

- [ ] **Step 3: Implement scanner**

Implement path denylist, content denylist, binary detection, max file size checks, and structured scan results.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/test_scanner.py -q`
Expected: PASS.

### Task 3: Git Operations

**Files:**
- Create: `src/soulkiller/git_ops.py`
- Test: `tests/test_git_ops.py`

- [ ] **Step 1: Write failing git operation tests**

```python
import subprocess

from soulkiller.git_ops import commit_all_if_changed, ensure_git_repo, has_remote, push_if_configured


def run_git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True, text=True, capture_output=True)


def test_commit_all_if_changed_commits_only_when_needed(tmp_path):
    ensure_git_repo(tmp_path)
    run_git(tmp_path, "config", "user.email", "test@example.com")
    run_git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "MEMORY.md").write_text("hello\n", encoding="utf-8")

    first = commit_all_if_changed(tmp_path, "backup: test")
    second = commit_all_if_changed(tmp_path, "backup: test")

    assert first.committed is True
    assert second.committed is False


def test_has_remote_false_for_new_repo(tmp_path):
    ensure_git_repo(tmp_path)

    assert has_remote(tmp_path) is False


def test_push_if_configured_skips_without_remote(tmp_path):
    ensure_git_repo(tmp_path)

    result = push_if_configured(tmp_path, auto_push=True)

    assert result.pushed is False
    assert "no git remote" in result.message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_git_ops.py -q`
Expected: FAIL because `soulkiller.git_ops` does not exist.

- [ ] **Step 3: Implement git helpers**

Implement git repo initialization, dirty check, commit-if-changed, remote detection, and push skipping when no remote exists.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/test_git_ops.py -q`
Expected: PASS.

### Task 4: Sync And CLI

**Files:**
- Create: `src/soulkiller/sync.py`
- Create: `src/soulkiller/cli.py`
- Test: `tests/test_sync.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing sync and CLI tests**

Create tests that verify extra backup mirrors Claude project memory and non-system Codex skills, writes `manifests/snapshot.json`, commits changes, and that `soulkiller status` reports configured paths.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=src pytest tests/test_sync.py tests/test_cli.py -q`
Expected: FAIL because sync and CLI modules do not exist.

- [ ] **Step 3: Implement sync and CLI**

Implement `init-config`, `status`, `sync`, `install-timer`, and `restore` command dispatch with argparse.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/test_sync.py tests/test_cli.py -q`
Expected: PASS.

### Task 5: Timer And Restore

**Files:**
- Create: `src/soulkiller/timer.py`
- Create: `src/soulkiller/restore.py`
- Test: `tests/test_timer_restore.py`
- Create: `README.md`

- [ ] **Step 1: Write failing timer and restore tests**

Create tests that verify systemd unit content, timer content, dry-run restore output, and staging restore copy behavior.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=src pytest tests/test_timer_restore.py -q`
Expected: FAIL because timer and restore modules do not exist.

- [ ] **Step 3: Implement timer, restore, and README**

Implement systemd user unit generation, optional enabling, dry-run restore, staging restore, and usage docs.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/test_timer_restore.py -q`
Expected: PASS.

### Task 6: Enable Local Backup

**Files:**
- Runtime config: `~/.config/soulkiller/config.toml`
- Runtime timer units: `~/.config/systemd/user/soulkiller.service`
- Runtime timer units: `~/.config/systemd/user/soulkiller.timer`

- [ ] **Step 1: Run full test suite**

Run: `PYTHONPATH=src pytest -q`
Expected: PASS.

- [ ] **Step 2: Create or preserve config**

Run: `PYTHONPATH=src python -m soulkiller init-config`
Expected: Creates config if missing and preserves it if present.

- [ ] **Step 3: Run sync**

Run: `PYTHONPATH=src python -m soulkiller sync`
Expected: Codex memories are committed if dirty; extra backup repo is initialized and committed; push is skipped when no remote exists.

- [ ] **Step 4: Install and enable timer**

Run: `PYTHONPATH=src python -m soulkiller install-timer --enable`
Expected: Writes systemd user units, reloads user daemon, enables and starts timer when systemd user manager is available.

- [ ] **Step 5: Verify status**

Run: `PYTHONPATH=src python -m soulkiller status`
Run: `systemctl --user list-timers soulkiller.timer --no-pager`
Expected: Status reports configured repositories; timer appears when systemd user manager is available.
