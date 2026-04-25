"""The core implement → review → (address → review)* → merge loop for a single task.

Workflow
--------
  silpi_implement  ──►  viharapala_review  ──►  merge  ──►  returns task dict
                              │
                     changes-required
                              │
                              ▼
                       silpi_address  ──►  viharapala_review  (repeats)

Returns the merged task dict on success, or None when pausing for author sign-off.
The caller (sthapathi) enqueues the result for Parikshaka.
"""

import json

from ..agents import silpi, viharapala
from ..bd import close_task, get_comments, review_state, set_state, show_task
from ..context import Context
from ..git import (
    branch_exists,
    branch_has_commits,
    checkout,
    create_branch,
    delete_branch,
    merge_squash_and_commit,
    pull,
    push,
    task_merged_to_main,
)
from ..shell import log, make_logger
from ..state import clear_task

_silpi = make_logger("Silpi")
_viharapala = make_logger("Viharapala")


async def run_task_loop(
    task: dict,
    branch: str,
    start_round: int,
    start_state: str,
    ctx: Context,
) -> dict | None:
    """Drive a single task through the full implement → review → merge lifecycle.

    Returns the task dict when merged successfully, or None when pausing for
    author sign-off (viharapala-approved on an epic).
    """
    task_id = task["id"]
    round_num = start_round
    state = start_state

    while True:
        task_context = show_task(task_id, ctx) or json.dumps(task)

        # ── Silpi: implement or address feedback ──────────────────────────────
        if state == "silpi_implement":
            _silpi(f"[Round {round_num}] implement {task_id}")
            await silpi.implement(task_id, task_context, branch, ctx)
            _ensure_review_submitted(task_id, ctx)
            state = "viharapala_review"

        elif state == "silpi_address":
            review_comments = get_comments(task_id, ctx) or "See bd comments."
            _silpi(f"[Round {round_num}] address feedback on {task_id}")
            await silpi.address_feedback(
                task_id, task_context, branch, round_num, review_comments, ctx
            )
            _ensure_review_submitted(task_id, ctx)
            state = "viharapala_review"

        # ── Viharapala: review ────────────────────────────────────────────────
        if state == "viharapala_review":
            _viharapala(f"[Round {round_num}] review {task_id}")
            await viharapala.review(task_id, branch, ctx)

            verdict = review_state(task_id, ctx)
            if verdict == "approved":
                _viharapala(f"{task_id} approved after {round_num} round(s).")
                state = "merge"
            elif verdict == "changes-required":
                _viharapala(f"{task_id} needs changes — handing back to Silpi (round {round_num + 1}).")
                round_num += 1
                state = "silpi_address"
                continue
            elif verdict == "viharapala-approved":
                _viharapala(f"{task_id} approved — awaiting author sign-off.")
                return None
            else:
                _viharapala(f"No verdict set ('{verdict or 'none'}') — re-running review.")
                continue

        # ── Merge ─────────────────────────────────────────────────────────────
        if state == "merge":
            if not branch_has_commits(branch, ctx):
                if task_merged_to_main(task_id, ctx):
                    # Merge landed in main but bd close failed previously.
                    # Close it now and exit cleanly rather than re-implementing.
                    log(f"Task {task_id} already merged to main — closing.")
                    close_task(task_id, "Approved and merged to main", ctx)
                    clear_task(ctx)
                    return task

                # Branch is empty or missing — Silpi never committed anything.
                # Re-route to implement rather than ghost-merging.
                log(f"Branch {branch} has no commits ahead of main — Silpi did not commit. Re-implementing.")
                if branch_exists(branch, ctx):
                    checkout(branch, ctx)
                else:
                    checkout("main", ctx)
                    pull(ctx)
                    create_branch(branch, ctx)
                state = "silpi_implement"
                continue

            log(f"Merging {branch} → main...")
            checkout("main", ctx)
            pull(ctx)
            merge_squash_and_commit(branch, task_id, ctx)
            push(ctx)
            delete_branch(branch, ctx)
            log("Merged and pushed.")

            close_task(task_id, "Approved and merged to main", ctx)
            clear_task(ctx)
            log(f"Task {task_id} complete.")
            return task


def _ensure_review_submitted(task_id: str, ctx: Context) -> None:
    """Guard: if Silpi forgot to submit for review, do it now."""
    state = review_state(task_id, ctx)
    if state not in ("ready-for-review", "approved", "changes-required"):
        log("Silpi did not submit for review — submitting now...")
        set_state(task_id, "review=ready-for-review", "Implementation complete", ctx)
