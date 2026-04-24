# Shreni (श्रेणी)

An autonomous multi-agent software development system. Shreni takes tasks from a `bd` backlog and implements them end-to-end — writing code, running tests, reviewing changes, and merging to `main`.

The name comes from *shreni*, the ancient Indian guild of craftsmen: specialized workers organized under a master architect to build with quality and discipline.

## Agents

| Agent | Sanskrit | Role |
|-------|----------|------|
| **Sthapathi** | स्थपति | Master architect — orchestrates the team, drives the task loop |
| **Silpi** | शिल्पी | Craftsman — implements tasks, writes tests, addresses review feedback |
| **Viharapala** | विहारपाल | Guardian — reviews code and epic designs, sets verdicts |
| **Parikshaka** | परीक्षक | Examiner — runs e2e tests on a schedule, creates bug tasks on failure |

## Setup

### 1. Install Python dependencies

```bash
uv sync
```

### 2. Install Claude Code plugins

Silpi uses the [`frontend-design`](https://claudecode.anthropic.com/marketplace/frontend-design@claude-code-plugins) plugin from the Claude Code marketplace to build production-grade frontend interfaces.

```bash
uv run install-plugins
```

To install manually:

```bash
claude plugin install frontend-design@claude-code-plugins
```

## Running

```bash
# Python runner
python run.py --repo /path/to/repo [--project-name MyProject]

# Or via the installed CLI
shreni --repo /path/to/repo [--project-name MyProject]

# Bash runner (plain tmux session, outside Claude Code)
bash run.sh /path/to/repo [ProjectName]
```

Must be run **outside** any active Claude Code session.
