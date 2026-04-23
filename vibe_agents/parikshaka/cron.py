"""Manage per-repo crontab entries for the Pariksaka runner."""

import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

# Project root so cron can invoke the runner module
_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


def _marker(repo_root: Path) -> str:
    """Unique comment line that identifies our crontab block for this repo."""
    return f"# vibe-agents-parikshaka:{repo_root}"


def install(command: str, repo_root: Path, log_file: Path) -> None:
    """Add a crontab block (comment + entry) that runs Pariksaka every 30 minutes."""
    current = _read()
    lines = _remove_block(current.splitlines(), repo_root)

    # Shell-escape the e2e command so it survives being passed as a -c argument
    safe_command = command.strip().replace("\n", " ").replace("\r", "")
    runner_invocation = (
        f"{sys.executable} -m vibe_agents.parikshaka.runner "
        f"--repo {shlex.quote(str(repo_root))} "
        f"--command {shlex.quote(safe_command)}"
    )
    # Two-line block: marker comment + cron entry (macOS crontab does not support
    # inline # comments after the command field)
    lines += [
        _marker(repo_root),
        f"*/30 * * * * cd {shlex.quote(str(_PROJECT_ROOT))} && {runner_invocation} >> {shlex.quote(str(log_file))} 2>&1",
    ]
    _write("\n".join(lines) + "\n")


def remove(repo_root: Path) -> None:
    """Remove the Pariksaka crontab block for this repo."""
    current = _read()
    lines = _remove_block(current.splitlines(), repo_root)
    _write("\n".join(lines) + "\n")


def _remove_block(lines: list[str], repo_root: Path) -> list[str]:
    """Strip the marker comment and the cron entry that follows it."""
    marker = _marker(repo_root)
    result = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line == marker:
            skip_next = True  # also drop the cron line that follows
            continue
        result.append(line)
    return result


def _read() -> str:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def _write(content: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cron", delete=False) as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        subprocess.run(["crontab", str(tmp)], check=True)
    finally:
        tmp.unlink(missing_ok=True)
