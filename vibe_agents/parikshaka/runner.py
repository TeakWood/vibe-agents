"""Pariksaka runner — invoked by cron every 30 minutes.

Steps:
  1. Run the e2e command in the target repo.
  2. If it passes, log success and exit.
  3. If it fails, parse individual test failures.
  4. For each failure, create a bd bug task unless one is already open.

Run as:
    python -m vibe_agents.parikshaka.runner --repo /path/to/repo --command "npm run e2e"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .parser import TestFailure, parse_failures
from ..shell import make_logger

log = make_logger("Parikshaka")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--command", required=True)
    args = parser.parse_args()

    repo_root = args.repo.resolve()
    command = args.command

    log(f"Running: {command}")
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    output = result.stdout + result.stderr

    if result.returncode == 0:
        log("All e2e tests passed.")
        return

    log(f"Tests failed (exit {result.returncode}). Parsing failures...")
    failures = parse_failures(output, command)

    if not failures:
        log("Could not parse individual failures — creating one generic bug.")

    for failure in failures:
        _report_failure(failure, repo_root)


def _report_failure(failure: TestFailure, repo_root: Path) -> None:
    """Create a bd bug for this failure unless an open one already exists."""
    if _bug_already_open(failure.title, repo_root):
        log(f"Bug already open for: {failure.title!r} — skipping.")
        return

    description = (
        f"Pariksaka detected a failing e2e test.\n\n"
        f"## Failure\n{failure.detail}\n\n"
        f"## Reproduce\nRun the e2e suite against this repo."
    )

    result = subprocess.run(
        [
            "bd", "create", failure.title,
            "--type", "bug",
            "--description", description,
            "--priority", "1",
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    if result.returncode == 0:
        try:
            task = json.loads(result.stdout)
            log(f"Created bug {task.get('id', '?')}: {failure.title!r}")
        except json.JSONDecodeError:
            log(f"Created bug: {failure.title!r}")
    else:
        log(f"ERROR creating bug for {failure.title!r}: {result.stderr.strip()}")


def _bug_already_open(title: str, repo_root: Path) -> bool:
    """Return True if an open bug with this exact title already exists in bd."""
    # bd query title= does a "contains" match; we check for exact match after.
    result = subprocess.run(
        ["bd", "query", f"title={title} AND type=bug AND status!=closed", "--json"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    try:
        tasks = json.loads(result.stdout or "[]")
        return any(t.get("title") == title for t in tasks)
    except json.JSONDecodeError:
        return False


if __name__ == "__main__":
    main()
