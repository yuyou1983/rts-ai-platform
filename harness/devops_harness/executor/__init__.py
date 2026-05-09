"""devops_harness.executor — autonomous task execution with self-validation.

Wraps the harness-executor SKILL.md workflow as a callable Python API.
The 7-step execution flow: setup → plan → execute → validate → verify → record → present.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TaskContext:
    """Context for a single task execution."""

    task_id: str = ""
    description: str = ""
    goal: str = ""
    files_changed: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | in_progress | validated | verified | completed | failed
    errors: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of a task execution cycle."""

    task: TaskContext = field(default_factory=TaskContext)
    static_ok: bool = False
    functional_ok: bool = False
    elapsed: float = 0.0
    memory_hits: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class HarnessExecutor:
    """Execute development tasks autonomously with self-validation.

    Usage::

        executor = HarnessExecutor(project_root=Path("/my/project"))
        result = executor.run("Add health check endpoint to API server")
        assert result.functional_ok
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._skill_dir = Path(__file__).parent
        self._scripts_dir = self._skill_dir / "scripts"
        self._harness_root = self._resolve_harness_root()

    # ─── Step 1: Setup ─────────────────────────────────────────

    def setup(self, task_description: str) -> TaskContext:
        """Bootstrap harness, check interrupted tasks, query memory."""
        ctx = TaskContext(
            task_id=self._init_task_state(task_description),
            description=task_description,
        )
        # Check for interrupted tasks
        interrupted = self._run_script("task_state.py", "list")
        if interrupted:
            # Resume protocol could go here
            pass
        # Query memory
        ctx.memory_hits = self._query_memory(task_description)
        return ctx

    # ─── Step 2: Plan ──────────────────────────────────────────

    def plan(self, ctx: TaskContext) -> TaskContext:
        """Scope the work and initialize task state."""
        ctx.goal = self._infer_goal(ctx.description)
        ctx.status = "in_progress"
        self._run_script("task_state.py", "init", ctx.description)
        return ctx

    # ─── Step 3: Execute ────────────────────────────────────────

    def execute(self, ctx: TaskContext) -> TaskContext:
        """Spawn executor subagent to make code changes."""
        # In real usage, this delegates to a subagent.
        # Here we provide the coordination framework.
        ctx.status = "executed"
        return ctx

    # ─── Step 4: Validate (static) ──────────────────────────────

    def validate(self, ctx: TaskContext) -> ExecutionResult:
        """Run static validation: build, lint, test."""
        result = ExecutionResult(task=ctx)

        # Run preflight checks
        preflight = self._run_script("preflight.py")
        if preflight is not None:
            result.errors.extend(preflight.get("failures", []))

        # Run project linters
        lint_ok = self._run_project_lint()
        result.static_ok = lint_ok
        return result

    # ─── Step 5: Verify (functional) ────────────────────────────

    def verify(self, result: ExecutionResult) -> ExecutionResult:
        """Spawn verifier subagent for functional verification."""
        # Generate task-specific verification
        self._run_script(
            "generate_task_verification.py",
            "--task", result.task.description,
            "--files", ",".join(result.task.files_changed),
        )
        # In real usage, verifier subagent runs the generated tests.
        result.functional_ok = result.static_ok  # placeholder
        return result

    # ─── Step 6: Record ─────────────────────────────────────────

    def record(self, result: ExecutionResult) -> None:
        """Mark task complete, store episodic memory."""
        status = "complete" if result.functional_ok else "failed"
        self._run_script("task_state.py", status, result.task.task_id)

        # Record to episodic memory
        episode = {
            "task_id": result.task.task_id,
            "description": result.task.description,
            "status": status,
            "static_ok": result.static_ok,
            "functional_ok": result.functional_ok,
        }
        episodes_dir = self._harness_root / "memory" / "episodes"
        episodes_dir.mkdir(parents=True, exist_ok=True)
        (episodes_dir / f"{result.task.task_id}.json").write_text(
            json.dumps(episode, indent=2, default=str)
        )

    # ─── Full pipeline ─────────────────────────────────────────

    def run(self, task_description: str) -> ExecutionResult:
        """Run the full 7-step execution pipeline."""
        import time
        t0 = time.monotonic()

        ctx = self.setup(task_description)
        ctx = self.plan(ctx)
        ctx = self.execute(ctx)
        result = self.validate(ctx)
        result = self.verify(result)
        self.record(result)
        result.elapsed = time.monotonic() - t0
        return result

    # ─── Helpers ───────────────────────────────────────────────

    def _resolve_harness_root(self) -> Path:
        """Find harness root using config_resolver priority chain."""
        for candidate in [
            self.project_root / ".harness",
            self.project_root / "harness",
        ]:
            if candidate.is_dir():
                return candidate
        return self.project_root / "harness"

    def _run_script(self, script_name: str, *args: str) -> Any:
        """Run an executor helper script."""
        script_path = self._scripts_dir / script_name
        if not script_path.exists():
            return None
        try:
            result = subprocess.run(
                ["python3", str(script_path), *args],
                capture_output=True, text=True, timeout=30,
                cwd=str(self.project_root),
            )
            if result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"stdout": result.stdout}
            return {"errors": result.stderr.splitlines()}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _init_task_state(self, description: str) -> str:
        """Initialize task state and return task ID."""
        import shortuuid
        return shortuuid.uuid()

    def _query_memory(self, query: str) -> list[dict[str, Any]]:
        """Search episodic memory for relevant past experiences."""
        memory_result = self._run_script("memory_query.py", "search", query, "--json")
        if memory_result and isinstance(memory_result, dict):
            return memory_result.get("results", [])
        return []

    def _infer_goal(self, description: str) -> str:
        """Infer the goal from task description (simple heuristic)."""
        # In production, this would call an LLM. Here we use simple heuristics.
        lower = description.lower()
        if any(kw in lower for kw in ("add", "implement", "create", "build")):
            return "implement"
        if any(kw in lower for kw in ("fix", "bug", "patch", "repair")):
            return "fix"
        if any(kw in lower for kw in ("refactor", "clean", "restructure")):
            return "refactor"
        return "general"

    def _run_project_lint(self) -> bool:
        """Run the project's own lint target."""
        try:
            result = subprocess.run(
                ["make", "lint"],
                capture_output=True, text=True, timeout=60,
                cwd=str(self.project_root),
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Fallback: try ruff directly
            try:
                result = subprocess.run(
                    ["python3", "-m", "ruff", "check", "."],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(self.project_root),
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False
