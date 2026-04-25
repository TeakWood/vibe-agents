"""Manage the bd → DoltHub backup cron job (dolt push every 5 minutes).

The push command bypasses bd dolt push (which has a port bug in server mode)
and calls dolt directly from the embedded dolt repo path:
  .beads/embeddeddolt/<prefix>/
"""

import shlex
import subprocess
import tempfile
from pathlib import Path

_CRON_SCHEDULE = "*/5 * * * *"


def _marker(repo_root: Path) -> str:
    return f"# shreni-bd-backup:{repo_root}"


def _dolt_db_path(repo_root: Path) -> Path | None:
    """Locate the embedded dolt repo inside .beads/embeddeddolt/."""
    dolt_dir = repo_root / ".beads" / "embeddeddolt"
    if not dolt_dir.exists():
        return None
    subdirs = [d for d in dolt_dir.iterdir() if d.is_dir()]
    return subdirs[0] if subdirs else None


def install(repo_root: Path, log_file: Path) -> None:
    """Install (or replace) the bd backup cron entry for this repo."""
    db_path = _dolt_db_path(repo_root)
    if db_path is None:
        raise RuntimeError(f"Cannot find embedded dolt repo under {repo_root}/.beads/embeddeddolt/")

    current = _read()
    lines = _remove_block(current.splitlines(), repo_root)

    push_cmd = (
        f"cd {shlex.quote(str(db_path))} && dolt push origin main"
        f" >> {shlex.quote(str(log_file))} 2>&1"
    )
    lines += [
        _marker(repo_root),
        f"{_CRON_SCHEDULE} {push_cmd}",
    ]
    _write("\n".join(lines) + "\n")


def remove(repo_root: Path) -> None:
    """Remove the bd backup cron entry for this repo."""
    current = _read()
    lines = _remove_block(current.splitlines(), repo_root)
    _write("\n".join(lines) + "\n")


def is_installed(repo_root: Path) -> bool:
    return _marker(repo_root) in _read()


def _remove_block(lines: list[str], repo_root: Path) -> list[str]:
    marker = _marker(repo_root)
    result = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line == marker:
            skip_next = True
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
