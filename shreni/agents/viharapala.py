"""Viharapala — the reviewer agent."""

from ..context import Context
from .runner import load_agent_prompt, run_agent


async def review(task_id: str, branch: str, ctx: Context) -> None:
    """Review an implementation and set the review verdict."""
    await run_agent(
        load_agent_prompt("viharapala", ctx),
        f"Review task {task_id} only. It has been submitted for review on branch '{branch}'.",
        ctx,
        agent_name="viharapala",
    )
