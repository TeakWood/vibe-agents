"""shreni init — set up a new project for autonomous development.

Two phases:

  Phase 1 — Machine prerequisites (one-time per machine)
    Checks dolt, bd, claude, and gh CLI are installed and authenticated.
    If anything is missing, prints the exact steps needed and exits.
    Re-run `shreni init` after completing them.

  Phase 2 — Per-project setup
    bd init, beads backup config, GitHub issues repo, backup cron, CLAUDE.md.
    Issue data is backed up as JSONL to a dedicated GitHub repo
    (<project>-issues) via plain git — no DoltHub credentials needed.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import anyio

from .agents import silpi as silpi_agent
from .backup import install as install_backup
from .context import Context
from .shell import log, make_logger

_silpi = make_logger("Silpi")


# ── Phase 1: Machine prerequisites ────────────────────────────────────────────

def _check_dolt_installed() -> None:
    if shutil.which("dolt") is None:
        print("\n  ✗ dolt — not installed")
        print("\n" + "━" * 56)
        print("  Machine setup required — install dolt, then re-run:")
        print("  shreni init --repo <path>")
        print("━" * 56)
        print("\n  brew install dolt\n")
        sys.exit(1)
    print("  ✓ dolt installed")


def _check_gh_installed() -> str:
    """Check gh CLI is installed and authenticated. Returns GitHub username."""
    if shutil.which("gh") is None:
        print("\n  ✗ gh — not installed")
        print("\n" + "━" * 56)
        print("  Machine setup required — install GitHub CLI, then re-run:")
        print("  shreni init --repo <path>")
        print("━" * 56)
        print("\n  brew install gh && gh auth login\n")
        sys.exit(1)
    print("  ✓ gh installed")

    result = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("\n  ✗ gh — not authenticated")
        print("\n" + "━" * 56)
        print("  Run: gh auth login")
        print("━" * 56)
        sys.exit(1)

    username = result.stdout.strip()
    print(f"  ✓ gh authenticated (User: {username})")
    return username


def _check_bd_installed() -> None:
    if shutil.which("bd") is None:
        print("\n  ✗ bd — not installed")
        print("\n" + "━" * 56)
        print("  Machine setup required — install Beads, then re-run:")
        print("  shreni init --repo <path>")
        print("━" * 56)
        print("\n  See: https://github.com/dolt-hub/beads for install instructions\n")
        sys.exit(1)
    print("  ✓ bd installed")


def _check_claude_installed() -> None:
    if shutil.which("claude") is None:
        print("\n  ✗ claude — not installed")
        print("\n" + "━" * 56)
        print("  Machine setup required — install Claude Code, then re-run:")
        print("  shreni init --repo <path>")
        print("━" * 56)
        print("\n  See: https://claude.ai/claude-code\n")
        sys.exit(1)
    print("  ✓ claude installed")


def _check_graphify_installed() -> None:
    if shutil.which("graphify") is None:
        print("\n  ✗ graphify — not installed")
        print("\n" + "━" * 56)
        print("  Machine setup required — install Graphify, then re-run:")
        print("  shreni init --repo <path>")
        print("━" * 56)
        print("\n  pipx install graphifyy && graphify install\n")
        sys.exit(1)
    print("  ✓ graphify installed")


# ── Phase 2: Per-project setup ────────────────────────────────────────────────

def _bd_prefix(project_name: str) -> str:
    """Derive the bd issue prefix from the project name (lowercase slug)."""
    return re.sub(r"[^a-z0-9]", "-", project_name.lower()).strip("-")


def _ensure_bd_initialized(ctx: Context) -> str:
    """Run bd init if the prefix database directory does not exist yet.

    Checks for .beads/embeddeddolt/<prefix>/ specifically — not just .beads/.
    This avoids re-running bd init when the database already exists (bd init
    refuses with an error if any database directory is found in embeddeddolt/).
    """
    prefix = _bd_prefix(ctx.project_name)
    dolt_path = ctx.repo_root / ".beads" / "embeddeddolt" / prefix
    if dolt_path.exists():
        log(f"bd database '{prefix}' exists — skipping bd init.")
        return prefix
    log(f"Initializing bd with prefix '{prefix}'...")
    subprocess.run(
        ["bd", "init", "--prefix", prefix, "--non-interactive"],
        check=True, cwd=ctx.repo_root,
    )
    log(f"bd initialized with prefix '{prefix}'.")
    return prefix


def _gitignore_beads(ctx: Context) -> None:
    """Ensure .beads/ is in .gitignore and untracked from git.

    Dolt already versions all task state in .beads/embeddeddolt/. Tracking
    .beads/ in project git causes checkout conflicts when agents switch branches
    after running bd commands that write to .beads/issues.jsonl.
    """
    gitignore = ctx.repo_root / ".gitignore"
    content = gitignore.read_text() if gitignore.exists() else ""
    if ".beads/" not in content:
        with gitignore.open("a") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write(".beads/\n")
        log(".beads/ added to .gitignore.")
    else:
        log(".beads/ already in .gitignore — skipping.")

    # Remove from git index if currently tracked
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".beads/"],
        capture_output=True, cwd=ctx.repo_root,
    )
    if result.returncode == 0:
        subprocess.run(
            ["git", "rm", "-r", "--cached", ".beads/"],
            check=True, cwd=ctx.repo_root,
        )
        subprocess.run(
            ["git", "commit", "-m", "chore: stop tracking .beads/ (Dolt is the source of truth)"],
            check=True, cwd=ctx.repo_root,
        )
        log(".beads/ removed from git index and committed.")


def _run_graphify(ctx: Context) -> None:
    """Wire graphify into Claude Code and install git hooks for auto-rebuild.

    The graph itself is built lazily the first time an agent runs /graphify.
    This step configures the CLAUDE.md section + PreToolUse hook so agents
    can use it, and installs git hooks so the graph stays current after commits.
    """
    log("Configuring graphify for Claude Code...")
    subprocess.run(
        ["graphify", "claude", "install"],
        check=True, cwd=ctx.repo_root,
    )
    log("graphify Claude Code integration installed (CLAUDE.md + PreToolUse hook).")

    log("Installing graphify git hooks...")
    subprocess.run(
        ["graphify", "hook", "install"],
        check=True, cwd=ctx.repo_root,
    )
    log("graphify git hooks installed (auto-rebuild on commit/branch switch).")

    gitignore = ctx.repo_root / ".gitignore"
    content = gitignore.read_text() if gitignore.exists() else ""
    if "graphify-out/" not in content:
        with gitignore.open("a") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write("graphify-out/\n")
        log("graphify-out/ added to .gitignore.")
    else:
        log("graphify-out/ already in .gitignore — skipping.")


def _configure_beads_backup(ctx: Context) -> None:
    """Append backup config to .beads/config.yaml if not already present."""
    config_file = ctx.repo_root / ".beads" / "config.yaml"
    if not config_file.exists():
        log("Warning: .beads/config.yaml not found — skipping backup config.")
        return
    content = config_file.read_text()
    if "backup:" in content:
        log("Backup config already in .beads/config.yaml — skipping.")
        return
    config_file.open("a").write(
        "\nbackup:\n"
        "  enabled: true\n"
        "  git-push: false\n"   # prevents backup commits racing with agent commits
        "  interval: 15m\n"
    )
    log("Backup config written to .beads/config.yaml")


def _init_jsonl_backup_repo(ctx: Context, github_username: str, repo_name: str) -> None:
    """Create the GitHub issues repo and init .beads/backup/ as its local clone."""
    backup_dir = ctx.repo_root / ".beads" / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    if (backup_dir / ".git").exists():
        log("JSONL backup repo already initialized — skipping.")
        return

    remote_url = f"git@github.com:{github_username}/{repo_name}.git"

    # Create the GitHub repo (private). Ignore "already exists" errors.
    log(f"Creating GitHub repo: {github_username}/{repo_name}")
    result = subprocess.run(
        ["gh", "repo", "create", repo_name, "--private"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 and "already exists" not in result.stderr:
        log(f"Warning: gh repo create failed: {result.stderr.strip()}")
        log(f"Create it manually: gh repo create {repo_name} --private")
    else:
        log(f"GitHub repo ready: github.com/{github_username}/{repo_name}")

    # Init local git repo inside .beads/backup/
    subprocess.run(["git", "init", "-b", "main"], check=True, cwd=backup_dir)
    subprocess.run(["git", "remote", "add", "origin", remote_url], check=True, cwd=backup_dir)

    # Write a .gitignore for the backup repo itself
    gitignore = backup_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*.lock\n*.tmp\n.DS_Store\n")

    # Seed with issues.jsonl if beads has already exported one
    issues_src = ctx.repo_root / ".beads" / "issues.jsonl"
    if issues_src.exists():
        import shutil as _shutil
        _shutil.copy2(issues_src, backup_dir / "issues.jsonl")
    subprocess.run(["git", "add", "issues.jsonl", ".gitignore"], cwd=backup_dir)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init: beads issue backup"],
        check=True, cwd=backup_dir,
    )

    result = subprocess.run(
        ["git", "push", "--force", "-u", "origin", "main"],
        capture_output=True, text=True, cwd=backup_dir,
    )
    if result.returncode != 0:
        log(f"Warning: initial push failed: {result.stderr.strip()}")
        log(f"Push manually: cd {backup_dir} && git push --force -u origin main")
    else:
        log(f"Initial push complete → github.com/{github_username}/{repo_name}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_init(ctx: Context) -> None:
    """Run the full project initialisation sequence."""
    log(f"Initialising Shreni for '{ctx.project_name}' at {ctx.repo_root}")

    # ── Phase 1: Machine prerequisites ───────────────────────────────────────
    log("Checking prerequisites...")
    _check_bd_installed()
    _check_claude_installed()
    _check_dolt_installed()
    _check_graphify_installed()
    github_username = _check_gh_installed()

    # ── Phase 2: Per-project setup ────────────────────────────────────────────
    prefix = _ensure_bd_initialized(ctx)
    _gitignore_beads(ctx)
    _configure_beads_backup(ctx)

    issues_repo = f"{prefix}-issues"
    _init_jsonl_backup_repo(ctx, github_username, issues_repo)

    # ── Backup cron (git push every 5 min) ───────────────────────────────────
    log_file = ctx.repo_root / ".claude" / "bd-backup.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    install_backup(ctx.repo_root, log_file)
    log(f"bd backup cron installed (every 5 min). Log → {log_file}")

    # ── Graphify knowledge graph ──────────────────────────────────────────────
    _run_graphify(ctx)

    # ── CLAUDE.md ─────────────────────────────────────────────────────────────
    if (ctx.repo_root / "CLAUDE.md").exists():
        log("CLAUDE.md exists — Silpi will update any missing sections.")
    else:
        log("CLAUDE.md not found — Silpi will create it now.")
    _silpi("Creating CLAUDE.md...")
    await silpi_agent.init_project(ctx)

    # ── Done ──────────────────────────────────────────────────────────────────
    log("━" * 50)
    log(f"Project '{ctx.project_name}' is ready.")
    log(f"  Issues backup: github.com/{github_username}/{issues_repo}")
    log(f"  Backup log: {log_file}")
    log(f"  Run: shreni run --repo {ctx.repo_root}")
    log("━" * 50)
