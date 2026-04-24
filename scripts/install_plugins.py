#!/usr/bin/env python3
"""Install required Claude Code plugins for Shreni."""

import subprocess
import sys


PLUGINS = [
    "frontend-design@claude-code-plugins",
]


def main() -> None:
    for plugin in PLUGINS:
        print(f"Installing Claude Code plugin: {plugin}")
        result = subprocess.run(
            ["claude", "plugin", "install", plugin],
            check=False,
        )
        if result.returncode != 0:
            print(f"ERROR: Failed to install plugin '{plugin}'", file=sys.stderr)
            sys.exit(result.returncode)
        print(f"Installed: {plugin}")
    print("All plugins installed.")


if __name__ == "__main__":
    main()
