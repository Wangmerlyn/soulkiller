from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shlex
import shutil
import subprocess


BEGIN_MARKER = "# BEGIN SOULKILLER"
END_MARKER = "# END SOULKILLER"
SIX_HOURS_SECONDS = 21600


@dataclass(frozen=True)
class CronInstallResult:
    installed: bool
    message: str


@dataclass(frozen=True)
class TmuxInstallResult:
    started: bool
    session_name: str
    message: str


def default_state_dir() -> Path:
    return Path("~/.local/state/soulkiller").expanduser()


def soulkiller_command() -> str:
    env_command = os.environ.get("SOULKILLER_COMMAND")
    if env_command:
        return env_command
    return shutil.which("soulkiller") or str((Path.cwd() / "bin" / "soulkiller").resolve())


def build_cron_block(config_path: Path, command: str | None = None, state_dir: Path | None = None) -> str:
    state = state_dir or default_state_dir()
    log_path = state / "sync.log"
    soulkiller = command or soulkiller_command()
    sync_command = " ".join(
        [
            shlex.quote(soulkiller),
            "sync",
            "--config",
            shlex.quote(str(config_path)),
            ">>",
            shlex.quote(str(log_path)),
            "2>&1",
        ]
    )
    return f"{BEGIN_MARKER}\n0 */6 * * * {sync_command}\n{END_MARKER}\n"


def _strip_existing_block(crontab_text: str) -> str:
    lines = crontab_text.splitlines()
    output: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == BEGIN_MARKER:
            skipping = True
            continue
        if line.strip() == END_MARKER:
            skipping = False
            continue
        if not skipping:
            output.append(line)
    return "\n".join(output).rstrip()


def install_cron(
    config_path: Path,
    command: str | None = None,
    state_dir: Path | None = None,
    runner=subprocess.run,
) -> CronInstallResult:
    if shutil.which("crontab") is None and runner is subprocess.run:
        return CronInstallResult(False, "crontab command not found")

    state = state_dir or default_state_dir()
    state.mkdir(parents=True, exist_ok=True)
    current = runner(["crontab", "-l"], text=True, capture_output=True)
    existing = current.stdout if current.returncode == 0 else ""
    stripped = _strip_existing_block(existing)
    block = build_cron_block(config_path=config_path, command=command, state_dir=state)
    new_crontab = f"{stripped}\n{block}" if stripped else block
    if not new_crontab.endswith("\n"):
        new_crontab += "\n"

    installed = runner(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    if installed.returncode != 0:
        return CronInstallResult(False, installed.stderr.strip() or installed.stdout.strip())
    return CronInstallResult(True, "cron entry installed")


def build_tmux_command(config_path: Path, soulkiller_command: str | None = None, state_dir: Path | None = None) -> str:
    state = state_dir or default_state_dir()
    command = soulkiller_command or globals()["soulkiller_command"]()
    log_path = state / "sync.log"
    return (
        "while :; do "
        f"{shlex.quote(command)} sync --config {shlex.quote(str(config_path))} "
        f">> {shlex.quote(str(log_path))} 2>&1; "
        f"sleep {SIX_HOURS_SECONDS}; "
        "done"
    )


def install_tmux_loop(
    config_path: Path,
    session_name: str = "soulkiller-backup",
    command: str | None = None,
    state_dir: Path | None = None,
    runner=subprocess.run,
) -> TmuxInstallResult:
    if shutil.which("tmux") is None and runner is subprocess.run:
        return TmuxInstallResult(False, session_name, "tmux command not found")

    state = state_dir or default_state_dir()
    state.mkdir(parents=True, exist_ok=True)
    has_session = runner(["tmux", "has-session", "-t", session_name], text=True, capture_output=True)
    if has_session.returncode == 0:
        return TmuxInstallResult(False, session_name, "tmux session already exists; inspect or kill it before installing")

    loop_command = build_tmux_command(config_path=config_path, soulkiller_command=command, state_dir=state)
    started = runner(["tmux", "new-session", "-d", "-s", session_name, loop_command], text=True, capture_output=True)
    if started.returncode != 0:
        return TmuxInstallResult(False, session_name, started.stderr.strip() or started.stdout.strip())
    return TmuxInstallResult(True, session_name, "tmux loop started")
