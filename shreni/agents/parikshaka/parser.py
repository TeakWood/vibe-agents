"""Parse e2e test output and extract individual failure descriptions."""

import re
from dataclasses import dataclass


@dataclass
class TestFailure:
    title: str       # Short name suitable for a bd task title
    detail: str      # Relevant excerpt from output for the description


def parse_failures(output: str, command: str) -> list[TestFailure]:
    """Extract individual test failures from e2e runner output.

    Handles Playwright, Cypress, and pytest output formats.
    Falls back to a single generic failure if no specific tests can be identified.
    """
    failures: list[TestFailure] = []

    failures = (
        _parse_playwright(output)
        or _parse_pytest(output)
        or _parse_cypress(output)
    )

    if not failures and _looks_like_failure(output):
        failures = [TestFailure(
            title=f"E2E test run failed: {command.split()[-1]}",
            detail=output[-2000:],
        )]

    return failures


# ── Playwright ────────────────────────────────────────────────────────────────

def _parse_playwright(output: str) -> list[TestFailure]:
    """Match:  ✘  tests/foo.spec.ts:12:5 › Suite › test name"""
    pattern = re.compile(
        r'(?:×|✘|FAILED)\s+(.+?)\s*(?:\n|$)(.*?)(?=(?:×|✘|FAILED|\Z))',
        re.DOTALL,
    )
    results = []
    for m in pattern.finditer(output):
        name = m.group(1).strip()
        detail = (m.group(2) or "").strip()[:1500]
        results.append(TestFailure(title=f"E2E: {name}", detail=detail))
    # Also try the simpler `  X failed` summary block
    if not results:
        block = re.search(r'(\d+) failed.*?(?=\n\n|\Z)', output, re.DOTALL)
        if block:
            lines = [l.strip() for l in block.group(0).splitlines() if l.strip()]
            for line in lines[1:6]:  # skip summary line, take up to 5 failures
                results.append(TestFailure(title=f"E2E: {line}", detail=block.group(0)[:1500]))
    return results


# ── pytest ────────────────────────────────────────────────────────────────────

def _parse_pytest(output: str) -> list[TestFailure]:
    """Match:  FAILED tests/e2e/test_foo.py::TestClass::test_name - AssertionError"""
    pattern = re.compile(r'^FAILED\s+(\S+)\s*-?\s*(.*)$', re.MULTILINE)
    results = []
    for m in pattern.finditer(output):
        test_id = m.group(1)
        reason = m.group(2).strip()
        results.append(TestFailure(
            title=f"E2E: {test_id}",
            detail=reason or test_id,
        ))
    return results


# ── Cypress ───────────────────────────────────────────────────────────────────

def _parse_cypress(output: str) -> list[TestFailure]:
    """Match failure blocks in Cypress text output."""
    pattern = re.compile(
        r'(?:\d+\)|\bfailing\b)[^\n]*\n\s+(.+?)(?=\n\s*\d+\)|\Z)',
        re.DOTALL,
    )
    results = []
    for m in pattern.finditer(output):
        name = m.group(1).strip().splitlines()[0]
        detail = m.group(1).strip()[:1500]
        results.append(TestFailure(title=f"E2E: {name}", detail=detail))
    return results


def _looks_like_failure(output: str) -> bool:
    keywords = re.compile(r'\b(?:failed|error|FAIL|ERROR)\b', re.IGNORECASE)
    return bool(keywords.search(output))
