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
from ..bd import close_task, get_comments, review_state, set_state, show_task, task_status
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
    stash_pop,
    stash_save,
    task_merged_to_main,
)
from ..observability import emit_event, span
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

    with span(
        ctx,
        "task",
        task_id=task_id,
        attrs={
            "title": task.get("title", ""),
            "branch": branch,
            "start_state": start_state,
            "start_round": start_round,
            "issue_type": task.get("issue_type"),
        },
    ):
        return await _drive_task(task, branch, round_num, state, ctx)


async def _drive_task(
    task: dict,
    branch: str,
    round_num: int,
    state: str,
    ctx: Context,
) -> dict | None:
    task_id = task["id"]

    while True:
        task_context = show_task(task_id, ctx) or json.dumps(task)

        # Resume-safety: if the task was already marked blocked before we got
        # here (e.g. a previous run hit the dependency wall), skip the agents
        # entirely and release back to the main loop.
        if _release_if_blocked(task_id, ctx):
            return None

        # ── Silpi: implement or address feedback ──────────────────────────────
        if state == "silpi_implement":
            _silpi(f"[Round {round_num}] implement {task_id}")
            await silpi.implement(task_id, task_context, branch, ctx)
            if _release_if_blocked(task_id, ctx):
                return None
            _ensure_review_submitted(task_id, ctx)
            state = "viharapala_review"

        elif state == "silpi_address":
            review_comments = get_comments(task_id, ctx) or "See bd comments."
            _silpi(f"[Round {round_num}] address feedback on {task_id}")
            await silpi.address_feedback(
                task_id, task_context, branch, round_num, review_comments, ctx
            )
            if _release_if_blocked(task_id, ctx):
                return None
            _ensure_review_submitted(task_id, ctx)
            state = "viharapala_review"

        # ── Viharapala: review ────────────────────────────────────────────────
        if state == "viharapala_review":
            _viharapala(f"[Round {round_num}] review {task_id}")
            await viharapala.review(task_id, branch, ctx)

            verdict = review_state(task_id, ctx)
            emit_event(
                ctx,
                "review_verdict",
                agent="viharapala",
                task_id=task_id,
                attrs={"verdict": verdict or "none", "round": round_num},
            )
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
                clear_task(ctx)
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
                # Re-route to implement rather than ghost-merging. Reset the
                # review dimension so the next viharapala_review verdict is a
                # fresh read, not a stale 'approved' carry-over that would loop
                # us straight back to merge with the same empty branch.
                log(f"Branch {branch} has no commits ahead of main — Silpi did not commit. Re-implementing.")
                set_state(task_id, "review=ready-for-review", "Re-implementing: empty branch", ctx)
                if branch_exists(branch, ctx):
                    checkout(branch, ctx)
                else:
                    checkout("main", ctx)
                    pull(ctx)
                    create_branch(branch, ctx)
                state = "silpi_implement"
                continue

            log(f"Merging {branch} → main...")
            # bd writes to .claude/bd-backup.log during agent runs; without
                # stashing, `git checkout main` aborts because of those dirty
                # files. Pop after the merge lands so any user-side dirty work
                # survives.
            stashed = stash_save(f"shreni: pre-merge {task_id}", ctx)
            checkout("main", ctx)
            pull(ctx)
            merge_squash_and_commit(branch, task_id, ctx)
            push(ctx)
            delete_branch(branch, ctx)
            if stashed:
                try:
                    stash_pop(ctx)
                except Exception as e:
                    log(f"Warning: could not restore pre-merge stash automatically ({e}). Run `git stash pop` to recover.")
            log("Merged and pushed.")

            close_task(task_id, "Approved and merged to main", ctx)
            clear_task(ctx)
            emit_event(
                ctx,
                "task_merged",
                task_id=task_id,
                attrs={"branch": branch, "rounds": round_num},
            )
            log(f"Task {task_id} complete.")
            return task


def _ensure_review_submitted(task_id: str, ctx: Context) -> None:
    """Guard: if Silpi forgot to submit for review, do it now.

    A stale 'approved' state must be reset — otherwise the loop sees
    verdict==approved on a freshly-implemented branch and skips Viharapala's
    real review, which can trap the orchestrator if the branch is empty.
    """
    state = review_state(task_id, ctx)
    if state not in ("ready-for-review", "changes-required"):
        log(f"Silpi did not submit for review (state='{state or 'none'}') — submitting now...")
        set_state(task_id, "review=ready-for-review", "Implementation complete", ctx)


def _release_if_blocked(task_id: str, ctx: Context) -> bool:
    """If Silpi marked the task blocked, release it back to the main loop.

    Without this, a task whose dependencies are still open would cycle forever:
    Silpi can't implement → empty branch → Viharapala says changes-required →
    Silpi runs again, ad infinitum. Returning to the main loop lets the
    orchestrator pick up other ready tasks; this one will be re-claimed once
    its dependencies merge.
    """
    if task_status(task_id, ctx) == "blocked":
        log(f"Task {task_id} marked blocked by Silpi — releasing to main loop.")
        clear_task(ctx)
        return True
    return False
