"""Parikshaka — QA agent, invoked after each task merge."""

from ..context import Context
from .runner import load_agent_prompt, run_agent


async def quality_check(task_id: str, task_title: str, ctx: Context) -> None:
    """Triage quality after a task has been merged to main.

    Parikshaka does not write code. It creates:
      - bug tasks (label=parikshaka) for e2e regressions
      - feature tasks (label=e2e) for missing e2e coverage
    Both are picked up by Sthapathi and implemented by Silpi.
    """
    await run_agent(
        load_agent_prompt("parikshaka", ctx),
        (
            f"Task {task_id} ('{task_title}') has been completed and merged to main.\n\n"

            f"Triage the project quality:\n"
            f"1. Discover and run the existing e2e suite. For each failing test, create a"
            f" bug task (--labels parikshaka) unless an open bug already exists for it.\n"
            f"2. Review the completed task and its diff. If it introduced user-visible"
            f" behaviour not covered by an existing e2e test, create a coverage task"
            f" (--type feature --labels e2e) with a detailed description of the user"
            f" journey and acceptance criteria for Silpi to implement.\n"
            f"Do not write any code or test files."
        ),
        ctx,
        agent_name="parikshaka",
    )
