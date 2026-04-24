"""Parikshaka — QA agent, invoked after each task merge."""

from ..context import Context
from .runner import load_agent_prompt, run_agent


async def quality_check(task_id: str, task_title: str, ctx: Context) -> None:
    """Run e2e quality check after a task has been merged to main."""
    await run_agent(
        load_agent_prompt("parikshaka", ctx),
        (
            f"Task {task_id} ('{task_title}') has been completed and merged to main.\n\n"
            f"Quality check the project:\n"
            f"1. Discover and run the e2e test suite.\n"
            f"2. If any tests fail, create bd bug tasks for each new regression"
            f" (skip failures that already have an open bug).\n"
            f"3. If all tests pass, review the completed task and write new e2e tests"
            f" for any user-facing functionality not yet covered.\n"
            f"4. Commit any new test files: {task_id}: Add e2e tests for <feature>"
        ),
        ctx,
    )
