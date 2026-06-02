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
from .bd import (
    active_parent_ids,
    breakdown_state,
    claim_task,
    close_task,
    ensure_initialized,
    epic_ready_to_close,
    ready_tasks,
    set_state,
    task_status,
    tasks_with_label,
)
from .context import Context
from .observability import emit_event, span
from . import phoenix as phoenix_otel
from .git import (
    branch_exists,
    branch_has_commits,
    checkout,
    create_branch,
    current_branch,
    pull,
    stash_pop,
    stash_save,
    task_merged_to_main,
)
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

# Toggle to re-enable Parikshaka. When False, merged tasks are still appended
# to the persistent queue file so they can be processed later, but the
# background worker is not started.
_PARIKSHAKA_ENABLED = False

_parikshaka = make_logger("Parikshaka")

# Epics the user is reviewing personally — they'll close (or approve) these
# independently. Silpi must never break them down while this label is present.
_USER_REVIEW_LABEL = "review:user-review"


def _user_review_epic_ids(ctx: Context) -> set[str]:
    """IDs of open epics carrying `review:user-review`.

    These are under the user's own review and will be closed by the user
    independently — the orchestrator identifies them so Silpi skips them
    rather than breaking them down.
    """
    return {
        t["id"]
        for t in tasks_with_label(_USER_REVIEW_LABEL, ctx)
        if t.get("issue_type") == "epic"
    }


async def _parikshaka_worker(
    recv: anyio.abc.ObjectReceiveStream,
    ctx: Context,
) -> None:
    """Background worker: drains the Parikshaka queue one task at a time."""
    async with recv:
        async for task_id, task_title in recv:
            _parikshaka(f"Quality check for {task_id} ('{task_title}')...")
            with span(
                ctx,
                "parikshaka.background_check",
                task_id=task_id,
                attrs={"title": task_title},
            ):
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
        if resume_epic["id"] in _user_review_epic_ids(ctx):
            log(f"Epic {resume_epic['id']} is under user review — skipping breakdown; "
                f"leaving it for you to close.")
            clear_epic(ctx)
        elif breakdown_state(resume_epic["id"], ctx) != "complete":
            log(f"Resuming epic breakdown for {resume_epic['id']}...")
            await run_epic_breakdown(resume_epic, ctx)
        else:
            clear_epic(ctx)

    resume_task, resume_branch, resume_state, resume_round = find_resumable_task(ctx)
    if resume_task:
        log(f"Resuming task {resume_task['id']} (state={resume_state}, round={resume_round}).")
        cur = current_branch(ctx)
        if cur != resume_branch:
            stashed = stash_save("shreni: pre-resume checkout", ctx)
            if branch_exists(resume_branch, ctx):
                checkout(resume_branch, ctx)
            else:
                checkout("main", ctx)
                pull(ctx)
                create_branch(resume_branch, ctx)
            if stashed:
                try:
                    stash_pop(ctx)
                except Exception as e:
                    log(f"Warning: could not restore pre-resume stash automatically ({e}). Run `git stash pop` to recover.")
        merged = await run_task_loop(resume_task, resume_branch, resume_round, resume_state, ctx)
        if merged:
            enqueue_parikshaka(merged, ctx)
            if _PARIKSHAKA_ENABLED:
                await parikshaka_send.send((merged["id"], merged.get("title", "")))

    # ── Main loop ─────────────────────────────────────────────────────────────
    # Epics already announced this run, so we report each only once instead of
    # on every idle iteration.
    signoff_reported: set[str] = set()
    user_review_reported: set[str] = set()

    while True:
        # 0. Close epics whose breakdown finished and whose every child task is
        # now closed. The epic stays open through breakdown + the child task
        # loop; once the last child merges, nothing else closes it, so we do it
        # here. Forced close because the epic's own (discovered-from) dependents
        # are already closed, making bd's open-dependency guard moot.
        for epic in tasks_with_label("breakdown:complete", ctx):
            if epic.get("issue_type") != "epic":
                continue
            if epic_ready_to_close(epic["id"], ctx):
                log(f"Epic {epic['id']} ('{epic['title']}') — all child tasks complete; closing.")
                close_task(epic["id"], "All child tasks complete", ctx, force=True)

        # 0a. Epics the user is reviewing personally — skip them entirely.
        # They'll be closed (or approved) by the user independently, so Silpi
        # must never break them down. We only identify them here; the actual
        # skip is enforced by excluding their IDs from the breakdown set below.
        user_review_ids = _user_review_epic_ids(ctx)
        new_user_review = user_review_ids - user_review_reported
        if new_user_review:
            for t in tasks_with_label(_USER_REVIEW_LABEL, ctx):
                if t["id"] in new_user_review:
                    log(f"Epic {t['id']} ('{t['title']}') is under user review — "
                        f"skipping; you'll close it independently.")
            user_review_reported |= new_user_review

        # 0b. Epics awaiting author sign-off — report once, then keep working.
        # These no longer halt the orchestrator; other ready tasks proceed while
        # the epics wait for your decision.
        pending_epics = [
            t for t in tasks_with_label("review:viharapala-approved", ctx)
            if t.get("issue_type") == "epic"
        ]
        new_pending = [t for t in pending_epics if t["id"] not in signoff_reported]
        if new_pending:
            log("━" * 40)
            log(f"AUTHOR REVIEW REQUIRED — {len(new_pending)} epic(s) awaiting your sign-off.")
            log("━" * 40)
            for t in new_pending:
                print(f"  Epic {t['id']}: {t['title']}")
            log("")
            log("For each epic:")
            log("  Review:   bd show <id>  &&  bd comments <id>")
            log("  Approve:  bd set-state <id> review=approved --reason 'Design approved' --json")
            log("  Reject:   bd set-state <id> review=changes-required --reason '<why>' --json")
            log("  Take it:  bd set-state <id> review=user-review --reason 'I'll close this myself' --json")
            log("Continuing with other ready work in the meantime.")
            signoff_reported |= {t["id"] for t in new_pending}

        # 0c. Break down author-approved epics — but never those under user review.
        approved_epics = [
            t for t in tasks_with_label("review:approved", ctx)
            if t.get("issue_type") == "epic"
            and t["id"] not in user_review_ids
            and breakdown_state(t["id"], ctx) != "complete"
        ]
        if approved_epics:
            for epic in approved_epics:
                await run_epic_breakdown(epic, ctx)
            continue

        # 0d. Merge tasks that Viharapala already approved (not yet closed)
        # Filter out tasks already marked status=blocked — they were released
        # by a prior iteration (e.g. stale approval on an empty branch) and
        # are awaiting human attention; re-entering would loop forever.
        approved_tasks = [
            t for t in tasks_with_label("review:approved", ctx)
            if t.get("issue_type") != "epic" and task_status(t["id"], ctx) != "blocked"
        ]
        if approved_tasks:
            for task in approved_tasks:
                task_id = task["id"]
                branch = f"feature/{slugify(task['title'])}"

                # Already merged — bd close must have failed previously. Close
                # cleanly without re-entering the implement/review/merge loop.
                # Force past bd's open-dependency guard: the work is on main, so
                # the block is moot. If even a forced close fails, the task would
                # otherwise keep the review:approved label and re-enter this path
                # forever (a busy loop), so mark it blocked for human attention.
                if task_merged_to_main(task_id, ctx):
                    log(f"Task {task_id} already merged to main — closing.")
                    if not close_task(task_id, "Already merged to main", ctx, force=True):
                        set_state(
                            task_id,
                            "status=blocked",
                            "Merged to main but bd close failed — needs human attention",
                            ctx,
                        )
                    continue

                # Approved but the branch has no commits ahead of main and the
                # task is not in main. This is a confused state (stale
                # approval, abandoned work, or a human-only task wrongly
                # marked approved). Block for human review rather than
                # dispatching to merge — task_loop would re-implement and the
                # stale 'approved' label would trap us in a Silpi/Viharapala
                # loop on every subsequent run.
                if not branch_has_commits(branch, ctx):
                    log(
                        f"Task {task_id} has label review:approved but branch "
                        f"{branch} has no commits ahead of main — marking "
                        f"status=blocked for human review."
                    )
                    set_state(
                        task_id,
                        "status=blocked",
                        "Stale approval: branch is empty and task not in main",
                        ctx,
                    )
                    continue

                log(f"Picking up approved task {task_id}: {task['title']}")
                emit_event(
                    ctx,
                    "task_picked_up",
                    task_id=task_id,
                    attrs={"title": task["title"], "branch": branch, "via": "approved-resume"},
                )
                save_task(task, branch, ctx)
                merged = await run_task_loop(task, branch, 1, "merge", ctx)
                if merged:
                    enqueue_parikshaka(merged, ctx)
                    if _PARIKSHAKA_ENABLED:
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
        emit_event(
            ctx,
            "task_picked_up",
            task_id=task_id,
            attrs={"title": task["title"], "branch": branch, "via": "ready-queue"},
        )
        save_task(task, branch, ctx)

        stashed = stash_save(f"shreni: pre-task {task_id}", ctx)
        checkout("main", ctx)
        pull(ctx)
        create_branch(branch, ctx)
        if stashed:
            try:
                stash_pop(ctx)
            except Exception as e:
                log(f"Warning: could not restore pre-task stash automatically ({e}). Run `git stash pop` to recover.")
        log(f"Branch: {branch}")

        # 3. Run the implement → review → merge loop
        merged = await run_task_loop(task, branch, 1, "silpi_implement", ctx)
        if merged:
            enqueue_parikshaka(merged, ctx)
            if _PARIKSHAKA_ENABLED:
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
            "  init     Set up a new project (bd init, DoltHub backup, CLAUDE.md)\n"
            "  run      Run the orchestrator against the project backlog (default)\n"
            "  logs     Inspect per-task spans/events under ~/.shreni/projects/<slug>/\n"
            "  phoenix  Start / probe / open the Arize Phoenix trace viewer\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    for cmd in ("init", "run"):
        sub = subparsers.add_parser(cmd)
        sub.add_argument("--repo", required=True, type=Path, help="Path to the git repository")
        sub.add_argument("--project-name", default=None, help="Project name (defaults to repo dir name)")

    logs_sub = subparsers.add_parser("logs", help="Inspect per-task spans/events.")
    logs_sub.add_argument("--repo", required=True, type=Path, help="Path to the git repository")
    logs_sub.add_argument("--project-name", default=None, help="Project name (defaults to repo dir name)")
    logs_sub.add_argument("--task", default=None, help="Task id to dump (omit to list tasks)")
    logs_sub.add_argument("--raw", action="store_true", help="Print raw JSONL instead of a formatted timeline")
    logs_sub.add_argument(
        "--perfetto", type=Path, default=None, metavar="OUT.json",
        help="Export a Chrome Trace Event file viewable at https://ui.perfetto.dev",
    )

    # Phoenix sub-subcommands: shreni phoenix {start,status,open}
    phx_sub = subparsers.add_parser("phoenix", help="Manage the Arize Phoenix trace viewer.")
    phx_sub.add_argument("--repo", required=True, type=Path, help="Path to the git repository")
    phx_sub.add_argument("--project-name", default=None, help="Project name (defaults to repo dir name)")
    phx_actions = phx_sub.add_subparsers(dest="phoenix_action")
    phx_start = phx_actions.add_parser("start", help="Run `phoenix serve` in the foreground.")
    phx_start.add_argument("--port", type=int, default=6006)
    phx_start.add_argument("--host", default="127.0.0.1")
    phx_actions.add_parser("status", help="Probe the Phoenix endpoint.")
    phx_actions.add_parser("open", help="Open the project page in your browser.")

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

    if command == "logs":
        perfetto_out = getattr(args, "perfetto", None)
        if perfetto_out is not None:
            from .cli.perfetto import export as export_perfetto
            sys.exit(export_perfetto(ctx, task=getattr(args, "task", None), output=perfetto_out))
        from .cli.logs import run_logs
        sys.exit(run_logs(ctx, task=getattr(args, "task", None), raw=getattr(args, "raw", False)))

    if command == "phoenix":
        from .cli import phoenix_cmd
        action = getattr(args, "phoenix_action", None) or "status"
        if action == "start":
            sys.exit(phoenix_cmd.cmd_start(port=args.port, host=args.host))
        if action == "status":
            sys.exit(phoenix_cmd.cmd_status(ctx))
        if action == "open":
            sys.exit(phoenix_cmd.cmd_open(ctx))
        print(f"Unknown phoenix action: {action}", file=sys.stderr)
        sys.exit(1)

    # ── run ───────────────────────────────────────────────────────────────────
    log(f"Sthapathi started for '{ctx.project_name}' at {ctx.repo_root}")
    if _PARIKSHAKA_ENABLED:
        log("Agents: Silpi (implement) + Viharapala (review) + Parikshaka (QA, background)")
    else:
        log("Agents: Silpi (implement) + Viharapala (review) — Parikshaka disabled")
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
    if _PARIKSHAKA_ENABLED:
        pending = load_parikshaka_queue(ctx)
        if pending:
            log(f"Replaying {len(pending)} task(s) left in Parikshaka queue from previous run.")
            for entry in pending:
                await send_channel.send((entry["id"], entry["title"]))

    # ── Initialise Phoenix sidechannel (no-op if disabled / unreachable) ─────
    phoenix_otel.setup(ctx)

    # ── Run main loop and Parikshaka worker in parallel ───────────────────────
    try:
        with span(
            ctx,
            "session",
            attrs={
                "project": ctx.project_name,
                "repo_root": str(ctx.repo_root),
                "parikshaka_enabled": _PARIKSHAKA_ENABLED,
            },
        ):
            async with anyio.create_task_group() as tg:
                if _PARIKSHAKA_ENABLED:
                    tg.start_soon(_parikshaka_worker, recv_channel, ctx)
                try:
                    await _main_loop(send_channel, ctx)
                finally:
                    await send_channel.aclose()
    finally:
        phoenix_otel.shutdown()


def cli() -> None:
    anyio.run(main)
