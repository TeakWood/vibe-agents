# Graph Report - /Users/navakanth/projects/vibe-agents  (2026-06-02)

## Corpus Check
- 29 files · ~54,645 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 277 nodes · 622 edges · 17 communities detected
- Extraction: 59% EXTRACTED · 41% INFERRED · 0% AMBIGUOUS · INFERRED: 253 edges (avg confidence: 0.69)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]

## God Nodes (most connected - your core abstractions)
1. `Context` - 101 edges
2. `_main_loop()` - 32 edges
3. `_drive_task()` - 26 edges
4. `log()` - 23 edges
5. `run_init()` - 18 edges
6. `run_agent()` - 16 edges
7. `main()` - 15 edges
8. `find_resumable_task()` - 13 edges
9. `run_cmd_output()` - 12 edges
10. `run_cmd()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `_main_loop()` --calls--> `load_epic()`  [INFERRED]
  /Users/navakanth/projects/vibe-agents/shreni/sthapathi.py → /Users/navakanth/projects/vibe-agents/shreni/state.py
- `_main_loop()` --calls--> `save_task()`  [INFERRED]
  /Users/navakanth/projects/vibe-agents/shreni/sthapathi.py → /Users/navakanth/projects/vibe-agents/shreni/state.py
- `Sthapathi (स्थपति) — master orchestrator and CLI entry point.  Usage:     shreni` --uses--> `Context`  [INFERRED]
  /Users/navakanth/projects/vibe-agents/shreni/sthapathi.py → /Users/navakanth/projects/vibe-agents/shreni/context.py
- `IDs of open epics carrying `review:user-review`.      These are under the user's` --uses--> `Context`  [INFERRED]
  /Users/navakanth/projects/vibe-agents/shreni/sthapathi.py → /Users/navakanth/projects/vibe-agents/shreni/context.py
- `Main task-picking loop. Sends completed tasks to the Parikshaka queue.` --uses--> `Context`  [INFERRED]
  /Users/navakanth/projects/vibe-agents/shreni/sthapathi.py → /Users/navakanth/projects/vibe-agents/shreni/context.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (53): emit_event(), _now_iso(), _open_otel_span(), _otel_attr_key(), _otel_kind(), _otel_record_error(), _otel_safe(), Per-task structured spans and events.  Records a JSONL stream of OpenTelemetry-f (+45 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (35): active_parent_ids(), query_tasks(), Beads (bd) task-tracker CLI integration., Return parent IDs of all currently in-progress tasks.      Used to prefer ready, Query tasks using bd query syntax (status/type/assignee etc. — no label: values), Return all open tasks that carry a specific label (e.g. 'review:approved')., review_state(), set_state() (+27 more)

### Community 2 - "Community 2"
Cohesion: 0.1
Nodes (41): breakdown_state(), claim_task(), close_task(), get_comments(), Close a task. Returns True on success, False if bd refused.      Pass force=True, ready_tasks(), show_task(), task_status() (+33 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (33): epic_children(), epic_ready_to_close(), True when an epic has children and every one of them is closed.      Guards agai, Close a task. Returns True on success, False if bd refused.      Pass force=True, Return parent IDs of all currently in-progress tasks.      Used to prefer ready, Return an epic's child tasks (id, status, issue_type, dependency_type each)., Context, Per-task agent log if task_id is given; otherwise the aggregate log. (+25 more)

### Community 4 - "Community 4"
Cohesion: 0.12
Nodes (28): _bd_prefix(), _check_bd_installed(), _check_claude_installed(), _check_dolt_installed(), _check_gh_installed(), _check_graphify_installed(), _check_phoenix_available(), _configure_beads_backup() (+20 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (22): ensure_initialized(), cmd_open(), cmd_start(), cmd_status(), _project_url(), `shreni phoenix` — manage the Arize Phoenix server that receives traces.  Phoeni, Run ``phoenix serve`` in the foreground. Blocks until Ctrl-C., Probe the OTLP endpoint and report whether Phoenix is reachable. (+14 more)

### Community 6 - "Community 6"
Cohesion: 0.33
Nodes (11): _backup_dir(), install(), is_installed(), _marker(), Manage the beads JSONL → GitHub backup cron job (git push every 5 minutes).  Bea, Install (or replace) the bd backup cron entry for this repo., Remove the bd backup cron entry for this repo., _read() (+3 more)

### Community 7 - "Community 7"
Cohesion: 0.21
Nodes (11): dequeue_parikshaka(), enqueue_parikshaka(), load_epic(), load_parikshaka_queue(), _load_parikshaka_queue_raw(), Crash-recovery state files written to the target repo's .claude/ directory., Append a merged task to the persistent Parikshaka queue., Remove a task from the persistent queue after Parikshaka finishes it. (+3 more)

### Community 8 - "Community 8"
Cohesion: 1.0
Nodes (0): 

### Community 9 - "Community 9"
Cohesion: 1.0
Nodes (0): 

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): Crash-recovery file for the in-progress task.

### Community 11 - "Community 11"
Cohesion: 1.0
Nodes (1): Crash-recovery file for an in-progress epic breakdown.

### Community 12 - "Community 12"
Cohesion: 1.0
Nodes (1): Persistent queue of merged tasks awaiting Parikshaka quality checks.

### Community 13 - "Community 13"
Cohesion: 1.0
Nodes (0): 

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (0): 

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (0): 

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **22 isolated node(s):** `Resolve locally installed Claude Code plugins for use in SDK sessions.`, `Return a SdkPluginConfig for a locally installed plugin, or None if not found.`, `Manage the beads JSONL → GitHub backup cron job (git push every 5 minutes).  Bea`, `Install (or replace) the bd backup cron entry for this repo.`, `Remove the bd backup cron entry for this repo.` (+17 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 8`** (2 nodes): `main()`, `install_plugins.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 9`** (1 nodes): `run.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 10`** (1 nodes): `Crash-recovery file for the in-progress task.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 11`** (1 nodes): `Crash-recovery file for an in-progress epic breakdown.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 12`** (1 nodes): `Persistent queue of merged tasks awaiting Parikshaka quality checks.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 13`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 14`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Context` connect `Community 3` to `Community 0`, `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 7`?**
  _High betweenness centrality (0.477) - this node is a cross-community bridge._
- **Why does `_main_loop()` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 7`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `main()` connect `Community 5` to `Community 0`, `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 7`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Are the 96 inferred relationships involving `Context` (e.g. with `Sthapathi (स्थपति) — master orchestrator and CLI entry point.  Usage:     shreni` and `IDs of open epics carrying `review:user-review`.      These are under the user's`) actually correct?**
  _`Context` has 96 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `_main_loop()` (e.g. with `load_epic()` and `log()`) actually correct?**
  _`_main_loop()` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `_drive_task()` (e.g. with `show_task()` and `implement()`) actually correct?**
  _`_drive_task()` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `log()` (e.g. with `_main_loop()` and `main()`) actually correct?**
  _`log()` has 21 INFERRED edges - model-reasoned connections that need verification._