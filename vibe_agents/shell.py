import re
import subprocess
from datetime import datetime
from pathlib import Path


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Sthapathi] {msg}", flush=True)


def make_logger(agent: str):
    """Return a log function that prefixes messages with the given agent name."""
    def _log(msg: str) -> None:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{agent}] {msg}", flush=True)
    return _log


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def run_cmd(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, check=True, cwd=cwd)


def run_cmd_output(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, check=False, text=True, capture_output=True, cwd=cwd)
    return result.stdout.strip()
