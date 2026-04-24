"""Base agent runner shared by all agents."""

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SdkPluginConfig,
    TextBlock,
    query,
)

from ..context import Context


async def run_agent(
    system_prompt: str,
    prompt: str,
    ctx: Context,
    *,
    plugins: list[SdkPluginConfig] | None = None,
) -> None:
    """Run a Claude agent session, streaming text output to stdout."""
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
                    print(block.text, end="", flush=True)
        elif isinstance(message, ResultMessage):
            if message.result:
                print(message.result, flush=True)


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
