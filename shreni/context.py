from dataclasses import dataclass
from pathlib import Path

from .shell import slugify


@dataclass
class Context:
    """Runtime context shared across all modules.

    Created once in the orchestrator after CLI args are parsed and passed
    explicitly to every function that needs it — no global state.
    """

    repo_root: Path       # The target git repository being worked on
    project_name: str     # Human-readable project name (for agent prompts)
    agents_dir: Path      # Directory containing silpi/, viharapala/ folders
    idle_interval: int = 120  # Seconds to sleep when no tasks are ready

    # ── Crash-recovery state (kept in the target repo) ───────────────────────

    @property
    def task_state_file(self) -> Path:
        """Crash-recovery file for the in-progress task."""
        return self.repo_root / ".claude" / "current-task.json"

    @property
    def epic_breakdown_file(self) -> Path:
        """Crash-recovery file for an in-progress epic breakdown."""
        return self.repo_root / ".claude" / "epic-breakdown.json"

    @property
    def parikshaka_queue_file(self) -> Path:
        """Persistent queue of merged tasks awaiting Parikshaka quality checks."""
        return self.repo_root / ".claude" / "parikshaka-queue.json"

    # ── Observability (kept in the user's home directory) ────────────────────
    #
    # Layout:
    #   ~/.shreni/projects/<slug>/
    #     <agent>.log              ← cross-task aggregate (legacy / tmux-friendly)
    #     session-spans.jsonl      ← orchestrator-level events (no task context)
    #     tasks/
    #       <task_id>/
    #         spans.jsonl          ← structured span stream for this task
    #         <agent>.log          ← per-task raw agent output

    @property
    def project_slug(self) -> str:
        return slugify(self.project_name)

    @property
    def shreni_home(self) -> Path:
        return Path.home() / ".shreni"

    @property
    def project_obs_dir(self) -> Path:
        return self.shreni_home / "projects" / self.project_slug

    @property
    def session_spans_file(self) -> Path:
        return self.project_obs_dir / "session-spans.jsonl"

    def task_obs_dir(self, task_id: str) -> Path:
        return self.project_obs_dir / "tasks" / task_id

    def task_spans_file(self, task_id: str) -> Path:
        return self.task_obs_dir(task_id) / "spans.jsonl"

    def agent_log_file(self, agent_name: str, task_id: str | None = None) -> Path:
        """Per-task agent log if task_id is given; otherwise the aggregate log."""
        if task_id:
            return self.task_obs_dir(task_id) / f"{agent_name}.log"
        return self.project_obs_dir / f"{agent_name}.log"
