"""Git operations against the target repository."""

from .context import Context
from .shell import run_cmd, run_cmd_output


def current_branch(ctx: Context) -> str:
    return run_cmd_output(["git", "branch", "--show-current"], ctx.repo_root)


def branch_exists(branch: str, ctx: Context) -> bool:
    return bool(run_cmd_output(["git", "branch", "--list", branch], ctx.repo_root))


def checkout(branch: str, ctx: Context) -> None:
    run_cmd(["git", "checkout", branch], ctx.repo_root)


def has_uncommitted_changes(ctx: Context) -> bool:
    """True if the working tree has any modified or untracked files."""
    out = run_cmd_output(["git", "status", "--porcelain"], ctx.repo_root)
    return bool(out.strip())


def stash_save(message: str, ctx: Context) -> bool:
    """Stash modified + untracked files. Returns True if a stash was created.

    Used to keep orchestrator-side artefacts (bd backup logs, generated test
    fixtures) from blocking `git checkout` between tasks. Pop with stash_pop.
    """
    if not has_uncommitted_changes(ctx):
        return False
    run_cmd(["git", "stash", "push", "-u", "-m", message], ctx.repo_root)
    return True


def stash_pop(ctx: Context) -> None:
    """Restore the most recent stash. Caller handles failures (conflicts)."""
    run_cmd(["git", "stash", "pop"], ctx.repo_root)


def pull(ctx: Context) -> None:
    run_cmd(["git", "pull"], ctx.repo_root)


def create_branch(branch: str, ctx: Context) -> None:
    run_cmd(["git", "checkout", "-b", branch], ctx.repo_root)


def merge_squash_and_commit(branch: str, task_id: str, ctx: Context) -> None:
    run_cmd(["git", "merge", "--squash", branch], ctx.repo_root)
    run_cmd(["git", "commit", "-m", f"{task_id}: Merge {branch}"], ctx.repo_root)


def push(ctx: Context) -> None:
    run_cmd(["git", "push"], ctx.repo_root)


def delete_branch(branch: str, ctx: Context) -> None:
    run_cmd(["git", "branch", "-D", branch], ctx.repo_root)


def log_range(from_ref: str, to_ref: str, ctx: Context) -> str:
    return run_cmd_output(
        ["git", "log", f"{from_ref}..{to_ref}", "--oneline"], ctx.repo_root
    )


def branch_has_commits(branch: str, ctx: Context) -> bool:
    """Return True if branch exists and has at least one commit ahead of main."""
    if not branch_exists(branch, ctx):
        return False
    return bool(log_range("main", branch, ctx))


def task_merged_to_main(task_id: str, ctx: Context) -> bool:
    """Return True if a merge commit for task_id already exists on main.

    Merge commits are written as "<task_id>: Merge feature/..." so grepping
    the task_id is sufficient to detect a completed merge.
    """
    out = run_cmd_output(
        ["git", "log", "main", "--oneline", "--grep", task_id],
        ctx.repo_root,
    )
    return bool(out.strip())
