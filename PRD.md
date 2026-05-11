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

### Project setup

> As a developer, I want to set up a new project for Shreni with a single command so the tracker, backup, and CLAUDE.md are all configured correctly without me reading documentation.

- The developer runs `shreni init --repo /path/to/repo`.
- Shreni checks machine prerequisites (dolt CLI, DoltHub credentials) and prints exact remediation steps with exit if anything is missing.
- Once prerequisites pass, Shreni initialises `bd`, configures DoltHub backup (push every 5 minutes), and uses Silpi to generate `CLAUDE.md`.
- The developer sees a confirmation with the DoltHub URL and the command to start the orchestrator.

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

### Suppressing deliberate test skips

> As a developer, I want to mark certain tests as intentionally skipped so Parikshaka does not create bug or coverage tasks for them.

- The developer adds test name patterns to `.parikshaka-ignore` in the project root.
- `shreni init` creates the file automatically with a commented template.
- Parikshaka reads the file before processing any suite output and ignores all matching tests silently.
- Patterns support `*` as a wildcard and are matched as substrings of the full test name.

### Observability

> As a developer, I want to see exactly what each agent did on each task — which tools it called, how long it took, what verdict it produced — without grepping through interleaved log files.

- All Sthapathi sessions write structured spans and per-agent logs to `~/.shreni/projects/<slug>/`, isolated per project.
- Each task gets its own subfolder (`tasks/<task_id>/`) containing `spans.jsonl` (a structured timeline) and per-agent `.log` files (raw output).
- Spans nest: `session → task → silpi.implement → tool_call`, so a task's full execution can be reconstructed from one file.
- `shreni init` creates `~/.shreni/projects/<slug>/` so it is ready before the first run.
- `shreni logs --repo <path>` lists tasks observed; `shreni logs --repo <path> --task T-1` prints the timeline for one task.

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
| F6 | An approved task must be squash-merged to `main`, pushed, and closed in `bd`. The merge must be skipped if the branch has no commits ahead of `main`; instead the task must be re-routed to Silpi for implementation. |
| F7 | Epics must go through: design proposal → Viharapala design review → author approval → Silpi task breakdown → normal task loop. |
| F8 | Tasks sharing a parent epic must be prioritised over unrelated tasks so work within a group completes before new groups start. |
| F9 | After each task merge, Sthapathi must enqueue it for Parikshaka and continue to the next task immediately — the main loop must not block on Parikshaka. |
| F10 | The Parikshaka queue must be persisted to `<repo>/.claude/parikshaka-queue.json` before the entry is sent to the in-memory worker, so no tasks are lost on crash. |
| F11 | On startup, Sthapathi must replay any entries remaining in `parikshaka-queue.json` into the worker before starting the main loop. |
| F12 | Parikshaka must discover the e2e command from CLAUDE.md, package.json, pyproject.toml, or Makefile. If none is found, it must skip the check and log the reason. |
| F13 | On e2e failure, Parikshaka must create a `bd` bug task (`type=bug, priority=1, label=parikshaka`) for each distinct failing test, unless an open bug with the same title already exists. |
| F14 | Parikshaka must create a `bd` feature task (`type=feature, label=e2e`) for any user-facing behaviour introduced by the merged task that is not already covered by an existing e2e test. It must not create duplicate coverage tasks. |
| F23 | Parikshaka must read `.parikshaka-ignore` before processing any suite output. Tests whose full name matches a pattern in the file must be silently skipped — no bug or coverage task is created for them. Patterns support `*` as a wildcard and substring matching. Lines starting with `#` are comments. |
| F24 | `shreni init` must create `.parikshaka-ignore` in the target repo if it does not already exist, pre-populated with a commented template explaining the format. |
| F15 | Silpi must recognise `label=e2e` tasks and follow the e2e test authoring flow: write tests, run the suite, commit only test files, submit for review. |
| F16 | `shreni init` must create or update `CLAUDE.md` using Silpi, capturing build, test, lint, dev server, env vars, key directories, coding conventions, and issue tracker rules (including the `manual`/`parikshaka`/`e2e` label conventions and task creation order). `shreni run` must exit with an error if `CLAUDE.md` is absent. |
| F17 | On crash or restart, Sthapathi must resume in-progress work without re-implementing already-completed steps. |
| F18 | `shreni init` must check machine prerequisites (dolt CLI installed, DoltHub credentials present, credentials verified via `dolt creds check`). On any failure it must print exact remediation steps and exit immediately. Per-project setup must not proceed until all prerequisites pass. |
| F19 | `shreni init` must run `bd init --prefix <slug>` if `.beads/` does not already exist, where the slug is derived from the project name (lowercase, hyphens). |
| F20 | `shreni init` must append backup configuration to `.beads/config.yaml` (`enabled: true`, `git-push: false`, `interval: 15m`) if not already present. `git-push: false` is required to prevent backup commits from racing with agent commits. |
| F21 | `shreni init` must register a DoltHub remote (`bd dolt remote add origin https://doltremoteapi.dolthub.com/<user>/<db>`) and perform an initial push using `dolt push origin main` directly from `.beads/embeddeddolt/<prefix>/`. |
| F22 | `shreni init` must install a cron job that pushes `<repo>/.beads/embeddeddolt/<prefix>/` to DoltHub every 5 minutes using `dolt push origin main`. The push must be invoked directly (not via `bd dolt push`) to avoid the `bd dolt push` port bug in server mode. |
| F25 | `shreni init` must create the per-project observability tree at `~/.shreni/projects/<slug>/` (with a `tasks/` subfolder), where `<slug>` is derived from the project name. Existing folders must be left intact. |
| F26 | The orchestrator must emit a structured JSONL span stream per task at `~/.shreni/projects/<slug>/tasks/<task_id>/spans.jsonl`, capturing at minimum: task pickup, each Silpi/Viharapala round, every tool call inside each agent, the review verdict, and the merge result. Orchestrator-level events that do not belong to a task (session start/stop, idle ticks) must be written to `~/.shreni/projects/<slug>/session-spans.jsonl`. |
| F27 | Each agent invocation (Silpi, Viharapala, Parikshaka) must write its raw output to a per-task log at `~/.shreni/projects/<slug>/tasks/<task_id>/<agent>.log`, in addition to a per-agent aggregate log at `~/.shreni/projects/<slug>/<agent>.log` (used by the tmux pane tailing). |
| F28 | Each span record must be one JSON object per line containing: ISO-8601 timestamp (`ts`), `type` (`span_start`/`span_end`/`event`), `name`, `span_id`, optional `parent_span_id` for nesting, optional `agent` and `task_id`, and on `span_end`: `duration_ms` and `status` (`ok`/`error`). |
| F29 | A `shreni logs --repo <path>` subcommand must list all task ids that have a span stream on disk; `shreni logs --repo <path> --task <id>` must print a formatted timeline; the `--raw` flag must dump the underlying JSONL unchanged. |
| F30 | `shreni logs --perfetto <path>` must export the span stream as a Chrome Trace Event Format JSON file viewable at https://ui.perfetto.dev. With `--task <id>` the file is scoped to one task; without, it bundles session + all task spans. Each `task_id` becomes a Perfetto process lane; each agent becomes a thread within that lane; span pairs collapse to complete (`ph: "X"`) events; standalone events become instant (`ph: "i"`) events. |

### Non-functional

| # | Requirement |
|---|-------------|
| N1 | No global state — all runtime configuration flows through the `Context` dataclass. |
| N2 | Log output must include timestamp and agent name for every message, with distinct ANSI colours per agent for dark-background terminals. |
| N3 | All `bd` task state transitions must use `--json` for structured, parseable output. |
| N4 | The Parikshaka background worker must process tasks sequentially to avoid concurrent `bd` writes or e2e suite conflicts. |
| N5 | The system must not run inside an active Claude Code session (`CLAUDECODE` env var check on startup). |
| N6 | Observability writes must never block or fail the agent loop. A failure to write a span or log line must be tolerated silently — observability is a side channel, not a critical path. |
| N7 | Logs and spans must be isolated per project under `~/.shreni/projects/<slug>/`. Two Shreni projects on the same machine must not share log files. |

---

## Agent Responsibilities Matrix

| Responsibility | Sthapathi | Silpi | Viharapala | Parikshaka |
|---------------|-----------|-------|------------|------------|
| Check machine prerequisites | ✅ | | | |
| Initialise bd, DoltHub remote, backup cron | ✅ | | | |
| Initialise observability tree (`~/.shreni/projects/<slug>/`) | ✅ | | | |
| Emit per-task spans and per-agent logs | ✅ | ✅ | ✅ | ✅ |
| Create/update CLAUDE.md | | ✅ | | |
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

---

## Workflow Diagram

```
shreni init --repo /path/to/repo
  ├── Phase 1: check dolt, DoltHub credentials → exit with instructions if missing
  └── Phase 2: bd init, .beads/config.yaml, DoltHub remote, initial push,
               backup cron (every 5 min), Silpi generates CLAUDE.md
         │
         ▼
shreni run --repo /path/to/repo
  └── checks CLAUDE.md present (exits with error if missing)
         │
         ▼
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
Sthapathi: branch has commits? ──No──► re-route to Silpi
    │ Yes
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
