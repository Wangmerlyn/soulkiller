from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import default_config_path, load_config, write_default_config
from .restore import (
    list_codex_snapshots,
    restore_codex_snapshot_to_staging,
    restore_dry_run,
    restore_to_staging,
)
from .scheduler import install_cron, install_tmux_loop
from .sync import RepoSyncResult, sync_all
from .timer import install_timer


def _config_path(args: argparse.Namespace) -> Path:
    value = getattr(args, "command_config", None) or getattr(args, "config", None)
    return Path(value).expanduser().resolve() if value else default_config_path().resolve()


def command_init_config(args: argparse.Namespace) -> int:
    path = _config_path(args)
    if path.exists() and not args.force:
        print(f"config exists: {path}")
        return 0
    write_default_config(path)
    print(f"created config: {path}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    config = load_config(_config_path(args))
    print(f"Codex memories: {config.codex_memories.path} enabled={config.codex_memories.enabled} auto_push={config.codex_memories.auto_push}")
    print(f"Codex source branch: {config.codex_memories.source_branch}")
    print(f"Codex snapshots branch: {config.codex_memories.snapshots_branch}")
    print(f"Extra backup: {config.extra_backup.repo_path} enabled={config.extra_backup.enabled} auto_push={config.extra_backup.auto_push}")
    print(f"Extra backup main branch: {config.extra_backup.main_branch}")
    print(f"Codex custom skills source: {config.backup_sources.codex_custom_skills}")
    print(f"Claude projects source: {config.backup_sources.claude_projects}")
    return 0


def _print_repo_result(result: RepoSyncResult) -> None:
    print(f"{result.name}: {result.path}")
    if result.error:
        print(f"  error: {result.error}")
    if result.scan_skipped:
        print("  safety scan: skipped")
    elif not result.scan.ok:
        print("  safety scan failed:")
        for issue in result.scan.issues:
            print(f"    {issue.path}: {issue.message}")
    else:
        print("  safety scan: ok")
    if result.committed:
        print(f"  committed: {result.commit_hash} {result.commit_message}")
    else:
        print(f"  committed: no ({result.commit_message})")
    print(f"  pushed: {'yes' if result.pushed else 'no'} ({result.push_message})")


def command_sync(args: argparse.Namespace) -> int:
    config = load_config(_config_path(args))
    result = sync_all(config)
    _print_repo_result(result.codex)
    _print_repo_result(result.extra)
    return 1 if result.codex.error or result.extra.error else 0


def command_install_timer(args: argparse.Namespace) -> int:
    path = _config_path(args)
    result = install_timer(path, unit_dir=Path(args.unit_dir).expanduser().resolve() if args.unit_dir else None, enable=args.enable)
    print(f"service: {result.service_path}")
    print(f"timer: {result.timer_path}")
    print(f"enabled: {result.enabled}")
    print(result.message)
    return 0 if result.enabled or not args.enable else 1


def command_install_cron(args: argparse.Namespace) -> int:
    result = install_cron(_config_path(args))
    print(result.message)
    return 0 if result.installed else 1


def command_install_tmux_loop(args: argparse.Namespace) -> int:
    result = install_tmux_loop(_config_path(args), session_name=args.session_name)
    print(f"session: {result.session_name}")
    print(result.message)
    return 0 if result.started else 1


def command_restore(args: argparse.Namespace) -> int:
    config = load_config(_config_path(args))
    if args.list_snapshots:
        for snapshot in list_codex_snapshots(config):
            print(snapshot)
        return 0
    if args.dry_run:
        for item in restore_dry_run(config):
            print(item)
        return 0
    if args.staging_dir:
        staging_dir = Path(args.staging_dir).expanduser()
        if args.source == "codex":
            result = restore_codex_snapshot_to_staging(config, args.snapshot, staging_dir)
        else:
            result = restore_to_staging(config, staging_dir)
        print(f"copied {result.copied_files} files to {result.staging_dir}")
        return 0
    print("restore requires --dry-run or --staging-dir", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="soulkiller")
    parser.add_argument("--config", help="Path to config.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-config")
    init_parser.add_argument("--config", dest="command_config", help="Path to config.toml")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=command_init_config)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--config", dest="command_config", help="Path to config.toml")
    status_parser.set_defaults(func=command_status)

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--config", dest="command_config", help="Path to config.toml")
    sync_parser.set_defaults(func=command_sync)

    timer_parser = subparsers.add_parser("install-timer")
    timer_parser.add_argument("--config", dest="command_config", help="Path to config.toml")
    timer_parser.add_argument("--unit-dir", help="Override systemd user unit directory")
    timer_parser.add_argument("--enable", action="store_true")
    timer_parser.set_defaults(func=command_install_timer)

    cron_parser = subparsers.add_parser("install-cron")
    cron_parser.add_argument("--config", dest="command_config", help="Path to config.toml")
    cron_parser.set_defaults(func=command_install_cron)

    tmux_parser = subparsers.add_parser("install-tmux-loop")
    tmux_parser.add_argument("--config", dest="command_config", help="Path to config.toml")
    tmux_parser.add_argument("--session-name", default="soulkiller-backup")
    tmux_parser.set_defaults(func=command_install_tmux_loop)

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--config", dest="command_config", help="Path to config.toml")
    restore_parser.add_argument("--source", choices=["extra", "codex"], default="extra")
    restore_parser.add_argument("--snapshot", default="latest")
    restore_parser.add_argument("--list-snapshots", action="store_true")
    restore_parser.add_argument("--dry-run", action="store_true")
    restore_parser.add_argument("--staging-dir")
    restore_parser.set_defaults(func=command_restore)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
