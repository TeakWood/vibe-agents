"""Resolve locally installed Claude Code plugins for use in SDK sessions."""

import sys
from pathlib import Path

from claude_agent_sdk import SdkPluginConfig


def resolve_plugin(marketplace: str, plugin_name: str) -> SdkPluginConfig | None:
    """Return a SdkPluginConfig for a locally installed plugin, or None if not found.

    Checks the versioned cache first (picks newest version), then falls back to
    the stable marketplace directory which has no version component.
    """
    base = Path.home() / ".claude" / "plugins"

    # ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
    cache_dir = base / "cache" / marketplace / plugin_name
    if cache_dir.is_dir():
        versions = sorted(
            (d for d in cache_dir.iterdir() if d.is_dir()),
            key=lambda d: d.name,
        )
        if versions:
            return SdkPluginConfig(type="local", path=str(versions[-1]))

    # ~/.claude/plugins/marketplaces/<marketplace>/plugins/<plugin>/
    stable = base / "marketplaces" / marketplace / "plugins" / plugin_name
    if stable.is_dir():
        return SdkPluginConfig(type="local", path=str(stable))

    return None
