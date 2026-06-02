"""Beads (bd) task-tracker CLI integration."""

import json
import subprocess

from .context import Context
from .shell import log, run_cmd, run_cmd_output


def ensure_initialized(ctx: Context) -> None:
    result = subprocess.run(
        ["bd", "ready", "--json"],
        check=False, text=True, capture_output=True, cwd=ctx.repo_root,
    )
    if result.returncode == 0:
        return
    log(f"bd not initialized in {ctx.repo_root}. Initializing as '{ctx.project_name}'...")
    subprocess.run(["bd", "init", ctx.project_name], check=True, cwd=ctx.repo_root)
    log("bd initialized.")


def review_state(task_id: str, ctx: Context) -> str:
    out = run_cmd_output(["bd", "state", task_id, "review"], ctx.repo_root)
    return out.strip('"')


def task_status(task_id: str, ctx: Context) -> str:
    out = run_cmd_output(["bd", "state", task_id, "status"], ctx.repo_root)
    return out.strip('"')


def breakdown_state(epic_id: str, ctx: Context) -> str:
    out = run_cmd_output(["bd", "state", epic_id, "breakdown"], ctx.repo_root)
    return out.strip('"')


def query_tasks(filter_expr: str, ctx: Context) -> list[dict]:
    """Query tasks using bd query syntax (status/type/assignee etc. — no label: values)."""
    try:
        result = subprocess.run(
            ["bd", "query", filter_expr, "--json"],
            check=False, text=True, capture_output=True, cwd=ctx.repo_root,
        )
        return json.loads(result.stdout or "[]")
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def tasks_with_label(label: str, ctx: Context) -> list[dict]:
    """Return all open tasks that carry a specific label (e.g. 'review:approved').

    bd query cannot handle label values containing colons, so this fetches all
    tasks via bd list and filters in Python.
    """
    try:
        result = subprocess.run(
            ["bd", "list", "--json"],
            check=False, text=True, capture_output=True, cwd=ctx.repo_root,
        )
        tasks = json.loads(result.stdout or "[]")
        return [t for t in tasks if label in (t.get("labels") or [])]
    except (json.JSONDecodeError, FileNotFoundError):
        return []


# Dependent issue_types that are bd bookkeeping, not real child work. Every
# `set-state` on an epic creates a closed `event` bead linked parent-child; the
# rest are bd infrastructure. None of these should count toward epic closure.
_NON_CHILD_TYPES = {"event", "agent", "rig", "role", "message", "gate", "template"}


def epic_children(epic_id: str, ctx: Context) -> list[dict]:
    """Return an epic's child tasks (id, status, issue_type, dependency_type each).

    Silpi links breakdown tasks to their epic with a `discovered-from`
    dependency, so the epic's `dependents` of that type are its children. Native
    `parent-child` links are included too (manual children), but bd's own
    bookkeeping beads — notably the `event` records every `set-state` creates —
    are filtered out. bd's `epic_total_children` / `epic_closeable` fields are
    NOT used: they count only `parent-child` links and ignore the
    `discovered-from` edges Silpi actually creates.
    """
    try:
        result = subprocess.run(
            ["bd", "show", epic_id, "--json"],
            check=False, text=True, capture_output=True, cwd=ctx.repo_root,
        )
        data = json.loads(result.stdout or "[]")
    except (json.JSONDecodeError, FileNotFoundError):
        return []
    epic = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
    if not epic:
        return []
    return [
        d for d in (epic.get("dependents") or [])
        if d.get("dependency_type") in ("discovered-from", "parent-child")
        and d.get("issue_type") not in _NON_CHILD_TYPES
    ]


def epic_ready_to_close(epic_id: str, ctx: Context) -> bool:
    """True when an epic has children and every one of them is closed.

    Guards against closing an epic that was never broken down (no children) —
    such an epic is left untouched.
    """
    children = epic_children(epic_id, ctx)
    return bool(children) and all(c.get("status") == "closed" for c in children)


def active_parent_ids(ctx: Context) -> set[str]:
    """Return parent IDs of all currently in-progress tasks.

    Used to prefer ready tasks that share a parent with work already underway,
    ensuring an epic/feature group is fully completed before starting a new one.
    bd does not auto-set epics to in_progress, so we derive the active set from
    the children instead.
    """
    in_progress = query_tasks("status=in_progress", ctx)
    return {t["parent"] for t in in_progress if t.get("parent")}


def ready_tasks(ctx: Context) -> list[dict]:
    try:
        result = subprocess.run(
            ["bd", "ready", "--json"],
            check=False, text=True, capture_output=True, cwd=ctx.repo_root,
        )
        return json.loads(result.stdout or "[]")
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def show_task(task_id: str, ctx: Context) -> str:
    return run_cmd_output(["bd", "show", task_id], ctx.repo_root)


def get_comments(task_id: str, ctx: Context) -> str:
    return run_cmd_output(["bd", "comments", task_id], ctx.repo_root)


def claim_task(task_id: str, ctx: Context) -> None:
    run_cmd(["bd", "update", task_id, "--claim", "--json"], ctx.repo_root)


def set_state(task_id: str, state_expr: str, reason: str, ctx: Context) -> None:
    run_cmd(
        ["bd", "set-state", task_id, state_expr, "--reason", reason, "--json"],
        ctx.repo_root,
    )


def close_task(task_id: str, reason: str, ctx: Context, force: bool = False) -> bool:
    """Close a task. Returns True on success, False if bd refused.

    Pass force=True to override bd's open-dependency guard — appropriate when
    the work is already merged to main, where the dependency block is moot.
    The real stderr is surfaced on failure rather than a generic guess.
    """
    cmd = ["bd", "close", task_id, "--reason", reason, "--json"]
    if force:
        cmd.append("--force")
    result = subprocess.run(
        cmd, check=False, text=True, capture_output=True, cwd=ctx.repo_root,
    )
    if result.returncode == 0:
        return True
    detail = (result.stderr or result.stdout).strip()
    log(f"Warning: could not close task {task_id}: {detail or 'unknown error'}")
    return False
