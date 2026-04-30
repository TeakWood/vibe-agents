"""Silpi — the implementer agent."""

import sys

from claude_agent_sdk import SdkPluginConfig

from ..context import Context
from ..plugins import resolve_plugin
from ..shell import log, run_cmd_output
from .runner import load_agent_prompt, run_agent


_MEMORIES_HEADER = (
    "## bd memories — durable rules from past investigations\n"
    "These were captured by prior `investigation` tasks. Treat them as binding"
    " constraints, not suggestions; they exist because the project already"
    " regressed on each rule at least once.\n\n"
)


def _bd_memories(ctx: Context) -> str:
    """Fetch `bd memories` for injection into Silpi's prompt.

    Returns an empty string when bd is unavailable or no memories are stored,
    so the prompt template can include this block unconditionally.
    """
    try:
        out = run_cmd_output(["bd", "memories"], ctx.repo_root)
    except Exception:
        return ""
    if not out or "no beads database" in out.lower() or "no memories" in out.lower():
        return ""
    return _MEMORIES_HEADER + out + "\n\n"


def _load_plugins() -> list[SdkPluginConfig]:
    plugin = resolve_plugin("claude-code-plugins", "frontend-design")
    if plugin:
        return [plugin]
    print(
        "WARNING: frontend-design plugin not found; "
        "run: claude plugin install frontend-design@claude-code-plugins",
        file=sys.stderr,
        flush=True,
    )
    return []


# Resolved once at import time so startup warns early if the plugin is missing.
_PLUGINS: list[SdkPluginConfig] = _load_plugins()


async def init_project(ctx: Context) -> None:
    """Create or update CLAUDE.md in the target repo with all critical project information."""
    await run_agent(
        load_agent_prompt("silpi", ctx),
        (
            f"You are Silpi, initialising the project context file for {ctx.project_name}.\n\n"

            f"## Instructions\n"
            f"Read the repository at {ctx.repo_root} and create or update CLAUDE.md at its root.\n\n"
            f"CLAUDE.md MUST contain the following sections (add any that are missing,"
            f" update any that are outdated):\n"
            f"1. **Project overview** — what the project does and its tech stack.\n"
            f"2. **Build command** — exact command(s) to compile / type-check the project.\n"
            f"3. **Test command** — exact command(s) to run the test suite.\n"
            f"4. **Lint / format commands** — any linters or formatters in use.\n"
            f"5. **Dev server** — how to start the local development server.\n"
            f"6. **Environment variables** — required env vars and where they come from"
            f" (e.g. .env.local).\n"
            f"7. **Key directories** — brief description of important folders"
            f" (src, tests, config, etc.).\n"
            f"8. **Coding conventions** — naming, file structure, import style, or anything"
            f" a developer must follow.\n"
            f"9. **Issue tracker rules** — include these rules verbatim:\n\n"
            f"   **Task labels:**\n"
            f"   > Three reserved labels are used by the Shreni agent system:\n"
            f"   > - `manual` — bug reported by a human:"
            f" `bd create \"<title>\" --type bug --labels manual`\n"
            f"   > - `parikshaka` — regression bug detected by the Parikshaka QA agent after"
            f" a task merge (never add this label manually)\n"
            f"   > - `e2e` — task to write missing e2e tests, created by Parikshaka and"
            f" implemented by Silpi (never add this label manually)\n"
            f"   > When creating a bug task manually always use `--labels manual` so it is"
            f" distinguishable from automated reports.\n\n"
            f"   **Task creation order:**\n"
            f"   > When creating a set of tasks manually, always create them in execution order —"
            f" blocking tasks first, then the tasks that depend on them.\n"
            f"   > Sthapathi picks up tasks in `ready` state. A task only becomes ready once all"
            f" its dependencies are complete. If you create tasks out of order without wiring up"
            f" dependencies, Sthapathi may attempt dependent tasks before their prerequisites are"
            f" done.\n"
            f"   > Use `--deps <id>` to declare a dependency when creating a task:\n"
            f"   > `bd create \"<title>\" --type feature --deps <blocking-task-id>`\n"
            f"   > Example — three tasks where each builds on the previous:\n"
            f"   > 1. `bd create \"Add database schema\" --type feature`  → returns T-1\n"
            f"   > 2. `bd create \"Build API endpoints\" --type feature --deps T-1`  → returns T-2\n"
            f"   > 3. `bd create \"Add frontend UI\" --type feature --deps T-2`  → returns T-3\n"
            f"   > This ensures Sthapathi implements T-1, then T-2, then T-3 in the correct"
            f" sequence.\n\n"
            f"Discover these by reading package.json / pyproject.toml / Makefile /"
            f" README.md / existing CLAUDE.md and any other config files present.\n"
            f"Do not invent information — only write what you can confirm from the repo.\n"
            f"When done, commit with the message: chore: initialise CLAUDE.md"
        ),
        ctx,
        agent_name="silpi",
        plugins=_PLUGINS,
    )


async def implement(task_id: str, task_context: str, branch: str, ctx: Context) -> None:
    """Implement a task from scratch."""
    await run_agent(
        load_agent_prompt("silpi", ctx),
        (
            f"You are Silpi, working on task {task_id} on branch '{branch}'.\n\n"
            f"{_bd_memories(ctx)}"
            f"## Task\n{task_context}\n\n"
            f"## Instructions\n"
            f"1. Read the task. If it involves any UI, frontend components, pages, or"
            f" visual design, invoke `/frontend-design` before writing any code so the"
            f" skill's design guidelines are active for this session.\n"
            f"2. Implement the task fully.\n"
            f"3. Write unit tests covering the new behaviour.\n"
            f"4. Run the project's quality gates (check CLAUDE.md for commands)"
            f" — all must pass before committing.\n"
            f"5. Build the project (check CLAUDE.md for the build command)"
            f" — the build MUST succeed with zero errors before proceeding.\n"
            f"6. Commit all changes using the format: {task_id}: <brief description>\n"
            f"7. When done, submit for review:\n"
            f"   bd set-state {task_id} review=ready-for-review"
            f" --reason 'Implementation complete' --json"
        ),
        ctx,
        agent_name="silpi",
        plugins=_PLUGINS,
    )


async def address_feedback(
    task_id: str,
    task_context: str,
    branch: str,
    round_num: int,
    review_comments: str,
    ctx: Context,
) -> None:
    """Address review feedback and resubmit."""
    await run_agent(
        load_agent_prompt("silpi", ctx),
        (
            f"You are Silpi, addressing review feedback on task {task_id}"
            f" on branch '{branch}'.\n\n"
            f"{_bd_memories(ctx)}"
            f"## Task\n{task_context}\n\n"
            f"## Review comments — fix ALL blocking issues\n{review_comments}\n\n"
            f"## Instructions\n"
            f"1. Fix every blocking issue in the review comments.\n"
            f"2. Run the project's quality gates (check CLAUDE.md for commands)"
            f" — all must pass.\n"
            f"3. Build the project (check CLAUDE.md for the build command)"
            f" — the build MUST succeed with zero errors before proceeding.\n"
            f"4. Commit using the format:"
            f" {task_id}: Address review feedback (round {round_num})\n"
            f"5. Resubmit for review:\n"
            f"   bd set-state {task_id} review=ready-for-review"
            f" --reason 'Changes addressed' --json"
        ),
        ctx,
        agent_name="silpi",
        plugins=_PLUGINS,
    )


async def breakdown_epic(
    epic_id: str,
    epic_context: str,
    epic_comments: str,
    ctx: Context,
) -> None:
    """Decompose an approved epic into feature tasks."""
    await run_agent(
        load_agent_prompt("silpi", ctx),
        (
            f"You are Silpi, breaking down approved epic {epic_id} into feature tasks.\n\n"
            f"## Epic\n{epic_context}\n\n"
            f"## Design proposal (from comments)\n{epic_comments}\n\n"
            f"## Instructions\n"
            f"Follow the 'Epic Breakdown' section in your AGENTS.md exactly.\n"
            f"The epic ID is {epic_id}.\n"
            f"When all tasks are created, signal completion:\n"
            f"  bd set-state {epic_id} breakdown=complete"
            f" --reason 'Feature tasks created' --json"
        ),
        ctx,
        agent_name="silpi",
        plugins=_PLUGINS,
    )
