"""Sthapathi (स्थपति) — master orchestrator and CLI entry point.

Usage:
    shreni init --repo /path/to/repo [--project-name MyProject]
    shreni run  --repo /path/to/repo [--project-name MyProject]

Run from a plain terminal OUTSIDE any Claude Code session.
"""

import argparse
import os
import sys
from pathlib import Path

import anyio

from .agents import parikshaka as parikshaka_agent
from .init import run_init
from .bd import active_parent_ids, breakdown_state, claim_task, ensure_initialized, ready_tasks, tasks_with_label
from .context import Context
from .git import branch_exists, checkout, create_branch, current_branch, pull
from .shell import log, make_logger, slugify
from .state import (
    clear_epic,
    dequeue_parikshaka,
    enqueue_parikshaka,
    load_epic,
    load_parikshaka_queue,
    save_task,
)
from .tmux import start_log_session
from .workflow.epic import run_epic_breakdown
from .workflow.resume import find_resumable_task
from .workflow.task_loop import run_task_loop

# Project root: the directory containing silpi/, viharapala/, parikshaka/, run.py
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()

_parikshaka = make_logger("Parikshaka")


async def _parikshaka_worker(
    recv: anyio.abc.ObjectReceiveStream,
    ctx: Context,
) -> None:
    """Background worker: drains the Parikshaka queue one task at a time."""
    async with recv:
        async for task_id, task_title in recv:
            _parikshaka(f"Quality check for {task_id} ('{task_title}')...")
            await parikshaka_agent.quality_check(task_id, task_title, ctx)
            dequeue_parikshaka(task_id, ctx)
            _parikshaka(f"Quality check complete for {task_id}.")


async def _main_loop(
    parikshaka_send: anyio.abc.ObjectSendStream,
    ctx: Context,
) -> None:
    """Main task-picking loop. Sends completed tasks to the Parikshaka queue."""
    # ── Crash recovery ────────────────────────────────────────────────────────
    resume_epic = load_epic(ctx)
    if resume_epic:
        if breakdown_state(resume_epic["id"], ctx) != "complete":
            log(f"Resuming epic breakdown for {resume_epic['id']}...")
            await run_epic_breakdown(resume_epic, ctx)
        else:
            clear_epic(ctx)

    resume_task, resume_branch, resume_state, resume_round = find_resumable_task(ctx)
    if resume_task:
        log(f"Resuming task {resume_task['id']} (state={resume_state}, round={resume_round}).")
        cur = current_branch(ctx)
        if cur != resume_branch:
            if branch_exists(resume_branch, ctx):
                checkout(resume_branch, ctx)
            else:
                checkout("main", ctx)
                pull(ctx)
                create_branch(resume_branch, ctx)
        merged = await run_task_loop(resume_task, resume_branch, resume_round, resume_state, ctx)
        if merged:
            enqueue_parikshaka(merged, ctx)
            await parikshaka_send.send((merged["id"], merged.get("title", "")))

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        # 0a. Epics awaiting author sign-off — pause and prompt the user
        pending_epics = [
            t for t in tasks_with_label("review:viharapala-approved", ctx)
            if t.get("type") == "epic"
        ]
        if pending_epics:
            log("━" * 40)
            log(f"AUTHOR REVIEW REQUIRED — {len(pending_epics)} epic(s) awaiting your sign-off.")
            log("━" * 40)
            for t in pending_epics:
                print(f"  Epic {t['id']}: {t['title']}")
            log("")
            log("For each epic:")
            log("  Review:   bd show <id>  &&  bd comments <id>")
            log("  Approve:  bd set-state <id> review=approved --reason 'Design approved' --json")
            log("  Reject:   bd set-state <id> review=changes-required --reason '<why>' --json")
            log(f"\nRe-run: python run.py --repo {ctx.repo_root}")
            sys.exit(0)

        # 0b. Break down author-approved epics
        approved_epics = [
            t for t in tasks_with_label("review:approved", ctx)
            if t.get("type") == "epic" and breakdown_state(t["id"], ctx) != "complete"
        ]
        if approved_epics:
            for epic in approved_epics:
                await run_epic_breakdown(epic, ctx)
            continue

        # 0c. Merge tasks that Viharapala already approved (not yet closed)
        approved_tasks = [
            t for t in tasks_with_label("review:approved", ctx)
            if t.get("type") != "epic"
        ]
        if approved_tasks:
            for task in approved_tasks:
                branch = f"feature/{slugify(task['title'])}"
                log(f"Picking up approved task {task['id']}: {task['title']}")
                save_task(task, branch, ctx)
                merged = await run_task_loop(task, branch, 1, "merge", ctx)
                if merged:
                    enqueue_parikshaka(merged, ctx)
                    await parikshaka_send.send((merged["id"], merged.get("title", "")))
            continue

        # 1. Pick the next ready task — prefer tasks sharing a parent with in-progress work
        tasks = ready_tasks(ctx)
        if not tasks:
            log(f"No tasks ready. Sleeping {ctx.idle_interval}s...")
            await anyio.sleep(ctx.idle_interval)
            continue

        active_parents = active_parent_ids(ctx)
        related_tasks = [t for t in tasks if t.get("parent") in active_parents]
        task = related_tasks[0] if related_tasks else tasks[0]
        if related_tasks:
            log(f"Prioritising task from active group {task.get('parent')}.")
        task_id: str = task["id"]
        branch = f"feature/{slugify(task['title'])}"

        log("━" * 40)
        log(f"Task {task_id}: {task['title']}")
        log("━" * 40)

        # 2. Claim and create feature branch
        claim_task(task_id, ctx)
        log(f"Claimed {task_id}.")
        save_task(task, branch, ctx)

        checkout("main", ctx)
        pull(ctx)
        create_branch(branch, ctx)
        log(f"Branch: {branch}")

        # 3. Run the implement → review → merge loop
        merged = await run_task_loop(task, branch, 1, "silpi_implement", ctx)
        if merged:
            enqueue_parikshaka(merged, ctx)
            await parikshaka_send.send((merged["id"], merged.get("title", "")))


async def main() -> None:
    # ── Guard: must not run inside a Claude Code session ──────────────────────
    if os.environ.get("CLAUDECODE"):
        print(
            "ERROR: CLAUDECODE is set — run outside a Claude Code session.\n"
            f"Open a plain terminal and run: python run.py --repo /path/to/repo",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── CLI args ──────────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Sthapathi — autonomous development orchestrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  init  Set up a new project (bd init, DoltHub backup, CLAUDE.md)\n"
            "  run   Run the orchestrator against the project backlog (default)\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    for cmd in ("init", "run"):
        sub = subparsers.add_parser(cmd)
        sub.add_argument("--repo", required=True, type=Path, help="Path to the git repository")
        sub.add_argument("--project-name", default=None, help="Project name (defaults to repo dir name)")

    # Back-compat: shreni --repo ... (no subcommand) → run
    parser.add_argument("--repo", nargs="?", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--project-name", nargs="?", default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Resolve repo and project name regardless of subcommand vs legacy form
    repo_arg = args.repo
    project_name_arg = args.project_name
    command = args.command or "run"

    if repo_arg is None:
        parser.print_help()
        sys.exit(1)

    repo_root = repo_arg.resolve()
    if not repo_root.exists():
        print(f"ERROR: Repository does not exist: {repo_root}", file=sys.stderr)
        sys.exit(1)
    if not (repo_root / ".git").exists():
        print(f"ERROR: Not a git repository: {repo_root}", file=sys.stderr)
        sys.exit(1)

    ctx = Context(
        repo_root=repo_root,
        project_name=project_name_arg or repo_root.name,
        agents_dir=_PROJECT_ROOT,
    )

    # ── Route to subcommand ───────────────────────────────────────────────────
    if command == "init":
        await run_init(ctx)
        return

    # ── run ───────────────────────────────────────────────────────────────────
    log(f"Sthapathi started for '{ctx.project_name}' at {ctx.repo_root}")
    log("Agents: Silpi (implement) + Viharapala (review) + Parikshaka (QA, background)")
    start_log_session(ctx)

    ensure_initialized(ctx)

    # ── Guard: project must be initialised before running ────────────────────
    if not (ctx.repo_root / "CLAUDE.md").exists():
        print(
            f"\nERROR: CLAUDE.md not found in {ctx.repo_root}\n"
            f"Run project initialisation first:\n"
            f"  shreni init --repo {ctx.repo_root}\n",
            file=sys.stderr,
        )
        sys.exit(1)
    log("CLAUDE.md found.")

    # ── Replay any tasks left in the persistent queue from a previous run ─────
    send_channel, recv_channel = anyio.create_memory_object_stream(max_buffer_size=1000)
    pending = load_parikshaka_queue(ctx)
    if pending:
        log(f"Replaying {len(pending)} task(s) left in Parikshaka queue from previous run.")
        for entry in pending:
            await send_channel.send((entry["id"], entry["title"]))

    # ── Run main loop and Parikshaka worker in parallel ───────────────────────
    async with anyio.create_task_group() as tg:
        tg.start_soon(_parikshaka_worker, recv_channel, ctx)
        try:
            await _main_loop(send_channel, ctx)
        finally:
            await send_channel.aclose()


def cli() -> None:
    anyio.run(main)
