"""Manage the beads JSONL → GitHub backup cron job (git push every 5 minutes).

Beads auto-exports issue data as JSONL to .beads/backup/ on its own interval.
This cron job commits and force-pushes that directory to a dedicated GitHub
repo (<project>-issues), giving off-machine backup with standard git/SSH auth.
"""

import shlex
import subprocess
import tempfile
from pathlib import Path

_CRON_SCHEDULE = "*/5 * * * *"


def _marker(repo_root: Path) -> str:
    return f"# shreni-bd-backup:{repo_root}"


def _backup_dir(repo_root: Path) -> Path:
    return repo_root / ".beads" / "backup"


def install(repo_root: Path, log_file: Path) -> None:
    """Install (or replace) the bd backup cron entry for this repo."""
    backup_dir = _backup_dir(repo_root)
    if not backup_dir.exists():
        raise RuntimeError(f"Backup dir not found: {backup_dir} — run shreni init first")

    # bd writes JSONL to .beads/issues.jsonl; copy it into the backup git repo
    # before committing so the GitHub repo always has the latest snapshot.
    issues_src = shlex.quote(str(repo_root / ".beads" / "issues.jsonl"))
    issues_dst = shlex.quote(str(backup_dir / "issues.jsonl"))
    push_cmd = (
        f"cp {issues_src} {issues_dst} 2>/dev/null;"
        f" cd {shlex.quote(str(backup_dir))}"
        f" && git add issues.jsonl"
        f" && git commit --allow-empty -m backup"
        f" && git push --force origin main"
        f" >> {shlex.quote(str(log_file))} 2>&1"
    )
    current = _read()
    lines = _remove_block(current.splitlines(), repo_root)
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
