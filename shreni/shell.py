import re
import subprocess
from datetime import datetime
from pathlib import Path

# ANSI color codes — tuned for black/dark backgrounds
_RESET    = "\033[0m"
_DIM      = "\033[90m"   # timestamp — dark gray, stays out of the way

_COLORS = {
    "Sthapathi":  "\033[96m",   # bright cyan   — orchestrator
    "Silpi":      "\033[92m",   # bright green  — implementer
    "Viharapala": "\033[93m",   # bright yellow — reviewer
    "Parikshaka": "\033[95m",   # bright magenta — QA
}
_DEFAULT_COLOR = "\033[97m"     # bright white  — any unknown agent


def _format(agent: str, msg: str) -> str:
    color = _COLORS.get(agent, _DEFAULT_COLOR)
    ts = f"{_DIM}[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{_RESET}"
    tag = f"{color}[{agent}]{_RESET}"
    return f"{ts} {tag} {msg}"


def log(msg: str) -> None:
    print(_format("Sthapathi", msg), flush=True)


def make_logger(agent: str):
    """Return a log function that prefixes messages with the given agent name and color."""
    def _log(msg: str) -> None:
        print(_format(agent, msg), flush=True)
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
