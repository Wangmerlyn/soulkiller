import subprocess

from soulkiller.cli import _print_repo_result, build_parser
from soulkiller.git_ops import commit_all_if_changed, ensure_git_repo, run_git, update_branch_to_ref
from soulkiller.scanner import ScanResult
from soulkiller.sync import RepoSyncResult


def run_cli(*args, env=None):
    command = ["bin/soulkiller", *args]
    return subprocess.run(command, text=True, capture_output=True, env=env)


def configure_identity(path):
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test User"], check=True)


def test_cli_init_config_writes_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    result = run_cli("init-config")

    assert result.returncode == 0
    assert (tmp_path / ".config" / "soulkiller" / "config.toml").exists()
    assert "created" in result.stdout or "exists" in result.stdout


def test_cli_status_reports_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    init = run_cli("init-config")
    assert init.returncode == 0

    status = run_cli("status")

    assert status.returncode == 0
    assert "Codex memories" in status.stdout
    assert "Extra backup" in status.stdout


def test_cli_status_reports_backup_branches(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    init = run_cli("init-config")
    assert init.returncode == 0

    status = run_cli("status")

    assert status.returncode == 0
    assert "Codex source branch: codex/source" in status.stdout
    assert "Codex snapshots branch: codex/snapshots" in status.stdout
    assert "Extra backup main branch: main" in status.stdout


def test_cli_accepts_config_before_subcommand(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / "custom.toml"
    init = run_cli("--config", str(config_path), "init-config")
    assert init.returncode == 0

    status = run_cli("--config", str(config_path), "status")

    assert status.returncode == 0
    assert str(tmp_path / ".codex" / "memories") in status.stdout


def test_restore_parser_accepts_codex_snapshot_source():
    args = build_parser().parse_args(
        ["restore", "--source", "codex", "--snapshot", "latest", "--staging-dir", "/tmp/stage"]
    )

    assert args.source == "codex"
    assert args.snapshot == "latest"
    assert args.staging_dir == "/tmp/stage"


def test_restore_parser_accepts_list_snapshots_for_codex_source():
    args = build_parser().parse_args(["restore", "--list-snapshots", "--source", "codex"])

    assert args.list_snapshots is True
    assert args.source == "codex"


def test_restore_parser_defaults_to_extra_latest_without_list_snapshots():
    args = build_parser().parse_args(["restore", "--dry-run"])

    assert args.source == "extra"
    assert args.snapshot == "latest"
    assert args.list_snapshots is False


def test_cli_restore_codex_dry_run_lists_snapshot_files(tmp_path):
    extra_repo = tmp_path / "extra-repo"
    ensure_git_repo(extra_repo)
    configure_identity(extra_repo)
    (extra_repo / "extra-only.txt").write_text("extra backup\n", encoding="utf-8")
    commit_all_if_changed(extra_repo, "backup: extra")
    run_git(extra_repo, "checkout", "--orphan", "snapshot-seed")
    run_git(extra_repo, "rm", "-rf", ".")
    (extra_repo / "MEMORY.md").write_text("codex memory\n", encoding="utf-8")
    snapshot = commit_all_if_changed(extra_repo, "snapshot: codex memories")
    assert snapshot.commit_hash is not None
    update_branch_to_ref(extra_repo, "codex/snapshots", snapshot.commit_hash)
    run_git(extra_repo, "checkout", "main")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""[codex_memories]
enabled = true
path = "{tmp_path / "codex-memories"}"
auto_push = false
source_branch = "codex/source"
snapshots_branch = "codex/snapshots"

[extra_backup]
enabled = true
repo_path = "{extra_repo}"
auto_push = false
init_if_missing = true
main_branch = "main"

[backup_sources]
codex_custom_skills = "{tmp_path / "codex-skills"}"
claude_projects = "{tmp_path / "claude-projects"}"
""",
        encoding="utf-8",
    )

    result = run_cli("--config", str(config_path), "restore", "--source", "codex", "--dry-run")

    assert result.returncode == 0
    assert "MEMORY.md" in result.stdout
    assert "extra-only.txt" not in result.stdout


def test_print_repo_result_reports_skipped_scan(tmp_path, capsys):
    result = RepoSyncResult(
        name="codex memories",
        path=tmp_path / "memories",
        scan=ScanResult(root=tmp_path / "memories", issues=[]),
        scan_skipped=True,
        committed=False,
        commit_hash=None,
        commit_message="no changes",
        pushed=False,
        push_message="no changes",
    )

    _print_repo_result(result)

    output = capsys.readouterr().out
    assert "safety scan: skipped" in output
