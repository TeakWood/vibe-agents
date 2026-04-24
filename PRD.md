# Shreni — Product Requirements Document

## Problem

Software development backlogs stall not because ideas are lacking, but because execution is slow. Routine tasks — implementing a spec, fixing a bug, reviewing a diff — each require a human to context-switch, read, type, wait, and repeat. For projects where one person or a small team is building fast, this bottleneck compounds.

LLMs can now write, test, and reason about code well enough to handle bounded, well-specified tasks end-to-end. The missing piece is the scaffolding that connects model capability to a real development workflow: branches, commits, reviews, merges, and quality gates.

Shreni is that scaffolding.

---

## Goal

Run a software development team autonomously against a task backlog. Given a repository and a list of tasks in a tracker, Shreni should implement each task, validate it passes quality gates, review it for correctness and quality, and merge it to `main` — without human involvement for routine work.

The human remains in the loop for decisions that require judgment: approving epic designs, auditing flagged reviews, and setting the task backlog.

---

## Users

**Primary user:** A solo developer or small team building a software product who wants to delegate implementation of well-specified tasks to an autonomous system while retaining control over direction and design.

**Secondary user:** A team that wants automated first-pass code review and regression detection as a quality backstop, even when they implement tasks themselves.

---

## User Stories

### Autonomous implementation

> As a developer, I want to add a task to my backlog and have it implemented, tested, reviewed, and merged without me doing it myself.

- The developer creates a task in `bd` with a title, description, and acceptance criteria.
- Shreni picks it up, creates a feature branch, implements it, runs tests, reviews the code, and merges to `main`.
- The developer sees the merged commit without having written the code.

### Review loop

> As a developer, I want the system to catch implementation errors before they land on `main`.

- Viharapala runs the project's quality gates (lint, tests) and reviews the diff against the task spec.
- If blocking issues are found, Silpi addresses them and resubmits.
- Only code that passes both quality gates and review lands on `main`.

### Epic planning

> As a developer, I want to describe a large feature at a high level and have it broken into implementable tasks automatically.

- The developer creates an epic in `bd` with a description.
- Silpi proposes a technical design as a comment.
- Viharapala reviews the design and approves or requests changes.
- After the developer approves the design, Silpi decomposes it into self-contained feature tasks.
- Sthapathi picks them up and implements them in dependency order.

### Regression detection

> As a developer, I want to know when an autonomous change breaks the e2e test suite.

- Parikshaka runs the e2e suite every 30 minutes.
- If tests fail, it creates a bug task in `bd` automatically.
- Sthapathi picks up the bug and routes it to Silpi for a fix.
- The developer sees bug tasks labelled `manual` vs. automatically-created ones so they can distinguish human-reported from automated bugs.

### Crash recovery

> As a developer, I want the system to resume where it left off if it crashes or is restarted.

- On startup, Sthapathi checks for in-progress work (state file, feature branches, tasks in review) and resumes without re-doing completed steps.

---

## Non-Goals

- **Replacing the developer entirely.** Epics require human sign-off on design. The task backlog is still curated by humans.
- **Handling ambiguous tasks.** Tasks need clear acceptance criteria. The system does not ask clarifying questions during implementation.
- **Multi-repo orchestration.** One Shreni instance manages one repository.
- **Cloud deployment or persistent hosting.** Shreni runs locally as a terminal process.

---

## Requirements

### Functional

| # | Requirement |
|---|-------------|
| F1 | Given a `bd` task in `ready` state, Sthapathi must claim it, create a feature branch, and invoke Silpi to implement it. |
| F2 | Silpi must write unit tests for every task and run all quality gates before committing. |
| F3 | Silpi must run the project build before marking a task ready for review. |
| F4 | Viharapala must run quality gates and write a structured review comment before setting a verdict. |
| F5 | If Viharapala returns `changes-required`, Silpi must address all blocking issues and resubmit. The loop repeats until approval or manual intervention. |
| F6 | An approved task must be squash-merged to `main`, pushed, and closed in `bd`. |
| F7 | Epics must go through: design proposal → Viharapala design review → author approval → Silpi task breakdown → normal task loop. |
| F8 | Tasks sharing a parent epic must be prioritised over unrelated tasks so work within a group completes before new groups start. |
| F9 | Parikshaka must discover the e2e command for the target repo (from CLAUDE.md, package.json, pyproject.toml, or Makefile). |
| F10 | Parikshaka must install a crontab entry that runs the e2e suite every 30 minutes and log output to `<repo>/.claude/qa-e2e.log`. |
| F11 | On e2e failure, Parikshaka must create a `bd` bug task (type=bug, priority=1) for each distinct test failure, unless an open bug with the same title already exists. |
| F12 | When Sthapathi exits, Parikshaka must remove its crontab entry before the process ends. |
| F13 | On startup, Sthapathi must check for a `CLAUDE.md` in the target repo and create or update it if absent, capturing build, test, lint, dev server, env vars, key directories, coding conventions, and issue tracker rules. |
| F14 | On crash or restart, Sthapathi must resume in-progress work without re-implementing already-completed steps. |

### Non-functional

| # | Requirement |
|---|-------------|
| N1 | No global state — all runtime configuration flows through the `Context` dataclass. |
| N2 | Log output must include timestamp and agent name for every message. |
| N3 | All `bd` task state transitions must use `--json` for structured, parseable output. |
| N4 | Parikshaka's crontab management must be idempotent: re-running install replaces the existing entry rather than creating a duplicate. |
| N5 | The system must not run inside an active Claude Code session (`CLAUDECODE` env var check on startup). |

---

## Agent Responsibilities Matrix

| Responsibility | Sthapathi | Silpi | Viharapala | Parikshaka |
|---------------|-----------|-------|------------|------------|
| Pick tasks from backlog | ✅ | | | |
| Create/delete feature branches | ✅ | | | |
| Write code and tests | | ✅ | | |
| Run quality gates (as implementer) | | ✅ | | |
| Run quality gates (as reviewer) | | | ✅ | |
| Write review comments | | | ✅ | |
| Set review verdict | | | ✅ | |
| Squash merge to main | ✅ | | | |
| Push and close tasks | ✅ | | | |
| Propose epic design | | ✅ | | |
| Review epic design | | | ✅ | |
| Break epics into tasks | | ✅ | | |
| Run e2e suite (cron) | | | | ✅ |
| Create bug tasks on failure | | | | ✅ |
| Manage crontab lifecycle | | | | ✅ |
| Initialise CLAUDE.md | | ✅ | | |

---

## Workflow Diagram

```
Developer adds task to bd
         │
         ▼
Sthapathi: claim task, create branch
         │
         ▼
Silpi: implement + tests + quality gates + build + commit
         │
         ▼
Viharapala: quality gates + review → verdict
         │
    ┌────┴────┐
    │         │
approved   changes-required
    │         │
    │         ▼
    │     Silpi: address feedback + resubmit
    │         │
    │         └──► Viharapala: re-review (loop)
    │
    ▼
Sthapathi: squash-merge → main → push → close task
```

---

## Out-of-Scope (v1)

- PR-based workflow (GitHub/GitLab PRs instead of direct merge)
- Parallelism (multiple tasks at once)
- Agent self-improvement (agents modifying their own prompt files)
- Task creation by agents (other than Parikshaka creating bugs and Silpi creating epic subtasks)
- Support for monorepos with multiple sub-projects
- Windows support (crontab management is macOS/Linux only)
