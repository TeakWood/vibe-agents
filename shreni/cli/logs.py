"""`shreni logs` — read structured span streams from disk.

Usage:
    shreni logs --repo /path/to/repo                  # list tasks observed
    shreni logs --repo /path/to/repo --task T-1       # timeline for one task
    shreni logs --repo /path/to/repo --task T-1 --raw # dump raw JSONL
"""

from __future__ import annotations

import json
from datetime import datetime

from ..context import Context
from ..observability import list_tasks, read_task_spans


def _format_event(rec: dict) -> str:
    ts = rec.get("ts", "")
    try:
        ts_short = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
    except Exception:
        ts_short = ts[:8]
    kind = rec.get("type", "?")
    name = rec.get("name", "")
    agent = rec.get("agent", "-")
    extra = ""
    if kind == "span_end":
        dur = rec.get("duration_ms")
        status = rec.get("status", "ok")
        extra = f" [{status} • {dur}ms]"
    elif kind == "event":
        attrs = rec.get("attrs") or {}
        if attrs:
            preview = " ".join(f"{k}={v}" for k, v in list(attrs.items())[:3])
            extra = f"  {preview}"
    return f"{ts_short}  {kind:<10}  {agent:<11}  {name}{extra}"


def run_logs(ctx: Context, *, task: str | None, raw: bool) -> int:
    """Entry point for the `shreni logs` subcommand. Returns an exit code."""
    if task is None:
        tasks = list_tasks(ctx)
        if not tasks:
            print(f"No task spans recorded yet under {ctx.project_obs_dir}/tasks/")
            return 0
        print(f"Tasks observed for '{ctx.project_name}' ({len(tasks)} total, newest first):")
        for tid in tasks:
            spans_path = ctx.task_spans_file(tid)
            size = spans_path.stat().st_size if spans_path.exists() else 0
            print(f"  {tid:<16}  spans.jsonl={size}B  ({ctx.task_obs_dir(tid)})")
        return 0

    records = read_task_spans(ctx, task)
    if not records:
        print(f"No spans recorded for task {task} under {ctx.task_obs_dir(task)}.")
        return 1

    if raw:
        for rec in records:
            print(json.dumps(rec))
        return 0

    print(f"Task {task}  —  {len(records)} event(s)  —  {ctx.task_spans_file(task)}")
    print("-" * 80)
    for rec in records:
        print(_format_event(rec))
    return 0
