import subprocess

from soulkiller.cli import _print_repo_result
from soulkiller.scanner import ScanResult
from soulkiller.sync import RepoSyncResult


def run_cli(*args, env=None):
    command = ["bin/soulkiller", *args]
    return subprocess.run(command, text=True, capture_output=True, env=env)


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


def test_cli_accepts_config_before_subcommand(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / "custom.toml"
    init = run_cli("--config", str(config_path), "init-config")
    assert init.returncode == 0

    status = run_cli("--config", str(config_path), "status")

    assert status.returncode == 0
    assert str(tmp_path / ".codex" / "memories") in status.stdout


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
