"""Base agent runner shared by all agents."""

from collections import deque
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
from ..observability import emit_event, set_current_span_attribute, span
from ..shell import log

_TRUNCATE = 120

# Phoenix renders `input.value` / `output.value` directly in the span detail
# pane. We cap them so a runaway agent log does not bloat span attributes,
# but keep both ends with an ellipsis so the most-recent output is preserved
# alongside the original prompt/start of the response.
_OUTPUT_CHAR_LIMIT = 16_000


def _truncate_for_span(text: str, limit: int = _OUTPUT_CHAR_LIMIT) -> str:
    if len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head
    return f"{text[:head]}\n... [{len(text) - limit} chars truncated] ...\n{text[-tail:]}"


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
    span_attrs = {
        "prompt_chars": len(prompt),
        "input.value": _truncate_for_span(prompt),
        "input.mime_type": "text/plain",
    }

    with ExitStack() as stack:
        handles = [stack.enter_context(p.open("a")) for p in log_paths]
        stack.enter_context(
            span(ctx, span_label, agent=agent_name, task_id=task_id, attrs=span_attrs)
        )

        tool_calls = 0
        # Accumulate every TextBlock + ResultMessage so the span carries the
        # same agent narrative the log file shows — that is what Phoenix
        # renders in the span detail pane via output.value.
        output_chunks: list[str] = []

        # The SDK only pipes the claude CLI's stderr when a callback is set;
        # without this, a CLI failure surfaces as the opaque "Command failed
        # with exit code 1 — Check stderr output for details". Capture the tail
        # so a genuine failure carries the real error, and mirror it into the
        # logs for live visibility.
        stderr_tail: deque[str] = deque(maxlen=80)

        def _capture_stderr(line: str) -> None:
            stderr_tail.append(line)
            _write_all(f"  ⚠ {line.rstrip()}\n")

        # Whether the CLI emitted a (non-error) ResultMessage. Some claude CLI
        # builds exit non-zero on teardown even after a successful result; when
        # that happens we must not abort the whole orchestrator.
        completed_ok = False

        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    system_prompt=system_prompt,
                    permission_mode="bypassPermissions",
                    cwd=str(ctx.repo_root),
                    plugins=plugins or [],
                    stderr=_capture_stderr,
                ),
            ):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            _write_all(block.text)
                            output_chunks.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            _write_all(_tool_status(block))
                            tool_calls += 1
                            output_chunks.append(_tool_status(block))
                            emit_event(
                                ctx,
                                "tool_call",
                                agent=agent_name,
                                task_id=task_id,
                                attrs=_tool_attrs(block),
                            )
                elif isinstance(message, ResultMessage):
                    if not message.is_error:
                        completed_ok = True
                    if message.result:
                        _write_all(message.result + "\n")
                        output_chunks.append(message.result + "\n")
        except Exception as exc:
            stderr_text = "\n".join(s.rstrip() for s in stderr_tail).strip()
            if completed_ok:
                # Work is done (commits / bd state were written via tools during
                # the session); the non-zero exit happened after the successful
                # result. Log and carry on instead of crashing the run.
                log(
                    f"{agent_name}: claude CLI exited abnormally after a "
                    f"successful result — continuing "
                    f"({type(exc).__name__}: {exc})."
                )
                emit_event(
                    ctx,
                    "agent_cli_exit_ignored",
                    agent=agent_name,
                    task_id=task_id,
                    attrs={"error": str(exc), "stderr_tail": stderr_text[-2000:]},
                )
            else:
                detail = (
                    f"\n--- claude CLI stderr (last {len(stderr_tail)} line(s)) ---\n{stderr_text}"
                    if stderr_text
                    else "\n(claude CLI produced no stderr output)"
                )
                msg = (
                    f"{agent_name} agent failed before completing: "
                    f"{type(exc).__name__}: {exc}{detail}"
                )
                _write_all(f"\nERROR: {msg}\n")
                emit_event(
                    ctx,
                    "agent_error",
                    agent=agent_name,
                    task_id=task_id,
                    attrs={"error": str(exc), "stderr_tail": stderr_text[-4000:]},
                )
                set_current_span_attribute("error", True)
                set_current_span_attribute("error.message", msg[:2000])
                raise RuntimeError(msg) from exc

        output_text = "".join(output_chunks)
        if output_text:
            set_current_span_attribute("output.value", _truncate_for_span(output_text))
            set_current_span_attribute("output.mime_type", "text/plain")
        set_current_span_attribute("tool_calls", tool_calls)

        emit_event(
            ctx,
            "agent_finished",
            agent=agent_name,
            task_id=task_id,
            attrs={"tool_calls": tool_calls, "output_chars": len(output_text)},
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
