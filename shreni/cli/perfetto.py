"""Convert Shreni span streams to Chrome Trace Event Format.

The output is a JSON file that can be dragged into https://ui.perfetto.dev
or ``chrome://tracing``. Each bd task becomes a Perfetto "process" lane,
and each agent (plus a synthetic "orchestrator" lane for task-level spans
that have no agent) becomes a "thread" inside that lane.

Span pairing is done by ``span_id``: a ``span_start`` + matching ``span_end``
collapse into a single Chrome ``ph: "X"`` complete event. ``event`` records
become ``ph: "i"`` instant events on the same thread. Spans that never
closed (e.g. a crash mid-task) are skipped — they would otherwise dangle
in the viewer.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..context import Context
from ..observability import list_tasks, read_task_spans


def _parse_ts_us(ts: str) -> float:
    """Parse our ISO-8601 timestamps into microseconds since epoch."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.timestamp() * 1_000_000


def _read_session_spans(ctx: Context) -> list[dict[str, Any]]:
    path = ctx.session_spans_file
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def to_perfetto(records_by_lane: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Translate Shreni spans into a Chrome Trace Event Format document.

    ``records_by_lane`` maps a process-lane label (e.g. ``"task T-42"`` or
    ``"session"``) to a list of span records in chronological order.
    """
    events: list[dict[str, Any]] = []

    pid_map: dict[str, int] = {}
    tid_map: dict[tuple[int, str], int] = {}
    next_tid_per_pid: dict[int, int] = {}

    def get_pid(name: str) -> int:
        if name not in pid_map:
            pid_map[name] = len(pid_map)
            pid = pid_map[name]
            events.append({
                "name": "process_name", "ph": "M",
                "pid": pid, "args": {"name": name},
            })
            events.append({
                "name": "process_sort_index", "ph": "M",
                "pid": pid, "args": {"sort_index": pid},
            })
        return pid_map[name]

    def get_tid(pid: int, tname: str) -> int:
        key = (pid, tname)
        if key not in tid_map:
            count = next_tid_per_pid.get(pid, 0)
            tid_map[key] = count
            next_tid_per_pid[pid] = count + 1
            events.append({
                "name": "thread_name", "ph": "M",
                "pid": pid, "tid": count,
                "args": {"name": tname},
            })
        return tid_map[key]

    for lane_name, records in records_by_lane.items():
        pid = get_pid(lane_name)
        start_by_id: dict[str, dict[str, Any]] = {}
        for rec in records:
            agent = rec.get("agent") or "orchestrator"
            tid = get_tid(pid, agent)
            try:
                ts_us = _parse_ts_us(rec["ts"])
            except (KeyError, ValueError):
                continue

            rtype = rec.get("type")
            if rtype == "span_start":
                start_by_id[rec.get("span_id", "")] = rec
            elif rtype == "span_end":
                start_rec = start_by_id.pop(rec.get("span_id", ""), None)
                if start_rec is None:
                    continue
                start_ts = _parse_ts_us(start_rec["ts"])
                dur_us = float(rec.get("duration_ms", 0)) * 1000
                args: dict[str, Any] = {}
                if start_rec.get("attrs"):
                    args.update(start_rec["attrs"])
                if rec.get("status") and rec["status"] != "ok":
                    args["status"] = rec["status"]
                if rec.get("error"):
                    args["error"] = rec["error"]
                if start_rec.get("task_id"):
                    args.setdefault("task_id", start_rec["task_id"])
                events.append({
                    "name": rec.get("name", "span"),
                    "ph": "X",
                    "ts": start_ts,
                    "dur": dur_us,
                    "pid": pid,
                    "tid": tid,
                    "cat": agent,
                    "args": args,
                })
            elif rtype == "event":
                args = dict(rec.get("attrs") or {})
                if rec.get("task_id"):
                    args.setdefault("task_id", rec["task_id"])
                events.append({
                    "name": rec.get("name", "event"),
                    "ph": "i",
                    "s": "t",
                    "ts": ts_us,
                    "pid": pid,
                    "tid": tid,
                    "cat": agent,
                    "args": args,
                })

    return {"traceEvents": events, "displayTimeUnit": "ms"}


def export(ctx: Context, *, task: str | None, output: Path) -> int:
    """Entry point for ``shreni logs --perfetto``. Returns an exit code."""
    if task:
        records = read_task_spans(ctx, task)
        if not records:
            print(f"No spans recorded for task {task} under {ctx.task_obs_dir(task)}.")
            return 1
        lanes = {f"task {task}": records}
    else:
        lanes: dict[str, list[dict[str, Any]]] = {}
        session = _read_session_spans(ctx)
        if session:
            lanes["session"] = session
        for tid in list_tasks(ctx):
            recs = read_task_spans(ctx, tid)
            if recs:
                lanes[f"task {tid}"] = recs

    if not lanes:
        print(f"No spans found under {ctx.project_obs_dir}.")
        return 1

    trace = to_perfetto(lanes)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(trace))
    print(f"Wrote Perfetto trace ({len(trace['traceEvents'])} events) → {output}")
    print(f"Open at: https://ui.perfetto.dev  →  'Open trace file'  →  {output}")
    return 0
