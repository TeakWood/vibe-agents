# vibe-agents — Technical Design

## Overview

vibe-agents is an autonomous multi-agent coding system built on the Claude Agent SDK. It takes a backlog of tasks from a `bd` (Beads) issue tracker and implements them end-to-end: writing code, running tests, reviewing changes, and merging to `main` — without human involvement for routine tasks.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Sthapathi (orchestrator)             │
│                                                         │
│  ┌──────────┐   implement/address   ┌───────────────┐   │
│  │  Silpi   │ ◄──────────────────── │  task_loop.py │   │
│  │  (impl)  │ ──────────────────►   │               │   │
│  └──────────┘   ready-for-review    │               │   │
│                                     │               │   │
│  ┌──────────────┐   review          │               │   │
│  │  Viharapala  │ ◄─────────────── │               │   │
│  │  (reviewer)  │ ──────────────►  │               │   │
│  └──────────────┘  approved /       └───────────────┘   │
│                    changes-required                      │
└─────────────────────────────────────────────────────────┘
           │                               │
           │ spawns                        │ reads/writes
           ▼                               ▼
  ┌─────────────────┐             ┌─────────────────┐
  │   Parikshaka    │             │   bd (Beads)    │
  │  (QA / cron)   │             │  issue tracker  │
  └─────────────────┘             └─────────────────┘
```

### Agents

| Agent | Role | Process model |
|-------|------|---------------|
| **Sthapathi** | Master orchestrator — picks tasks, drives the loop, manages lifecycle | Main async process |
| **Silpi** | Implementer — writes code, tests, commits | Claude SDK sub-agent (invoked via `run_agent`) |
| **Viharapala** | Code reviewer — runs quality gates, writes review comments, sets verdict | Claude SDK sub-agent |
| **Parikshaka** | QA examiner — runs e2e tests on a cron schedule, creates bug tasks on failure | Child `subprocess.Popen` |

---

## Module Layout

```
vibe_agents/
├── sthapathi.py          # Orchestrator entry point and main loop
├── context.py            # Runtime dataclass (repo_root, project_name, etc.)
├── bd.py                 # All Beads CLI interactions
├── state.py              # Crash-recovery state files (.claude/)
├── git.py                # Git operations (branch, merge, push)
├── shell.py              # Logging (log, make_logger) and slugify
├── plugins.py            # Claude Code plugin resolution
├── agents/
│   ├── runner.py         # Generic Claude SDK runner (run_agent, load_agent_prompt)
│   ├── silpi.py          # Silpi prompt builders (implement, address_feedback, breakdown_epic, init_project)
│   ├── viharapala.py     # Viharapala prompt builder (review)
│   └── parikshaka/
│       ├── agent.py      # Parikshaka process: discover → cron install → sleep → SIGTERM cleanup
│       ├── cron.py       # macOS crontab management (install, remove, marker-based idempotency)
│       ├── runner.py     # Cron payload: run e2e, parse failures, create bd bugs
│       ├── discovery.py  # Find e2e command from CLAUDE.md / package.json / pyproject.toml / Makefile
│       └── parser.py     # Parse Playwright / pytest / Cypress test output into TestFailure structs
└── workflow/
    ├── task_loop.py      # implement → review → (address → review)* → merge state machine
    ├── epic.py           # Epic breakdown: invoke Silpi to decompose approved epics
    └── resume.py         # Crash recovery: find and resume in-progress work
```

Agent prompt files (Markdown, loaded by `runner.py` as system prompts):

```
silpi/
├── AGENTS.md             # Silpi instructions: implementation loop, epic breakdown, rules
├── SOUL.md               # Silpi persona and values
└── .claude/settings.json # frontend-design plugin enabled at project scope

viharapala/
├── AGENTS.md             # Viharapala instructions: code review and epic design review
├── SOUL.md               # Viharapala persona and values
└── skills/bd-review/SKILL.md
```

---

## Key Data Flows

### Task lifecycle

```
bd task (ready)
    │
    ▼
Sthapathi claims task → create feature branch
    │
    ▼
task_loop.py — state machine
    │
    ├── silpi_implement ──► Silpi writes code + tests + commits
    │                           └─► bd set-state review=ready-for-review
    │
    ├── viharapala_review ──► Viharapala runs quality gates, writes comment
    │                             ├─► review=approved → merge state
    │                             ├─► review=changes-required → silpi_address
    │                             └─► review=viharapala-approved → pause for author
    │
    ├── silpi_address ──► Silpi fixes blocking issues → resubmits
    │
    └── merge ──► squash-merge feature branch → main → push → close task
```

### Epic lifecycle

```
Author creates epic in bd
    │
    ▼
Sthapathi picks up epic (type=epic, label=review:approved pending)
    │
    ▼
Silpi proposes design (comment on epic)
    │
    ▼
Viharapala reviews design → sets review=viharapala-approved
    │
    ▼
Author reviews → sets review=approved (manual step)
    │
    ▼
Sthapathi runs epic breakdown → Silpi decomposes into feature tasks
    │
    ▼
Silpi sets breakdown=complete → feature tasks picked up as normal tasks
```

### Parikshaka lifecycle

```
Sthapathi starts → subprocess.Popen(parikshaka/agent.py)
    │
    ▼
Parikshaka discovers e2e command → installs crontab (*/30 * * * *)
    │
    ▼
Every 30 min: parikshaka/runner.py
    ├── run e2e command in repo
    ├── parse failures (Playwright/pytest/Cypress)
    └── for each failure: bd create bug (if not already open)
    │
    ▼
Sthapathi exits → SIGTERM → Parikshaka removes crontab entry → exits
```

---

## State Management

### Crash recovery (`state.py`)

Two JSON files under `<repo>/.claude/`:

| File | Purpose |
|------|---------|
| `current-task.json` | Records the active task, branch, round, and state so the orchestrator can resume after a crash |
| `epic-breakdown.json` | Records an in-progress epic breakdown to allow retry if interrupted |

`resume.py` checks four sources in priority order on startup:

1. `current-task.json` state file
2. Current git branch (if it looks like a feature branch)
3. Tasks with `label=review:ready-for-review` → resume at `viharapala_review`
4. Tasks with `label=review:approved` (non-epic) → resume at `merge`

### bd label conventions

| Label | Meaning |
|-------|---------|
| `review:ready-for-review` | Silpi has submitted; Viharapala should pick it up |
| `review:changes-required` | Viharapala found blocking issues |
| `review:approved` | Approved; orchestrator will merge |
| `review:viharapala-approved` | Reviewer approved epic design; awaiting author sign-off |
| `breakdown:complete` | Epic has been decomposed into feature tasks |
| `manual` | Bug was created by a human (not by Parikshaka) |

---

## Agent SDK Integration

`agents/runner.py` wraps `claude_agent_sdk.query()`. Each agent invocation:

1. Loads the agent's `AGENTS.md` as the system prompt (via `load_agent_prompt`)
2. Injects a user-turn message built by the calling module (e.g. `silpi.implement`)
3. Passes `ClaudeAgentOptions(cwd=repo_root)` so the agent operates inside the target repo
4. Optionally passes `SdkPluginConfig` entries (Silpi loads `frontend-design@claude-code-plugins`)

The `cwd` is always the **target repo**, not the vibe-agents project root. The agent prompt files live in the vibe-agents project and are loaded by path before the SDK call.

---

## Plugin System

Silpi uses the `frontend-design` Claude Code marketplace plugin for UI/frontend tasks. The plugin is:

- Installed via `uv run install-plugins` (runs `claude plugin install frontend-design@claude-code-plugins`)
- Registered at project scope in `silpi/.claude/settings.json`
- Resolved at runtime by `plugins.py` → passed as `SdkPluginConfig` to `run_agent`
- Invoked inside Silpi's session via `/frontend-design` when the task involves UI work

`plugins.py` returns `None` if the plugin is not installed; Silpi still runs but without the design guidelines.

---

## bd CLI Workarounds

The `bd query` command cannot parse colons in label values (e.g. `label=review:approved` fails). All label-based lookups use:

```python
bd list --json  # returns all tasks
# then filter in Python: [t for t in tasks if label in (t.get("labels") or [])]
```

Similarly, `bd` does not automatically set epics to `in_progress` when child tasks start. Sthapathi infers which epic group is active by finding the `parent` IDs of tasks with `status=in_progress`.

---

## Configuration

All runtime configuration flows through the `Context` dataclass. There are no global variables.

| Field | Source | Purpose |
|-------|--------|---------|
| `repo_root` | `--repo` CLI arg | Target repository path |
| `project_name` | `--project-name` or `repo_root.name` | Used in agent prompts |
| `agents_dir` | vibe-agents project root | Locates `silpi/` and `viharapala/` prompt dirs |
| `idle_interval` | Hardcoded default 120s | Sleep time when no tasks are ready |

---

## Logging

Each agent has a named logger produced by `make_logger(agent_name)`:

```
[2026-04-23 10:15:32] [Sthapathi] Task T-42: Add user authentication
[2026-04-23 10:15:33] [Silpi] [Round 1] implement T-42
[2026-04-23 10:28:11] [Viharapala] [Round 1] review T-42
[2026-04-23 10:29:05] [Parikshaka] Running: npm run e2e
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `claude-agent-sdk` | Claude sub-agent runner |
| `anyio` | Async runtime for Sthapathi's main loop |
| `bd` (CLI, external) | Beads issue tracker — task management |
| `claude` (CLI, external) | Claude Code CLI — plugin installation |
