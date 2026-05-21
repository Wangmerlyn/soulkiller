# Soulkiller

Soulkiller is a shareable Python CLI for backing up long-term coding-agent
memory. This repository is the public tool source only. It should never contain
real private memory, transcripts, secrets, project notes, or backup snapshots.

Soulkiller works with the memory stores where they already live:

- `~/.codex/memories` is expected to already be a git repository. Soulkiller
  commits and pushes that repository in place.
- A separate private backup repository stores memory that should not live in
  the public tool repo, including Claude project memory and custom Codex skills.

## What It Backs Up

Soulkiller keeps two backup paths separate.

### Codex Memory

Codex long-term memory stays in:

```text
~/.codex/memories
```

Soulkiller runs git status, commit, and push inside that repository. It does not
copy this data into the Soulkiller source tree.

### Private Backup Repository

Claude project memory and custom Codex skills are copied into a private backup
repository with this layout:

```text
codex/
  skills/
    <skill>/
claude/
  project-memories/
    <project-id>/
      memory/
manifests/
  snapshot.json
```

Use a private remote for this repository.

## Configuration

Soulkiller reads configuration from:

```text
~/.config/soulkiller/config.toml
```

Create a starter config with:

```sh
./bin/soulkiller init-config
```

The config should point to the local private backup repository, the Codex memory
repository, and any Claude project memory locations you want included.

## Commands

```sh
./bin/soulkiller init-config
```

Create `~/.config/soulkiller/config.toml` with editable defaults.

```sh
./bin/soulkiller status
```

Show configured paths and whether each backup target is enabled.

```sh
./bin/soulkiller sync
```

Scan configured inputs, update the private backup repository, commit changes,
and push configured remotes. Codex memory is committed and pushed in
`~/.codex/memories`.

```sh
./bin/soulkiller install-timer
```

Install a systemd user timer for scheduled syncs.

```sh
./bin/soulkiller restore --dry-run
```

Preview what would be restored without writing files.

```sh
./bin/soulkiller restore --staging-dir <path>
```

Restore into a staging directory for manual inspection. Soulkiller should not
overwrite live memory directly during a restore.

## Scheduling

The primary supported scheduler is a systemd user timer:

```sh
./bin/soulkiller install-timer --enable
systemctl --user list-timers soulkiller*
```

On machines where the systemd user manager is not persistent after logout, also
enable user lingering from an admin shell if you need the timer to survive
reboots before login:

```sh
loginctl enable-linger "$USER"
```

If systemd user services are unavailable, use cron as the preferred fallback:

```cron
0 */6 * * * /path/to/soulkiller/bin/soulkiller sync
```

Soulkiller can install or replace its managed cron block when `crontab` is
available:

```sh
./bin/soulkiller install-cron
```

If neither systemd nor cron is available, use the tmux fallback:

```sh
./bin/soulkiller install-tmux-loop
tmux attach -t soulkiller-backup
```

If a `soulkiller-backup` tmux session already exists, Soulkiller refuses to
overwrite it. Inspect it or stop it first with `tmux kill-session -t
soulkiller-backup`.

## Safety Scan

Soulkiller blocks files and paths that look unsafe to back up. The scanner is
designed to stop common private or noisy data from entering the private backup
repository.

Blocked patterns include:

- secrets and credentials
- auth tokens and key material
- `.env` files
- SQLite databases
- logs
- session and transcript data
- cache directories

If `status` or `sync` reports a blocked path, remove it from the configured
inputs or add a narrower include path.

## Restore Workflow

Always restore to a staging directory first:

```sh
./bin/soulkiller restore --staging-dir /tmp/soulkiller-restore
```

Inspect the staged files, then manually copy back only the memory or skill data
you intend to keep. This keeps accidental overwrites out of live Codex and
Claude state.

## Repository Rule

Keep this repository public-safe. Real memory belongs in `~/.codex/memories` or
the configured private backup repository, never in the Soulkiller source repo.
