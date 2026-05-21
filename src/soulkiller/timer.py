from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class TimerInstallResult:
    service_path: Path
    timer_path: Path
    enabled: bool
    message: str


def default_unit_dir() -> Path:
    return Path("~/.config/systemd/user").expanduser()


def _soulkiller_command() -> str:
    return shutil.which("soulkiller") or "soulkiller"


def build_service_unit(config_path: Path) -> str:
    command = _soulkiller_command()
    return f"""[Unit]
Description=Soulkiller long-term memory backup

[Service]
Type=oneshot
ExecStart={command} sync --config {config_path}
"""


def build_timer_unit() -> str:
    return """[Unit]
Description=Run Soulkiller memory backup periodically

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
"""


def install_timer(config_path: Path, unit_dir: Path | None = None, enable: bool = False) -> TimerInstallResult:
    target_dir = unit_dir or default_unit_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    service_path = target_dir / "soulkiller.service"
    timer_path = target_dir / "soulkiller.timer"
    service_path.write_text(build_service_unit(config_path), encoding="utf-8")
    timer_path.write_text(build_timer_unit(), encoding="utf-8")

    if not enable:
        return TimerInstallResult(service_path, timer_path, enabled=False, message="timer files written")

    daemon = subprocess.run(["systemctl", "--user", "daemon-reload"], text=True, capture_output=True)
    if daemon.returncode != 0:
        return TimerInstallResult(service_path, timer_path, enabled=False, message=daemon.stderr.strip() or daemon.stdout.strip())
    enable_result = subprocess.run(["systemctl", "--user", "enable", "--now", "soulkiller.timer"], text=True, capture_output=True)
    if enable_result.returncode != 0:
        return TimerInstallResult(
            service_path,
            timer_path,
            enabled=False,
            message=enable_result.stderr.strip() or enable_result.stdout.strip(),
        )
    return TimerInstallResult(service_path, timer_path, enabled=True, message="timer enabled")

