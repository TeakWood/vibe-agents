from dataclasses import dataclass
from pathlib import Path


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
