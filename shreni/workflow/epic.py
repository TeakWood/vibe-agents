"""Epic breakdown workflow: Silpi decomposes an approved epic into feature tasks."""

import json

from ..bd import breakdown_state, get_comments, show_task
from ..context import Context
from ..shell import log
from ..state import clear_epic, save_epic
from ..agents import silpi


async def run_epic_breakdown(epic: dict, ctx: Context) -> None:
    """Invoke Silpi to decompose an approved epic into feature tasks."""
    epic_id = epic["id"]
    log(f"Breaking down epic {epic_id}: {epic['title']}")
    save_epic(epic, ctx)

    epic_context = show_task(epic_id, ctx) or json.dumps(epic)
    epic_comments = get_comments(epic_id, ctx) or "No comments yet."

    await silpi.breakdown_epic(epic_id, epic_context, epic_comments, ctx)

    if breakdown_state(epic_id, ctx) == "complete":
        clear_epic(ctx)
        log(f"Epic {epic_id} breakdown complete.")
    else:
        log(f"Warning: epic {epic_id} breakdown incomplete — will retry on next run.")
