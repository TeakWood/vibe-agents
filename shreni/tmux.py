"""Optional tmux log session — opens a detached window tailing all agent logs.

Layout (even-horizontal, 3 panes):
  ┌──────────────┬─────────────────┬──────────────┐
  │    Silpi     │   Viharapala    │  Parikshaka  │
  │   silpi.log  │ viharapala.log  │parikshaka.log│
  └──────────────┴─────────────────┴──────────────┘

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

    Skips silently if tmux is not installed. If a session for this project
    already exists, prints the attach command and returns without recreating it.
    """
    if shutil.which("tmux") is None:
        return

    session = f"shreni-{ctx.project_name.lower().replace(' ', '-')}"
    log_dir = ctx.repo_root / ".claude"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Pre-create log files so tail -f doesn't error before the first agent run
    for name in _AGENTS:
        (log_dir / f"{name}.log").touch(exist_ok=True)

    # Don't recreate if already running
    if _session_exists(session):
        log(f"tmux session '{session}' already running — attach with: tmux attach -t {session}")
        return

    # Create detached session; first pane gets silpi.log
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session, "-n", "logs"],
        check=True,
    )
    _send(session, 0, f"tail -f {log_dir / 'silpi.log'}")
    _set_title(session, 0, "Silpi")

    # Add viharapala and parikshaka panes
    for i, name in enumerate(_AGENTS[1:], start=1):
        subprocess.run(
            ["tmux", "split-window", "-h", "-t", f"{session}:logs"],
            check=True,
        )
        _send(session, i, f"tail -f {log_dir / f'{name}.log'}")
        _set_title(session, i, name.capitalize())

    # Even horizontal layout so all three panes share space equally
    subprocess.run(
        ["tmux", "select-layout", "-t", f"{session}:logs", "even-horizontal"],
        check=True,
    )

    # Focus the silpi pane
    subprocess.run(
        ["tmux", "select-pane", "-t", f"{session}:logs.0"],
        check=True,
    )

    log(f"tmux session '{session}' started.")
    log(f"  Attach: tmux attach -t {session}")


def _session_exists(session: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True,
    )
    return result.returncode == 0


def _send(session: str, pane: int, cmd: str) -> None:
    subprocess.run(
        ["tmux", "send-keys", "-t", f"{session}:logs.{pane}", cmd, "Enter"],
        check=True,
    )


def _set_title(session: str, pane: int, title: str) -> None:
    subprocess.run(
        ["tmux", "select-pane", "-t", f"{session}:logs.{pane}", "-T", title],
        check=True,
    )
