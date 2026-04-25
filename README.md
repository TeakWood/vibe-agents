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

## Usage

Must be run **outside** any active Claude Code session (open a plain terminal).

### Initialise a new project (once per repo)

```bash
uv run shreni init --repo /path/to/repo [--project-name MyProject]
```

Checks prerequisites (dolt, DoltHub credentials), initialises `bd`, configures DoltHub backup, and generates `CLAUDE.md`.

### Run the orchestrator

```bash
uv run shreni run --repo /path/to/repo [--project-name MyProject]
```

To use `shreni` directly without `uv run`, activate the virtual environment first:

```bash
source .venv/bin/activate
shreni run --repo /path/to/repo
```
