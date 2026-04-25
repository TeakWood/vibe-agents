"""Crash-recovery helpers: find an interrupted task and determine where to resume."""

from ..bd import query_tasks, review_state, tasks_with_label
from ..context import Context
from ..git import branch_has_commits, current_branch as get_current_branch, log_range, task_merged_to_main
from ..shell import log, slugify
from ..state import load_task


def classify_resume_state(rev_state: str) -> str:
    """Map a bd review dimension value to the next orchestrator action."""
    if rev_state == "ready-for-review":
        return "viharapala_review"
    if rev_state == "changes-required":
        return "silpi_address"
    if rev_state == "approved":
        return "merge"
    return "silpi_implement"


def detect_next_round(branch: str, ctx: Context) -> int:
    """Count 'Address review feedback' commits on the branch to find the next round number."""
    out = log_range("main", branch, ctx)
    if not out:
        return 1
    count = sum(1 for line in out.splitlines() if "Address review feedback" in line)
    return count + 1


def find_resumable_task(ctx: Context) -> tuple[dict | None, str | None, str, int]:
    """Find an interrupted in-progress task in priority order.

    Checks three sources in order:
      1. State file written at task-claim time (most reliable).
      2. Current feature branch matched against in-progress bd tasks.
      3. Any task already submitted for review (Viharapala may have crashed).

    Returns (task, branch, resume_state, round_num) or (None, None, "none", 1).
    """
    # 1. State file
    task, branch = load_task(ctx)
    if task and branch:
        task_id = task["id"]
        rev = review_state(task_id, ctx)
        state = classify_resume_state(rev)
        round_num = detect_next_round(branch, ctx) if state != "silpi_implement" else 1
        log(f"Resume: state file → task {task_id}, branch={branch}, state={state}, round={round_num}")
        return task, branch, state, round_num

    # 2. Current feature branch
    cur_branch = get_current_branch(ctx)
    if cur_branch.startswith("feature/"):
        for t in query_tasks("status=in_progress", ctx):
            if f"feature/{slugify(t['title'])}" == cur_branch:
                rev = review_state(t["id"], ctx)
                state = classify_resume_state(rev)
                round_num = detect_next_round(cur_branch, ctx)
                log(f"Resume: current branch → task {t['id']}, state={state}, round={round_num}")
                return t, cur_branch, state, round_num

    # 3. Any task already submitted for review (Viharapala crashed)
    rfr_tasks = tasks_with_label("review:ready-for-review", ctx)
    if rfr_tasks:
        t = rfr_tasks[0]
        branch = f"feature/{slugify(t['title'])}"
        round_num = detect_next_round(branch, ctx)
        log(f"Resume: ready-for-review → task {t['id']}, branch={branch}, round={round_num}")
        return t, branch, "viharapala_review", round_num

    # 4. Any non-epic task approved but not yet merged (merge step crashed)
    approved_tasks = [
        t for t in tasks_with_label("review:approved", ctx)
        if t.get("type") != "epic"
    ]
    if approved_tasks:
        t = approved_tasks[0]
        branch = f"feature/{slugify(t['title'])}"
        if branch_has_commits(branch, ctx):
            log(f"Resume: review=approved → task {t['id']}, branch={branch}, state=merge")
            return t, branch, "merge", 1
        elif task_merged_to_main(t["id"], ctx):
            # Merge landed in main but bd close failed — task_loop will close it.
            log(f"Resume: review=approved → task {t['id']}, already in main, state=merge (close only)")
            return t, branch, "merge", 1
        else:
            log(f"Resume: review=approved → task {t['id']}, branch has no commits — state=silpi_implement")
            return t, branch, "silpi_implement", 1

    return None, None, "none", 1
