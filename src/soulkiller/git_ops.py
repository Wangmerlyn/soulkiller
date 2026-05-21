from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class CommitResult:
    committed: bool
    commit_hash: str | None
    message: str


@dataclass(frozen=True)
class PushResult:
    pushed: bool
    message: str


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        capture_output=True,
    )


def is_git_repo(path: Path) -> bool:
    result = run_git(path, "rev-parse", "--is-inside-work-tree", check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def is_bare_git_repo(path: Path) -> bool:
    result = run_git(path, "rev-parse", "--is-bare-repository", check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if is_git_repo(path):
        return
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, text=True, capture_output=True)


def has_changes(repo: Path) -> bool:
    result = run_git(repo, "status", "--porcelain")
    return bool(result.stdout.strip())


def commit_all_if_changed(repo: Path, message: str) -> CommitResult:
    run_git(repo, "add", "-A")
    diff = run_git(repo, "diff", "--cached", "--quiet", check=False)
    if diff.returncode == 0:
        return CommitResult(committed=False, commit_hash=None, message="no changes")

    run_git(repo, "commit", "-m", message)
    commit_hash = run_git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    return CommitResult(committed=True, commit_hash=commit_hash, message=message)


def branch_exists(repo: Path, branch: str) -> bool:
    result = run_git(
        repo,
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/heads/{branch}",
        check=False,
    )
    return result.returncode == 0


def ref_exists(repo: Path, ref: str) -> bool:
    result = run_git(repo, "show-ref", "--verify", "--quiet", ref, check=False)
    return result.returncode == 0


def update_branch_to_ref(repo: Path, branch: str, ref: str) -> None:
    run_git(repo, "branch", "-f", branch, ref)


def ensure_branch_worktree(repo: Path, branch: str, worktree_path: Path) -> None:
    if path_present(worktree_path):
        registered_branch = registered_worktree_branch(repo, worktree_path)
        path_is_git_repo = is_git_repo(worktree_path)
        path_is_bare_git_repo = is_bare_git_repo(worktree_path)

        if (path_is_git_repo or path_is_bare_git_repo) and registered_branch is None:
            raise ValueError(f"{worktree_path} is a git repo but not a registered worktree of {repo}")

        if registered_branch == branch:
            if not path_is_git_repo:
                raise ValueError(f"{worktree_path} is registered as a worktree but is not a git repo")
            run_git(worktree_path, "reset", "--hard")
            run_git(worktree_path, "clean", "-fd")
            return

        if registered_branch is None:
            remove_path_if_present(worktree_path)
        else:
            remove_worktree(repo, worktree_path)
            if path_present(worktree_path):
                raise RuntimeError(f"failed to remove registered worktree {worktree_path}")

    if branch_exists(repo, branch):
        run_git(repo, "worktree", "add", str(worktree_path), branch)
    elif ref_exists(repo, f"refs/remotes/origin/{branch}"):
        run_git(
            repo,
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree_path),
            f"refs/remotes/origin/{branch}",
        )
    else:
        run_git(repo, "worktree", "add", "-b", branch, str(worktree_path))


def remove_worktree(repo: Path, worktree_path: Path) -> None:
    result = run_git(repo, "worktree", "remove", "--force", str(worktree_path), check=False)
    if result.returncode != 0:
        reason = format_git_error(result)
        raise RuntimeError(f"failed to remove registered worktree {worktree_path}: {reason}")


def remove_path_if_present(path: Path) -> None:
    if not path_present(path):
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def format_git_error(result: subprocess.CompletedProcess[str]) -> str:
    details = [detail for detail in (result.stderr.strip(), result.stdout.strip()) if detail]
    return "\n".join(details) if details else "unknown error"


def registered_worktree_branch(repo: Path, worktree_path: Path) -> str | None:
    target = worktree_path.resolve()
    current_path: Path | None = None
    current_branch = ""
    result = run_git(repo, "worktree", "list", "--porcelain")

    for line in [*result.stdout.splitlines(), ""]:
        if line == "":
            if current_path is not None and current_path.resolve() == target:
                return current_branch
            current_path = None
            current_branch = ""
        elif line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree "))
        elif line.startswith("branch "):
            current_branch = line.removeprefix("branch ").removeprefix("refs/heads/")

    return None


def has_remote(repo: Path) -> bool:
    result = run_git(repo, "remote")
    return bool(result.stdout.strip())


def current_branch(repo: Path) -> str:
    result = run_git(repo, "branch", "--show-current", check=False)
    branch = result.stdout.strip()
    return branch


def push_if_configured(repo: Path, auto_push: bool) -> PushResult:
    if not auto_push:
        return PushResult(pushed=False, message="auto_push disabled")
    if not current_branch(repo):
        return PushResult(pushed=False, message="detached HEAD; push skipped")
    if not has_remote(repo):
        return PushResult(pushed=False, message="no git remote configured; push skipped")

    branch = current_branch(repo)
    upstream = run_git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    if upstream.returncode == 0:
        run_git(repo, "push")
    else:
        run_git(repo, "push", "-u", "origin", branch)
    return PushResult(pushed=True, message="pushed")


def push_branch_if_configured(
    repo: Path,
    branch: str,
    auto_push: bool,
    force_with_lease: bool = False,
) -> PushResult:
    if not auto_push:
        return PushResult(pushed=False, message="auto_push disabled")
    if not has_remote(repo):
        return PushResult(pushed=False, message="no git remote configured; push skipped")

    args = ["push"]
    if force_with_lease:
        args.append("--force-with-lease")
    args.extend(["origin", f"{branch}:{branch}"])
    run_git(repo, *args)
    return PushResult(pushed=True, message=f"pushed {branch}")
