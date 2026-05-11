"""Per-task structured spans and events.

Records a JSONL stream of OpenTelemetry-flavoured span events under
``~/.shreni/projects/<slug>/tasks/<task_id>/spans.jsonl``. Events that
happen outside a task (orchestrator startup, idle ticks, queue replays)
are written to the project-level ``session-spans.jsonl`` instead.

Event shapes
------------
``span_start``  → opens a span (records ``span_id`` and ``parent_span_id``)
``span_end``    → closes the matching span (adds ``duration_ms`` and ``status``)
``event``       → instantaneous point-in-time fact attached to the current span

Spans nest via ContextVars, so callers do not need to thread span ids
through every function. The ``span()`` context manager handles
start/end pairing and re-entrancy across async tasks.
"""

import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .context import Context

_current_span_id: ContextVar[str | None] = ContextVar("shreni_current_span_id", default=None)
_current_task_id: ContextVar[str | None] = ContextVar("shreni_current_task_id", default=None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _spans_path(ctx: Context, task_id: str | None) -> Path:
    path = ctx.task_spans_file(task_id) if task_id else ctx.session_spans_file
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write(ctx: Context, task_id: str | None, record: dict[str, Any]) -> None:
    path = _spans_path(ctx, task_id)
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def current_task_id() -> str | None:
    return _current_task_id.get()


def emit_event(
    ctx: Context,
    name: str,
    *,
    agent: str | None = None,
    task_id: str | None = None,
    attrs: dict[str, Any] | None = None,
) -> None:
    """Record a point-in-time event under the current (or given) span."""
    tid = task_id or _current_task_id.get()
    record = {
        "ts": _now_iso(),
        "type": "event",
        "name": name,
    }
    if agent:
        record["agent"] = agent
    if tid:
        record["task_id"] = tid
    parent = _current_span_id.get()
    if parent:
        record["parent_span_id"] = parent
    if attrs:
        record["attrs"] = attrs
    _write(ctx, tid, record)


@contextmanager
def span(
    ctx: Context,
    name: str,
    *,
    agent: str | None = None,
    task_id: str | None = None,
    attrs: dict[str, Any] | None = None,
) -> Iterator[str]:
    """Open a span; emits matching span_start / span_end records.

    If ``task_id`` is provided, it becomes the current task for any nested
    spans/events until this context exits. Nested spans automatically link
    to this span via ``parent_span_id``.
    """
    span_id = uuid.uuid4().hex[:16]
    tid = task_id or _current_task_id.get()
    parent = _current_span_id.get()

    start_record: dict[str, Any] = {
        "ts": _now_iso(),
        "type": "span_start",
        "name": name,
        "span_id": span_id,
    }
    if agent:
        start_record["agent"] = agent
    if tid:
        start_record["task_id"] = tid
    if parent:
        start_record["parent_span_id"] = parent
    if attrs:
        start_record["attrs"] = attrs
    _write(ctx, tid, start_record)

    span_token = _current_span_id.set(span_id)
    task_token = _current_task_id.set(task_id) if task_id else None

    started = time.monotonic()
    status = "ok"
    error_message: str | None = None
    try:
        yield span_id
    except BaseException as exc:
        status = "error"
        error_message = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        _current_span_id.reset(span_token)
        if task_token is not None:
            _current_task_id.reset(task_token)

        end_record: dict[str, Any] = {
            "ts": _now_iso(),
            "type": "span_end",
            "name": name,
            "span_id": span_id,
            "duration_ms": duration_ms,
            "status": status,
        }
        if agent:
            end_record["agent"] = agent
        if tid:
            end_record["task_id"] = tid
        if parent:
            end_record["parent_span_id"] = parent
        if error_message:
            end_record["error"] = error_message
        _write(ctx, tid, end_record)


def read_task_spans(ctx: Context, task_id: str) -> list[dict[str, Any]]:
    """Return all span records for a task in chronological order."""
    path = ctx.task_spans_file(task_id)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def list_tasks(ctx: Context) -> list[str]:
    """Return task ids that have an observability folder, newest first."""
    tasks_dir = ctx.project_obs_dir / "tasks"
    if not tasks_dir.exists():
        return []
    entries = [p for p in tasks_dir.iterdir() if p.is_dir()]
    entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in entries]
