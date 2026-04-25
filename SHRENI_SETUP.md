# Shreni Setup Guide

Everything that happens when you run `shreni init` and what you need before it will succeed.

---

## Prerequisites (one-time per machine)

Run these once. `shreni init` checks each one on every invocation and exits early with exact instructions if anything is missing.

### 1. Beads (`bd`)

The issue tracker CLI. Shreni uses it to create, update, and close tasks.

```bash
# Install — see https://github.com/dolt-hub/beads
# Verify
bd --version
```

### 2. Dolt

The embedded SQL database that backs Beads. `bd` ships with an embedded Dolt engine but the standalone `dolt` CLI is still needed for backup operations.

```bash
brew install dolt
dolt version
```

### 3. Claude Code (`claude`)

The agent runtime. Silpi and Viharapala run as Claude Code subagents.

```bash
# Install — see https://claude.ai/claude-code
claude --version
```

### 4. GitHub CLI (`gh`) — authenticated

Used to create the private issues backup repository automatically.

```bash
brew install gh
gh auth login        # follow prompts — SSH recommended
gh api user --jq .login   # verify: prints your GitHub username
```

---

## Running init

```bash
shreni init --repo /path/to/your/project
# Optional override if the project name should differ from the directory name:
shreni init --repo /path/to/your/project --project-name MyProject
```

The project name is slugified (lowercased, non-alphanumerics replaced with `-`) to form the **prefix** used for issue IDs and directory names. Example: `"My Project"` → `my-project`.

---

## What init does, step by step

### Phase 1 — Prerequisite checks

Checks `bd`, `claude`, `dolt`, and `gh` are in `PATH` and that `gh` is authenticated. Exits with a clear error message on the first failure. Nothing is written to disk in this phase.

### Phase 2 — Project setup

Steps run in this order:

---

#### Step 1 — Beads database (`bd init`)

**Condition:** skipped if `.beads/embeddeddolt/<prefix>/` already exists.

```
.beads/
  embeddeddolt/
    <prefix>/          ← created here (embedded Dolt database)
      .dolt/
        noms/          ← chunk store (all issue data)
        repo_state.json
  metadata.json        ← written by bd init — tells bd which database to open
  config.yaml          ← beads config (backup interval, export path, etc.)
```

Command run internally:
```bash
bd init --prefix <prefix> --non-interactive
```

> **If metadata.json drifts** (e.g. someone ran `bd init` with a different prefix and `bd list` shows nothing): fix it by running `bd init --prefix <prefix> --non-interactive` manually once.

---

#### Step 2 — Gitignore `.beads/`

**Condition:** skipped if `.beads/` is already in `.gitignore`.

Adds `.beads/` to the project's `.gitignore`. If `.beads/` was previously tracked by git, it is removed from the index with `git rm -r --cached` and a commit is made.

**Why:** Dolt is the source of truth for issue data. Tracking `.beads/` in project git causes merge conflicts when agents switch branches — Dolt writes to `issues.jsonl` on every `bd` command.

---

#### Step 3 — Beads backup config

**Condition:** skipped if `backup:` is already present in `.beads/config.yaml`.

Appends to `.beads/config.yaml`:

```yaml
backup:
  enabled: true
  git-push: false   # prevents beads' own backup commits racing with agent commits
  interval: 15m
```

`git-push: false` disables beads' built-in git-push behavior. The shreni cron handles pushing instead.

---

#### Step 4 — GitHub issues backup repo

**Condition:** skipped if `.beads/backup/.git/` already exists.

Creates a private GitHub repository named `<prefix>-issues` and initialises `.beads/backup/` as its local git clone.

```
.beads/
  backup/
    .git/              ← standalone git repo (independent of project git)
    .gitignore         ← excludes dolt binary files (*.darc, manifest, oldgen, LOCK)
    issues.jsonl       ← snapshot of all issues (copied from .beads/issues.jsonl)
```

Steps performed:
1. `gh repo create <prefix>-issues --private` — creates the GitHub repo
2. `git init -b main` inside `.beads/backup/`
3. `git remote add origin git@github.com:<user>/<prefix>-issues.git`
4. Writes `.gitignore` excluding dolt binary backup artifacts
5. Copies `.beads/issues.jsonl` into `.beads/backup/` if it exists
6. `git commit --allow-empty -m "init: beads issue backup"`
7. `git push --force -u origin main`

**Note:** `.beads/backup/` is a completely separate git repository from the project repo. It is invisible to project git because `.beads/` is gitignored. Dolt also writes binary backup files (`.darc`, `manifest`, `oldgen`) into this directory — these are excluded from git commits by the `.gitignore`.

---

#### Step 5 — Backup cron job

Always runs (no skip condition). Replaces any existing shreni cron entry for this repo.

Installs a crontab entry that runs every 5 minutes:

```
*/5 * * * *  cp .beads/issues.jsonl .beads/backup/issues.jsonl 2>/dev/null; \
             cd .beads/backup && \
             git add issues.jsonl && \
             git commit --allow-empty -m backup && \
             git push --force origin main \
             >> .claude/bd-backup.log 2>&1
```

What this does each run:
1. Copies `.beads/issues.jsonl` (written by beads' auto-export) into the backup repo
2. Stages and commits it (even if unchanged, via `--allow-empty`)
3. Force-pushes to `github.com/<user>/<prefix>-issues`
4. Appends output to `.claude/bd-backup.log`

The cron marker is `# shreni-bd-backup:/path/to/repo`. Re-running `shreni init` always replaces the entry so changes to the cron format take effect immediately.

---

#### Step 6 — CLAUDE.md

Silpi (the implementer agent) reads the repository and creates or updates `CLAUDE.md` at the repo root. This file is the primary context document that all agents read at the start of every task.

If `CLAUDE.md` already exists, Silpi adds any missing sections without overwriting existing content.

---

## After init completes

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Project '<name>' is ready.
  Issues backup: github.com/<user>/<prefix>-issues
  Backup log: .claude/bd-backup.log
  Run: shreni run --repo /path/to/project
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Start the orchestrator:

```bash
shreni run --repo /path/to/project
```

---

## Monitoring agents

Each agent writes its output to a separate log file under `.claude/`:

| File | Agent |
|---|---|
| `.claude/silpi.log` | Silpi — implementation and feedback |
| `.claude/viharapala.log` | Viharapala — code review |
| `.claude/parikshaka.log` | Parikshaka — QA / e2e triage |

The main terminal (`shreni run`) shows only orchestrator status — task picks, merges, state transitions.

### tmux (automatic)

If `tmux` is installed, `shreni run` automatically opens a detached session named `shreni-<project>` with three side-by-side panes tailing each log:

```
┌──────────────┬─────────────────┬──────────────┐
│    Silpi     │   Viharapala    │  Parikshaka  │
│   silpi.log  │ viharapala.log  │parikshaka.log│
└──────────────┴─────────────────┴──────────────┘
```

Attach to it in another terminal:

```bash
tmux attach -t shreni-<project>
```

If the session already exists (e.g. after a restart), `shreni run` prints the attach command and leaves the existing session untouched.

### Manual (no tmux)

Open separate terminals and tail each file:

```bash
tail -f /path/to/project/.claude/silpi.log
tail -f /path/to/project/.claude/viharapala.log
tail -f /path/to/project/.claude/parikshaka.log
```

---

## Re-running init

`shreni init` is safe to re-run. Each step has a skip condition so only missing pieces are created. The one exception is the cron job — it is always replaced to pick up any format changes.

---

## Troubleshooting

### `bd list` shows no issues after init

`metadata.json` is pointing at the wrong database. Fix:

```bash
cd /path/to/project
bd init --prefix <prefix> --non-interactive
```

This regenerates `metadata.json` without touching issue data.

### Backup not reaching GitHub

Check the log:

```bash
tail -f /path/to/project/.claude/bd-backup.log
```

Common causes:
- SSH key not added to GitHub — run `gh auth status` and `ssh -T git@github.com`
- `<prefix>-issues` repo was deleted on GitHub — re-run `shreni init` to recreate it
- `.beads/issues.jsonl` not yet written — run `bd export` to force an export

### Cron entry has old `dolt push` command

Re-run `shreni init`. The cron step always replaces the entry.

### "Found existing Dolt database" error during init

Another database directory exists in `.beads/embeddeddolt/` under a different prefix. `bd init` refuses to run. This is safe to ignore if your prefix database already exists (Step 1 skips anyway). If it does not exist, delete the stale directory:

```bash
rm -rf /path/to/project/.beads/embeddeddolt/<wrong-prefix>
shreni init --repo /path/to/project
```
