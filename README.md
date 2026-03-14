# vibe-agents
Vibe coding agents with orchestrator

## Setup

### 1. Install Python dependencies

```bash
uv sync
```

### 2. Install Claude Code plugins

Silpi uses the [`frontend-design`](https://claudecode.anthropic.com/marketplace/frontend-design@claude-code-plugins) plugin from the Claude Code marketplace to build production-grade frontend interfaces.

Install it via the bundled script:

```bash
uv run install-plugins
```

This runs `claude plugin add frontend-design@claude-code-plugins` and registers it for Silpi automatically via `silpi/.claude/settings.json`.

To install manually from the Claude Code marketplace:

```bash
claude plugin install frontend-design@claude-code-plugins
```

Or search for **frontend-design** in the Claude Code marketplace UI (`/marketplace` in Claude Code).

## Running

```bash
# Python runner
python run.py --repo /path/to/repo [--project-name MyProject]

# Bash runner (plain tmux session, outside Claude Code)
bash run.sh /path/to/repo [ProjectName]
```
