"""Base agent runner shared by all agents."""

from contextlib import ExitStack
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SdkPluginConfig,
    TextBlock,
    ToolUseBlock,
    query,
)

from ..context import Context
from ..observability import emit_event, span

_TRUNCATE = 120


def _tool_status(block: ToolUseBlock) -> str:
    """Return a single-line status string for a tool call."""
    name = block.name
    inp = block.input or {}
    if name == "Bash":
        detail = inp.get("command", "")
    elif name in ("Read", "Write", "Edit", "NotebookEdit"):
        detail = inp.get("file_path", "")
    elif name == "Agent":
        detail = inp.get("description", "")
    else:
        detail = next(iter(inp.values()), "") if inp else ""
    detail = str(detail).replace("\n", " ")
    if len(detail) > _TRUNCATE:
        detail = detail[:_TRUNCATE] + "…"
    return f"  ⚙ {name}: {detail}\n" if detail else f"  ⚙ {name}\n"


def _tool_attrs(block: ToolUseBlock) -> dict:
    """Pull the salient input field (command / file_path / description) for spans."""
    name = block.name
    inp = block.input or {}
    attrs: dict = {"tool": name}
    if name == "Bash" and inp.get("command"):
        attrs["command"] = str(inp["command"])[:512]
    elif name in ("Read", "Write", "Edit", "NotebookEdit") and inp.get("file_path"):
        attrs["file_path"] = str(inp["file_path"])
    elif name == "Agent" and inp.get("description"):
        attrs["description"] = str(inp["description"])[:256]
    return attrs


async def run_agent(
    system_prompt: str,
    prompt: str,
    ctx: Context,
    *,
    agent_name: str = "agent",
    task_id: str | None = None,
    span_name: str | None = None,
    plugins: list[SdkPluginConfig] | None = None,
) -> None:
    """Run a Claude agent session, streaming output to per-task and aggregate logs.

    Per-task log path:
        ~/.shreni/projects/<slug>/tasks/<task_id>/<agent_name>.log
    Aggregate log path (always written, used by tmux pane tailing):
        ~/.shreni/projects/<slug>/<agent_name>.log

    Emits a span around the whole invocation and one ``tool_call`` event per
    tool use, so a task's full timeline can be reconstructed from
    ``spans.jsonl`` without grepping through interleaved log files.
    """
    aggregate_log = ctx.agent_log_file(agent_name)
    aggregate_log.parent.mkdir(parents=True, exist_ok=True)

    log_paths: list[Path] = [aggregate_log]
    if task_id:
        per_task_log = ctx.agent_log_file(agent_name, task_id=task_id)
        per_task_log.parent.mkdir(parents=True, exist_ok=True)
        log_paths.append(per_task_log)

    def _write_all(text: str) -> None:
        for handle in handles:
            handle.write(text)
            handle.flush()

    span_label = span_name or f"{agent_name}.run"
    span_attrs = {"prompt_chars": len(prompt)}

    with ExitStack() as stack:
        handles = [stack.enter_context(p.open("a")) for p in log_paths]
        stack.enter_context(
            span(ctx, span_label, agent=agent_name, task_id=task_id, attrs=span_attrs)
        )

        tool_calls = 0
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                system_prompt=system_prompt,
                permission_mode="bypassPermissions",
                cwd=str(ctx.repo_root),
                plugins=plugins or [],
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        _write_all(block.text)
                    elif isinstance(block, ToolUseBlock):
                        _write_all(_tool_status(block))
                        tool_calls += 1
                        emit_event(
                            ctx,
                            "tool_call",
                            agent=agent_name,
                            task_id=task_id,
                            attrs=_tool_attrs(block),
                        )
            elif isinstance(message, ResultMessage):
                if message.result:
                    _write_all(message.result + "\n")

        emit_event(
            ctx,
            "agent_finished",
            agent=agent_name,
            task_id=task_id,
            attrs={"tool_calls": tool_calls},
        )


def load_agent_prompt(agent_name: str, ctx: Context) -> str:
    """Load SOUL.md + AGENTS.md for an agent, interpolating {PROJECT_NAME} and {REPO_ROOT}."""
    agent_dir = ctx.agents_dir / agent_name
    soul = (agent_dir / "SOUL.md").read_text()
    instructions = (agent_dir / "AGENTS.md").read_text()
    combined = f"{soul}\n\n---\n\n{instructions}"
    return (
        combined
        .replace("{PROJECT_NAME}", ctx.project_name)
        .replace("{REPO_ROOT}", str(ctx.repo_root))
    )
