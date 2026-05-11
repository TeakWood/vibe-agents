"""Optional tmux log session — opens a detached window tailing all agent logs.

Layout (even-horizontal, 3 panes with titled borders):
  ┌─ shreni-silpi ──┬─ shreni-viharapala ─┬─ shreni-parikshaka ─┐
  │  silpi.log      │  viharapala.log      │  parikshaka.log     │
  └─────────────────┴──────────────────────┴─────────────────────┘

Attach: tmux attach -t shreni-<project>
"""

import shutil
import subprocess
from pathlib import Path

from .context import Context
from .shell import log

_AGENTS = ["silpi", "viharapala", "parikshaka"]


def start_log_session(ctx: Context) -> None:
    """Open a detached tmux session tailing all agent logs.

    Passes the tail command directly to new-session/split-window rather than
    using send-keys, so pane-base-index in ~/.tmux.conf has no effect.

    Skips silently if tmux is not installed. If a session for this project
    already exists, prints the attach command and returns without recreating it.
    A tmux failure is non-fatal — shreni continues and logs the manual fallback.
    """
    if shutil.which("tmux") is None:
        return

    session = f"shreni-{ctx.project_name.lower().replace(' ', '-')}"
    log_dir = ctx.project_obs_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # Pre-create the per-agent aggregate log files so `tail -f` does not error
    # before the first agent run. Per-task logs live under tasks/<task_id>/ and
    # are created on demand by the runner.
    for name in _AGENTS:
        (log_dir / f"{name}.log").touch(exist_ok=True)

    if _session_exists(session):
        log(f"tmux session '{session}' already running — attach with: tmux attach -t {session}")
        return

    try:
        # First pane: silpi — command passed directly, no send-keys needed
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, "-n", "logs",
             f"tail -f {log_dir / 'silpi.log'}"],
            check=True,
        )
        # Enable pane border titles (top bar showing pane name)
        subprocess.run(
            ["tmux", "set-option", "-t", session, "pane-border-status", "top"],
            check=True,
        )
        subprocess.run(
            ["tmux", "set-option", "-t", session, "pane-border-format",
             " #{pane_title} "],
            check=True,
        )
        # Title the silpi pane — newly created pane is always active,
        # so targeting the window without a pane index hits the right one
        _set_title(session, f"shreni-silpi")

        # Remaining panes: split horizontally, title immediately after creation
        for name in _AGENTS[1:]:
            subprocess.run(
                ["tmux", "split-window", "-h", "-t", f"{session}:logs",
                 f"tail -f {log_dir / f'{name}.log'}"],
                check=True,
            )
            _set_title(session, f"shreni-{name}")

        # Equalise pane widths
        subprocess.run(
            ["tmux", "select-layout", "-t", f"{session}:logs", "even-horizontal"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        log(f"Warning: tmux session setup failed ({e}) — monitor logs manually:")
        for name in _AGENTS:
            log(f"  tail -f {log_dir / f'{name}.log'}")
        return

    log(f"tmux session '{session}' started.")
    log(f"  Attach: tmux attach -t {session}")


def _session_exists(session: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True,
    )
    return result.returncode == 0


def _set_title(session: str, title: str) -> None:
    """Set the title of the currently active pane in the logs window."""
    subprocess.run(
        ["tmux", "select-pane", "-t", f"{session}:logs", "-T", title],
        check=True,
    )
