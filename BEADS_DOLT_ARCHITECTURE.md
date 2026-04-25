# How Beads and Dolt Work Together

A technical reference for the beads + dolt persistence stack.

---

## The Core Idea

Beads uses [Dolt](https://docs.dolthub.com) as its primary database. Dolt is best understood as **git for SQL tables** — it is a fully MySQL-compatible relational database that also tracks every row change as a versioned commit. This gives beads two capabilities in one:

1. **Live SQL queries** — `bd list`, `bd show`, filters, search all run as SQL against a local Dolt server.
2. **Distributed sync** — the entire database can be pushed to / pulled from a remote (DoltHub), just like `git push/pull`.

---

## Runtime Architecture

Beads supports two dolt modes. Check `.beads/metadata.json` (`dolt_mode`) to see which you have.

### Mode 1 — Embedded (default for beads v1.x)

```
┌─────────────────────────────────────────────────────┐
│  bd CLI (Go binary)                                  │
│                                                      │
│  dolt engine runs in-process (no separate server)    │
└──────────────────────┬──────────────────────────────┘
                       │  in-process
┌──────────────────────▼──────────────────────────────┐
│  Dolt Repository  (.beads/embeddeddolt/)             │
│                                                      │
│  .beads/embeddeddolt/.dolt/noms/  — chunk store      │
│  .beads/embeddeddolt/.dolt/repo_state.json           │
└─────────────────────────────────────────────────────┘
```

No server process to manage. `bd dolt status` reports `Dolt engine: embedded`.

### Mode 2 — Server (legacy)

```
┌─────────────────────────────────────────────────────┐
│  bd CLI (Go binary)                                  │
│                                                      │
│  reads/writes via MySQL protocol (TCP)               │
└──────────────────────┬──────────────────────────────┘
                       │  127.0.0.1:<port>
┌──────────────────────▼──────────────────────────────┐
│  Dolt SQL Server  (dolt sql-server)                  │
│                                                      │
│  MySQL-compatible server wrapping the dolt repo      │
│  Port stored in  .beads/dolt-server.port             │
│  PID stored in   .beads/dolt-server.pid              │
│  Logs at         .beads/dolt-server.log              │
└──────────────────────┬──────────────────────────────┘
                       │  reads/writes files
┌──────────────────────▼──────────────────────────────┐
│  Dolt Repository  (.beads/dolt/)                     │
│                                                      │
│  .beads/dolt/.dolt/noms/       — chunk store (data)  │
│  .beads/dolt/.dolt/repo_state.json — remotes, HEAD   │
│  .beads/dolt/config.yaml       — server config       │
└─────────────────────────────────────────────────────┘
```

**`bd dolt start`** launches `dolt sql-server` as a background process. **`bd dolt stop`** kills it.

---

## What Is Stored Where

| Entity | Storage |
|---|---|
| Issues, labels, dependencies, comments | SQL tables in the dolt repo |
| Server config (remotes, etc.) | `.beads/dolt/.dolt/repo_state.json` |
| Dolt server tuning (port, host, timeouts) | `.beads/dolt/config.yaml` |
| Runtime state (PID, port, lock) | `.beads/dolt-server.{pid,port,lock}` |
| Backend type, database name | `.beads/metadata.json` |
| JSONL backup (off-machine) | `.beads/backup/` — standalone git repo → GitHub |

The SQL tables beads uses are approximately: `issues`, `labels`, `dependencies`, `comments`, `config`, `events`.

---

## Versioning: How Dolt Differs from a Regular Database

Every time beads mutates data (create, update, close an issue), dolt can record a **commit** — a snapshot of all changed rows with an author, timestamp, and hash. This is equivalent to `git commit` but for table rows.

This means:
- You get a full audit trail of every issue change, queryable with `dolt log` or `CALL DOLT_DIFF(...)`.
- Push and pull move the entire commit history, not just current row values.
- Conflicts during pull are resolved at the row level (not line level like git).

The dolt CLI operates on this commit history:

```bash
cd .beads/dolt
dolt log           # commit history (like git log)
dolt diff          # uncommitted changes (like git diff)
dolt branch -a     # branches + remote-tracking branches
```

---

## Remote Sync (DoltHub — Optional)

DoltHub is **not required for normal operation**. Issue data is backed up off-machine via the JSONL git repo (see below). DoltHub is only useful if you want SQL-queryable history on the web.

If you choose to configure a DoltHub remote, note that there are **two places** the remote URL is stored and they must be kept in sync:

| Store | Location | Set by |
|---|---|---|
| Native dolt (CLI) | `.beads/dolt/.dolt/repo_state.json` | `dolt remote add` |
| Beads SQL store | SQL table inside the dolt database | `bd dolt remote add` |

When they diverge you get the conflict error:

```
Error: remote "origin" has conflicting URLs:
  SQL: https://doltremoteapi.dolthub.com/old-name/repo
  CLI: https://doltremoteapi.dolthub.com/new-name/repo
```

Fix: `bd dolt remote remove origin --force` then `bd dolt remote add origin <url>`.

---

## JSONL Backup: The Off-Machine Layer

In parallel with dolt, beads maintains a JSONL export in `.beads/backup/`:

```
.beads/backup/
  .git/                ← standalone git repo → github.com/<user>/<project>-issues
  .gitignore
  issues.jsonl
  labels.jsonl
  dependencies.jsonl
  comments.jsonl
  events.jsonl
  config.jsonl
  backup_state.json    ← last exported dolt commit hash + row counts
```

**When JSONL is written:** on a configurable interval (`backup.interval`, default 15 minutes) and on clean shutdown.

**When JSONL is pushed off-machine:** a cron job runs every 5 minutes:
```bash
cd .beads/backup && git add -A && git commit --allow-empty -m backup && git push --force origin main
```
The backup target is a private GitHub repo named `<project>-issues`, created automatically by `shreni init` using the `gh` CLI. Auth uses the same SSH key as the project repo — no separate credential setup needed.

**When JSONL is read:** during `bd backup restore`. If the dolt SQL tables are empty or the dolt server is unavailable, beads falls back to serving data from these files.

**Important:** After a `bd backup restore`, the JSONL data is loaded back into memory but the dolt SQL tables may not be rebuilt with full commit history. The dolt repo will have a single "Initialize" commit and no prior history. The data is intact; the version history is not.

**Note on DoltHub:** DoltHub is no longer used for backup. The embedded dolt repo has no required remote. If you want SQL-queryable issue history on the web, you can manually configure a DoltHub remote — but it is not part of normal operation.

---

## Lifecycle of a `bd create` Command

1. `bd create --title="..."` parses args and opens a MySQL connection to `.beads/dolt-server.port`.
2. Beads issues `INSERT INTO issues (...)` SQL.
3. Dolt records the row insertion as an uncommitted working-set change.
4. Beads calls `CALL DOLT_COMMIT(...)` to snapshot the change as a dolt commit.
5. Beads attempts `CALL DOLT_PUSH('origin', 'main')` (auto-push — may fail silently).
6. Beads prints the new issue ID to stdout.
7. On the next backup interval, the JSONL export is updated.

---

## Key Files Reference

| File | Purpose |
|---|---|
| `.beads/dolt/` | The dolt repository directory |
| `.beads/dolt/config.yaml` | Dolt SQL server config (port, host, timeouts) |
| `.beads/dolt/.dolt/repo_state.json` | Remotes, HEAD, branch tracking |
| `.beads/dolt/.dolt/noms/` | Chunk store — the actual data (binary, do not edit) |
| `.beads/metadata.json` | Backend type, dolt database name |
| `.beads/dolt-server.port` | Port the running server is listening on |
| `.beads/dolt-server.pid` | PID of the running server process |
| `.beads/dolt-server.log` | Server stdout/stderr log |
| `.beads/config.yaml` | Beads project config (backup interval, actor, etc.) |
| `.beads/backup/` | JSONL snapshots for off-machine recovery |

---

## Common Operations

```bash
# Start/stop the dolt server
bd dolt start
bd dolt stop

# Check server status
bd dolt status

# View raw dolt commit log
cd .beads/embeddeddolt/<prefix> && dolt log -n 10

# Inspect live data via SQL
mysql -h 127.0.0.1 -P $(cat .beads/dolt-server.port) -u root --protocol=tcp

# Force a full JSONL export
bd export

# Restore from JSONL after data loss
bd backup restore

# Manually push backup to GitHub (cron does this automatically every 5 min)
cd .beads/backup && git add -A && git commit --allow-empty -m backup && git push --force origin main

# Check backup log
tail -f .claude/bd-backup.log

# Clone issues backup on a new machine
git clone git@github.com:<user>/<project>-issues .beads/backup
```
