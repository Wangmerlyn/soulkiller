# Soulkiller Memory Backup Design

## Purpose

Soulkiller is a shareable Python CLI for backing up long-term coding-agent
memory without storing private memory in the public tool repository. It backs up
the user's Codex and Claude memory stores while keeping Codex-owned state
separate from Soulkiller-owned snapshot history.

## Repository Boundaries

Soulkiller uses three logical repositories:

- `soulkiller`: the public or shareable tool repository. It contains CLI code,
  tests, docs, and scheduler templates only.
- Codex memories source repository: the existing `~/.codex/memories` git
  repository. Soulkiller treats this repository as read-only source state and
  does not create commits, branches, or tags in it.
- Private backup repository: the configured `extra_backup.repo_path`. Soulkiller
  uses this repo for generated extra backups and Codex memory backup branches.

Soulkiller must not add private memory data, access tokens, local auth files,
session logs, backup snapshots, or machine-local settings to its own repository.

## Backup Scope

The default scope is the long-term memory ecosystem:

- Codex memories: the source commit graph of `~/.codex/memories` plus snapshots
  of its working-tree content, excluding `.git`.
- Claude project memory: `~/.claude/projects/*/memory`.
- Custom Codex skills: non-system directories under `~/.codex/skills`, excluding
  `.system`.

The default scope excludes session history and runtime state outside these
explicit inputs, including logs, sqlite files, caches, auth files, env files,
local hooks, transcripts, downloads, paste cache, and model caches.

## Data Layout

The private backup repository is a multi-branch repo:

- `main`: generated extra backup layout.
- `codex/source`: mirror of the Codex memories source repository's current
  committed HEAD and original commit graph.
- `codex/snapshots`: append-only Soulkiller snapshot history for the Codex
  memories working tree.

The `main` branch keeps the existing generated layout:

```text
codex/skills/<skill-name>/
claude/project-memories/<project-id>/memory/
manifests/snapshot.json
```

The `codex/snapshots` branch root mirrors the Codex memories root directly. It
does not wrap files under `codex/memories/`, because restore should be able to
stage a tree that looks like the original memory directory.

Snapshot metadata lives in the commit message, not in files inside the snapshot
tree, so the tree shape stays faithful to the source. Each snapshot commit uses
trailers like:

```text
Source-Path: ~/.codex/memories
Source-Head: <sha>
Source-Branch: <branch-or-detached>
Source-Dirty: true|false
Snapshot-Time: <utc>
```

## Sync Behavior

`soulkiller sync` performs two independent syncs under one process lock.

Codex memory backup:

- Verify the configured Codex memories path exists and is a git repository.
- Read the source branch, HEAD, and dirty state without checking out branches or
  mutating source refs.
- Force-update the private backup repo's `codex/source` branch to the source
  repository HEAD. This preserves the original Codex repository shape as
  committed by Codex.
- Copy the Codex memories working tree, excluding `.git`, into a temporary
  checkout of the private backup repo's `codex/snapshots` branch.
- Create a snapshot commit only when the copied tree differs from the current
  `codex/snapshots` tree. Scheduled runs with no content changes must be
  no-ops, not empty commits.
- Push `codex/source` and `codex/snapshots` explicitly when
  `codex_memories.auto_push` is enabled and the private backup repo has a
  remote. `codex/source` may require force-with-lease semantics; `codex/snapshots`
  must not be force-pushed.

Extra backup sync:

- Verify or initialize the private backup repository.
- Mirror allowed custom skills and Claude project memory into the `main` branch
  categorized layout.
- Remove stale mirrored files that no longer exist in source inputs.
- Write `manifests/snapshot.json`.
- Run the safety scan on the generated extra backup tree.
- Commit only when the generated tree changes, then push the `main` branch when
  `extra_backup.auto_push` is enabled and a remote exists.

No-op syncs exit successfully and report that no changes were found.

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
source_branch = "codex/source"
snapshots_branch = "codex/snapshots"

[extra_backup]
enabled = true
repo_path = "~/.local/share/soulkiller/extra-memory-backup"
auto_push = true
init_if_missing = true
main_branch = "main"

[backup_sources]
codex_custom_skills = "~/.codex/skills"
claude_projects = "~/.claude/projects"
```

`extra_backup.repo_path` must resolve outside the Soulkiller source repository.
Soulkiller should fail before writing private data if a configured backup target
would live inside the public tool checkout.

## Timer Behavior

The primary scheduler remains a systemd user timer. Existing cron and tmux
fallbacks also continue to call:

```text
soulkiller sync --config <path>
```

Because snapshot creation is part of `sync`, scheduler behavior does not need a
new command. Every scheduled run checks for changes, but unchanged Codex memory
trees do not produce empty snapshot commits.

## Safety Model

Codex memories are treated as Codex-owned private state and are not safety
scanned before backup. Scanning arbitrary memory could block valid private notes
and would not make a private remote public-safe. The safety requirement is
instead containment: Codex memory branches must only be written to the configured
private backup repo.

The generated extra backup on `main` remains fail-closed for obvious secrets,
auth files, logs, binary data, cache directories, session data, and oversized
files. Safety scan failures abort the extra backup commit and push.

## Restore Model

Restore stays conservative and stages data for manual inspection. It should be
ref-aware:

- `restore --source extra --staging-dir <path>` stages the checked or selected
  extra backup tree from `main`.
- `restore --source codex --snapshot latest --staging-dir <path>` stages the
  latest `codex/snapshots` tree.
- `restore --source codex --snapshot <commit-or-ref> --staging-dir <path>`
  stages a specific Codex snapshot.
- `restore --list-snapshots --source codex` lists available snapshot commits.

Soulkiller does not overwrite live `~/.codex` or `~/.claude` paths by default.
Any future live restore path must require an explicit opt-in, a clean target
check, and a pre-restore backup.

## CLI Surface

```text
soulkiller init-config
soulkiller status
soulkiller sync
soulkiller install-timer
soulkiller install-cron
soulkiller install-tmux-loop
soulkiller restore --dry-run
soulkiller restore --list-snapshots --source codex
soulkiller restore --source codex --snapshot latest --staging-dir <path>
soulkiller restore --source extra --staging-dir <path>
```

`status` should show the Codex source path, private backup repo path, configured
branch names, enabled flags, and auto-push settings. `sync` output should report
the `codex/source`, `codex/snapshots`, and `main` branch results separately.
