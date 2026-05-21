import subprocess

from soulkiller.scheduler import build_cron_block, build_tmux_command, install_cron


def test_build_cron_block_uses_six_hour_schedule(tmp_path):
    config_path = tmp_path / "config.toml"
    command = tmp_path / "bin" / "soulkiller"
    state_dir = tmp_path / "state"

    block = build_cron_block(config_path=config_path, command=str(command), state_dir=state_dir)

    assert "# BEGIN SOULKILLER" in block
    assert f"0 */6 * * * {command} sync --config {config_path}" in block
    assert f">> {state_dir / 'sync.log'} 2>&1" in block
    assert "# END SOULKILLER" in block


def test_install_cron_replaces_existing_block(tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["crontab", "-l"]:
            return subprocess.CompletedProcess(args, 0, stdout="MAILTO=''\n# BEGIN SOULKILLER\nold\n# END SOULKILLER\n", stderr="")
        if args == ["crontab", "-"]:
            assert kwargs["input"].count("# BEGIN SOULKILLER") == 1
            assert "old" not in kwargs["input"]
            assert "MAILTO=''" in kwargs["input"]
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        raise AssertionError(args)

    result = install_cron(config_path=tmp_path / "config.toml", command="/bin/soulkiller", state_dir=tmp_path, runner=fake_run)

    assert result.installed is True
    assert calls == [["crontab", "-l"], ["crontab", "-"]]


def test_build_tmux_command_runs_loop_script(tmp_path):
    command = build_tmux_command(
        config_path=tmp_path / "config.toml",
        soulkiller_command="/bin/soulkiller",
        state_dir=tmp_path / "state",
    )

    assert "while :" in command
    assert "/bin/soulkiller sync --config" in command
    assert "sleep 21600" in command
