"""Crash-recovery state files written to the target repo's .claude/ directory."""

import json

from .context import Context


def save_task(task: dict, branch: str, ctx: Context) -> None:
    ctx.task_state_file.parent.mkdir(parents=True, exist_ok=True)
    ctx.task_state_file.write_text(json.dumps({"task": task, "branch": branch}))


def load_task(ctx: Context) -> tuple[dict | None, str | None]:
    if not ctx.task_state_file.exists():
        return None, None
    try:
        data = json.loads(ctx.task_state_file.read_text())
        return data.get("task"), data.get("branch")
    except (json.JSONDecodeError, KeyError):
        return None, None


def clear_task(ctx: Context) -> None:
    if ctx.task_state_file.exists():
        ctx.task_state_file.unlink()


def save_epic(epic: dict, ctx: Context) -> None:
    ctx.epic_breakdown_file.parent.mkdir(parents=True, exist_ok=True)
    ctx.epic_breakdown_file.write_text(json.dumps({"epic": epic}))


def load_epic(ctx: Context) -> dict | None:
    if not ctx.epic_breakdown_file.exists():
        return None
    try:
        data = json.loads(ctx.epic_breakdown_file.read_text())
        return data.get("epic")
    except (json.JSONDecodeError, KeyError):
        return None


def clear_epic(ctx: Context) -> None:
    if ctx.epic_breakdown_file.exists():
        ctx.epic_breakdown_file.unlink()
