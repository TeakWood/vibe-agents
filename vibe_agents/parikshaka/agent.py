"""Pariksaka (परीक्षक) — QA agent, runs as a child process spawned by the orchestrator.

Lifecycle:
  1. Discovers the e2e command for the target repo.
  2. Installs a crontab entry to run it every 30 minutes.
  3. Sleeps until SIGTERM is received.
  4. On SIGTERM: removes the crontab entry and exits cleanly.

Run as:
    python -m vibe_agents.parikshaka.agent --repo /path/to/repo
"""

import argparse
import signal
import sys
import time
from pathlib import Path

from .cron import install, remove
from .discovery import find_e2e_command
from ..shell import make_logger

log = make_logger("Parikshaka")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pariksaka — e2e cron manager")
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args()

    repo_root = args.repo.resolve()
    log_file = repo_root / ".claude" / "qa-e2e.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    command = find_e2e_command(repo_root)
    if not command:
        log(f"No e2e command found in {repo_root}. Exiting.")
        sys.exit(0)

    log(f"e2e command: {command}")
    log(f"Installing cron job (every 30 min). Log → {log_file}")
    install(command, repo_root, log_file)
    log("Cron job installed. Waiting for shutdown signal.")

    def _shutdown(signum: int, _frame: object) -> None:
        log(f"Signal {signum} received — removing cron job...")
        remove(repo_root)
        log("Cron job removed. Exiting.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
