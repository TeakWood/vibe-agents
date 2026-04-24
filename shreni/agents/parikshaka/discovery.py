"""Discover e2e test commands from the target repository."""

import json
import re
from pathlib import Path


def find_e2e_command(repo_root: Path) -> str | None:
    """Return the e2e test command for the repo, or None if none can be found.

    Checks in order:
      1. CLAUDE.md  — looks for an explicit e2e / playwright / cypress entry
      2. package.json scripts — common e2e script names
      3. pyproject.toml / Makefile — Python / generic projects
    """
    cmd = _from_claude_md(repo_root) or _from_package_json(repo_root) or _from_python(repo_root)
    return cmd


def _from_claude_md(repo_root: Path) -> str | None:
    claude_md = repo_root / "CLAUDE.md"
    if not claude_md.exists():
        return None
    text = claude_md.read_text()
    # Match a fenced code block or inline code after a heading that mentions e2e/playwright/cypress
    pattern = re.compile(
        r'(?i)(?:e2e|playwright|cypress)[^\n]*\n+```[^\n]*\n([^\n`]+)',
        re.MULTILINE,
    )
    m = pattern.search(text)
    if m:
        return m.group(1).strip()
    # Fallback: backtick inline code on a line mentioning e2e
    inline = re.compile(r'(?i)(?:e2e|playwright|cypress)[^\n]*`([^`]+)`')
    m = inline.search(text)
    return m.group(1).strip() if m else None


def _from_package_json(repo_root: Path) -> str | None:
    pkg = repo_root / "package.json"
    if not pkg.exists():
        return None
    try:
        scripts = json.loads(pkg.read_text()).get("scripts", {})
    except (json.JSONDecodeError, KeyError):
        return None
    preferred = ["e2e", "test:e2e", "test:playwright", "playwright", "cypress", "test:cypress"]
    for key in preferred:
        if key in scripts:
            runner = "npm run"
            # Use npx if the script calls playwright/cypress directly
            return f"{runner} {key}"
    return None


def _from_python(repo_root: Path) -> str | None:
    # Check for pytest e2e markers in pyproject.toml
    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text()
        if "e2e" in text or "playwright" in text:
            return "pytest tests/e2e -v"
    makefile = repo_root / "Makefile"
    if makefile.exists():
        text = makefile.read_text()
        m = re.search(r'^(e2e|test-e2e|test\.e2e)\s*:', text, re.MULTILINE)
        if m:
            return f"make {m.group(1)}"
    return None
