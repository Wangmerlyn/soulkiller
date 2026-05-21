# Soulkiller Memory Backup Design

## Purpose

Soulkiller is a shareable tool for backing up long-term coding-agent memory without storing any private memory in the tool repository. It supports the user's current Codex and Claude layout while remaining configurable for other machines.

## Repository Boundaries

Soulkiller uses three separate repositories:

- `soulkiller`: public or shareable tool repository with CLI code, timer templates, configuration examples, tests, and docs.
- Codex memory repository: the existing `~/.codex/memories` git repository. Soulkiller commits and pushes this repository in place.
- Extra memory backup repository: a private user-managed repository for long-term memory artifacts that are not already in the Codex memory repository.

Soulkiller must not add private memory data, access tokens, local auth files, session logs, or machine-local settings to its own repository.

## Backup Scope

The default scope is "long-term memory ecosystem":

- Codex memories: all tracked and untracked working-tree content under `~/.codex/memories`, managed by that repository's own git metadata.
- Claude project memory: `~/.claude/projects/*/memory`.
- Custom Codex skills: non-system directories under `~/.codex/skills`, excluding `.system`.

The default scope excludes session history and runtime state:

- Codex sessions, logs, sqlite files, caches, auth files, env files, local hooks, and model caches.
- Claude sessions, transcripts, debug/cache/telemetry directories, session env, local settings, downloads, paste cache, and file history.
- Any path or content matching high-risk secret patterns.

## Data Layout

The extra backup repository uses a portable categorized layout:

```text
codex/skills/<skill-name>/
claude/project-memories/<project-id>/memory/
manifests/snapshot.json
```

Project IDs are derived from Claude's existing project directory names. The snapshot manifest records source paths, destination paths, sync timestamp, copied item counts, and skipped paths.

## Sync Behavior

`soulkiller sync` performs two independent syncs:

1. Codex memory sync:
   - Verify the configured path exists and is a git repository.
   - Run a safety scan on the working tree.
   - Stage all changes, create a timestamped backup commit if there are changes, and push if `auto_push` is enabled and a remote exists.
   - If no remote exists, keep the local commit and report that push was skipped.

2. Extra backup sync:
   - Verify or initialize the configured extra backup repository.
   - Mirror allowed custom skills and Claude project memory into the categorized layout.
   - Remove stale mirrored files that no longer exist in the source.
   - Write `manifests/snapshot.json`.
   - Run a safety scan on the repository working tree.
   - Commit and optionally push if a remote exists.

No-op syncs should exit successfully and report that no changes were found.

## Configuration

The default config path is:

```text
~/.config/soulkiller/config.toml
```

Default values:

```toml
[codex_memories]
enabled = true
path = "~/.codex/memories"
auto_push = true

[extra_backup]
enabled = true
repo_path = "~/.local/share/soulkiller/extra-memory-backup"
auto_push = true
init_if_missing = true

[backup_sources]
codex_custom_skills = "~/.codex/skills"
claude_projects = "~/.claude/projects"
```

The CLI can create this config with `soulkiller init-config`.

## Timer Behavior

The primary scheduler is a systemd user timer. `soulkiller install-timer` writes:

- `~/.config/systemd/user/soulkiller.service`
- `~/.config/systemd/user/soulkiller.timer`

The timer runs `soulkiller sync` every six hours and uses `Persistent=true` so a missed run is attempted after login. Cron instructions are documentation-only fallback.

## Safety Model

Soulkiller is fail-closed for obvious secrets:

- High-risk filenames such as `auth.json`, `.env`, `*.sqlite`, `*.db`, `settings.local.json`, and files containing `token`, `secret`, `credential`, or `webhook` in sensitive contexts are rejected.
- Text files are scanned for common secret assignments and webhook URLs.
- Binary and oversized files are rejected by default.

Safety scan failures abort commit and push.

## Restore Model

The first version provides conservative restore support only:

- `soulkiller restore --dry-run` reports what would be restored.
- `soulkiller restore --staging-dir <path>` copies backup data into a staging directory.

Soulkiller does not overwrite live `~/.codex` or `~/.claude` paths in the first version.

## CLI Surface

```text
soulkiller init-config
soulkiller status
soulkiller sync
soulkiller install-timer
soulkiller restore --dry-run
soulkiller restore --staging-dir <path>
```

The CLI is implemented with Python standard library modules so the tool remains easy to install and inspect.
