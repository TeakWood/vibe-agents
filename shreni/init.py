"""shreni init — set up a new project for autonomous development.

Two phases:

  Phase 1 — Machine prerequisites (one-time per machine)
    Checks dolt is installed, credentials exist, and are verified with DoltHub.
    If anything is missing, prints the exact steps needed and exits.
    Re-run `shreni init` after completing them.

  Phase 2 — Per-project setup
    bd init, beads backup config, DoltHub remote, initial push,
    backup cron, CLAUDE.md.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import anyio

from .agents import silpi as silpi_agent
from .backup import install as install_backup, is_installed as backup_installed
from .context import Context
from .shell import log, make_logger

_silpi = make_logger("Silpi")


# ── Phase 1: Machine prerequisites ────────────────────────────────────────────

def _check_machine_prerequisites() -> str:
    """Check dolt install, credentials, and DoltHub verification.

    Returns the DoltHub username on success.
    Prints what the user needs to do and exits if anything is missing.
    """
    missing: list[str] = []

    # 1. dolt CLI installed?
    if shutil.which("dolt") is None:
        print("\n  ✗ dolt — not installed")
        print("\n" + "━" * 56)
        print("  Machine setup required — complete these steps, then")
        print("  re-run:  shreni init --repo <path>")
        print("━" * 56)
        print("\n  Step 1 — Install dolt:")
        print("    brew install dolt\n")
        sys.exit(1)

    print("  ✓ dolt installed")

    # 2. Dolt credentials exist?
    creds = subprocess.run(["dolt", "creds", "ls"], capture_output=True, text=True)
    if creds.returncode != 0 or not creds.stdout.strip():
        missing.append("creds")

    # 3. Credentials verified with DoltHub?
    dolthub_username = None
    if not missing:
        check = subprocess.run(
            ["dolt", "creds", "check", "--endpoint", "doltremoteapi.dolthub.com:443"],
            capture_output=True, text=True,
        )
        output = check.stdout + check.stderr
        for line in output.splitlines():
            if line.strip().lower().startswith("user:"):
                dolthub_username = line.split(":", 1)[1].strip()
                break
        if not dolthub_username:
            missing.append("verified")

    if missing:
        print("\n  ✗ DoltHub credentials not set up\n")
        print("━" * 56)
        print("  Machine setup required — complete these steps, then")
        print("  re-run:  shreni init --repo <path>")
        print("━" * 56)
        if "creds" in missing:
            print("\n  Step 2 — Generate DoltHub credentials:")
            print("    dolt creds new\n")
            print("  Step 3 — Add the public key to your DoltHub account:")
            print("    dolt creds ls   ← copy this output")
            print("    → https://dolthub.com/settings/credentials")
            print("      paste the key and save\n")
        print("  Step 4 — Verify credentials (note the 'User:' value):")
        print("    dolt creds check --endpoint doltremoteapi.dolthub.com:443\n")
        sys.exit(1)

    print(f"  ✓ DoltHub credentials verified (User: {dolthub_username})")
    return dolthub_username


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


# ── Phase 2: Per-project setup ────────────────────────────────────────────────

def _bd_prefix(project_name: str) -> str:
    """Derive the bd issue prefix from the project name (lowercase slug)."""
    return re.sub(r"[^a-z0-9]", "-", project_name.lower()).strip("-")


def _ensure_bd_initialized(ctx: Context) -> str:
    """Run bd init if .beads/ doesn't exist. Returns the prefix used."""
    prefix = _bd_prefix(ctx.project_name)
    if (ctx.repo_root / ".beads").exists():
        log("bd already initialized — skipping bd init.")
        return prefix
    log(f"Initializing bd with prefix '{prefix}'...")
    subprocess.run(["bd", "init", "--prefix", prefix], check=True, cwd=ctx.repo_root)
    log("bd initialized.")
    return prefix


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


def _add_dolthub_remote(ctx: Context, dolthub_username: str, db_name: str) -> None:
    """Register the DoltHub remote via bd dolt remote add."""
    remote_url = f"https://doltremoteapi.dolthub.com/{dolthub_username}/{db_name}"
    log(f"Adding DoltHub remote: {remote_url}")
    result = subprocess.run(
        ["bd", "dolt", "remote", "add", "origin", remote_url],
        capture_output=True, text=True, cwd=ctx.repo_root,
    )
    if result.returncode != 0:
        log(f"Warning: bd dolt remote add failed: {result.stderr.strip()}")
        log("You may need to add the remote manually — see the DoltHub setup instructions.")
    else:
        log("Remote added.")


def _initial_push(ctx: Context, prefix: str) -> None:
    """Push to DoltHub using direct dolt CLI (bypasses bd dolt push port bug)."""
    dolt_path = ctx.repo_root / ".beads" / "embeddeddolt" / prefix
    if not dolt_path.exists():
        log(f"Warning: dolt db path not found at {dolt_path} — skipping initial push.")
        return
    log(f"Pushing to DoltHub...")
    result = subprocess.run(
        ["dolt", "push", "origin", "main"],
        capture_output=True, text=True, cwd=dolt_path,
    )
    if result.returncode != 0:
        log(f"Warning: initial push failed: {result.stderr.strip()}")
        log("Ensure the DoltHub repo exists, then push manually:")
        log(f"  cd {dolt_path} && dolt push origin main")
    else:
        log("Initial push to DoltHub complete.")


def _print_dolthub_repo_instructions(ctx: Context, dolthub_username: str, db_name: str) -> None:
    prefix = _bd_prefix(ctx.project_name)
    dolt_path = ctx.repo_root / ".beads" / "embeddeddolt" / prefix
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ACTION REQUIRED — Create the DoltHub repository
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Before continuing, create the DoltHub database:

  Step 5 → https://dolthub.com/repositories/new
           Name it exactly:  {db_name}

  Then press Enter to continue...
""", flush=True)
    input()


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_init(ctx: Context) -> None:
    """Run the full project initialisation sequence."""
    log(f"Initialising Shreni for '{ctx.project_name}' at {ctx.repo_root}")

    # ── Phase 1: Machine prerequisites ───────────────────────────────────────
    log("Checking prerequisites...")
    _check_bd_installed()
    _check_claude_installed()
    dolthub_username = _check_machine_prerequisites()

    # ── Phase 2: Per-project setup ────────────────────────────────────────────
    prefix = _ensure_bd_initialized(ctx)
    _configure_beads_backup(ctx)

    # Prompt user to create the DoltHub repo before we try to push
    db_name = f"{prefix}-beads"
    _print_dolthub_repo_instructions(ctx, dolthub_username, db_name)

    _add_dolthub_remote(ctx, dolthub_username, db_name)
    _initial_push(ctx, prefix)

    # ── Backup cron (dolt push every 5 min) ──────────────────────────────────
    log_file = ctx.repo_root / ".claude" / "bd-backup.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if backup_installed(ctx.repo_root):
        log("bd backup cron already installed — skipping.")
    else:
        install_backup(ctx.repo_root, log_file)
        log(f"bd backup cron installed (every 5 min). Log → {log_file}")

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
    log(f"  DoltHub: https://www.dolthub.com/{dolthub_username}/{db_name}")
    log(f"  Backup log: {log_file}")
    log(f"  Run: shreni run --repo {ctx.repo_root}")
    log("━" * 50)
