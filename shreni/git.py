"""Git operations against the target repository."""

from .context import Context
from .shell import run_cmd, run_cmd_output


def current_branch(ctx: Context) -> str:
    return run_cmd_output(["git", "branch", "--show-current"], ctx.repo_root)


def branch_exists(branch: str, ctx: Context) -> bool:
    return bool(run_cmd_output(["git", "branch", "--list", branch], ctx.repo_root))


def checkout(branch: str, ctx: Context) -> None:
    run_cmd(["git", "checkout", branch], ctx.repo_root)


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
