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

> As a developer, I want to know when a merged change breaks the e2e test suite without it stalling the main development loop.

- After each task merges, Parikshaka is queued to run a quality check in the background.
- The main loop immediately picks up the next task — it does not wait for Parikshaka.
- If e2e tests fail, Parikshaka creates a bug task (`label=parikshaka`) in `bd`.
- Sthapathi picks up the bug and routes it to Silpi for a fix in a subsequent iteration.

### e2e coverage

> As a developer, I want new user-facing features to automatically get e2e test coverage without me writing the tests.

- After each task merges, Parikshaka analyses whether the completed work introduced user-visible behaviour not covered by an existing e2e test.
- If a gap is found, Parikshaka creates a coverage task (`label=e2e`) with a description of the user journey and acceptance criteria.
- Silpi picks up the task, writes the e2e tests, and submits them for Viharapala review.
- The tests land on `main` through the normal implement → review → merge cycle.

### Crash recovery

> As a developer, I want the system to resume where it left off if it crashes or is restarted.

- On startup, Sthapathi checks for in-progress work (state file, feature branches, tasks in review) and resumes without re-doing completed steps.
- Any tasks that merged before the crash but hadn't been processed by Parikshaka are replayed from a persistent queue file on restart.

---

## Non-Goals

- **Replacing the developer entirely.** Epics require human sign-off on design. The task backlog is still curated by humans.
- **Handling ambiguous tasks.** Tasks need clear acceptance criteria. The system does not ask clarifying questions during implementation.
- **Multi-repo orchestration.** One Shreni instance manages one repository.
- **Cloud deployment or persistent hosting.** Shreni runs locally as a terminal process.
- **Parikshaka writing test code.** Parikshaka creates tasks; Silpi writes the code. This keeps test code in the review cycle.

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
| F9 | After each task merge, Sthapathi must enqueue it for Parikshaka and continue to the next task immediately — the main loop must not block on Parikshaka. |
| F10 | The Parikshaka queue must be persisted to `<repo>/.claude/parikshaka-queue.json` before the entry is sent to the in-memory worker, so no tasks are lost on crash. |
| F11 | On startup, Sthapathi must replay any entries remaining in `parikshaka-queue.json` into the worker before starting the main loop. |
| F12 | Parikshaka must discover the e2e command from CLAUDE.md, package.json, pyproject.toml, or Makefile. If none is found, it must skip the check and log the reason. |
| F13 | On e2e failure, Parikshaka must create a `bd` bug task (`type=bug, priority=1, label=parikshaka`) for each distinct failing test, unless an open bug with the same title already exists. |
| F14 | Parikshaka must create a `bd` feature task (`type=feature, label=e2e`) for any user-facing behaviour introduced by the merged task that is not already covered by an existing e2e test. It must not create duplicate coverage tasks. |
| F15 | Silpi must recognise `label=e2e` tasks and follow the e2e test authoring flow: write tests, run the suite, commit only test files, submit for review. |
| F16 | On startup, Sthapathi must check for a `CLAUDE.md` in the target repo and create or update it if absent, capturing build, test, lint, dev server, env vars, key directories, coding conventions, and issue tracker rules (including the `manual`/`parikshaka`/`e2e` label conventions and task creation order). |
| F17 | On crash or restart, Sthapathi must resume in-progress work without re-implementing already-completed steps. |

### Non-functional

| # | Requirement |
|---|-------------|
| N1 | No global state — all runtime configuration flows through the `Context` dataclass. |
| N2 | Log output must include timestamp and agent name for every message. |
| N3 | All `bd` task state transitions must use `--json` for structured, parseable output. |
| N4 | The Parikshaka background worker must process tasks sequentially to avoid concurrent `bd` writes or e2e suite conflicts. |
| N5 | The system must not run inside an active Claude Code session (`CLAUDECODE` env var check on startup). |

---

## Agent Responsibilities Matrix

| Responsibility | Sthapathi | Silpi | Viharapala | Parikshaka |
|---------------|-----------|-------|------------|------------|
| Pick tasks from backlog | ✅ | | | |
| Create/delete feature branches | ✅ | | | |
| Write production code and unit tests | | ✅ | | |
| Write e2e tests | | ✅ | | |
| Run quality gates (as implementer) | | ✅ | | |
| Run quality gates (as reviewer) | | | ✅ | |
| Write review comments | | | ✅ | |
| Set review verdict | | | ✅ | |
| Squash merge to main | ✅ | | | |
| Push and close tasks | ✅ | | | |
| Propose epic design | | ✅ | | |
| Review epic design | | | ✅ | |
| Break epics into tasks | | ✅ | | |
| Queue completed tasks for QA | ✅ | | | |
| Run e2e suite | | | | ✅ |
| Create regression bug tasks | | | | ✅ |
| Create e2e coverage tasks | | | | ✅ |
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
    │
    ├──► enqueue in parikshaka-queue.json (persisted)
    │
    └──► next task immediately ◄────────────────────────┐
                                                        │
              Parikshaka worker (background):           │
                run e2e suite                           │
                  ├── regressions → bug tasks ──────────┤
                  └── coverage gaps → e2e tasks ────────┘
                           (picked up in next iteration)
```

---

## Out-of-Scope (v1)

- PR-based workflow (GitHub/GitLab PRs instead of direct merge)
- Multiple tasks running in parallel
- Agent self-improvement (agents modifying their own prompt files)
- Support for monorepos with multiple sub-projects
- Windows support
