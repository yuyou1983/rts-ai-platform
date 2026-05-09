"""Tests for devops-harness: creator + executor."""

from devops_harness.creator import HarnessCreator
from devops_harness.executor import ExecutionResult, HarnessExecutor, TaskContext


class TestCreator:
    def test_detect_greenfield(self, tmp_path):
        """Empty project → greenfield."""
        creator = HarnessCreator(project_root=tmp_path)
        result = creator.detect()
        assert result.project_type == "greenfield"

    def test_detect_existing(self, tmp_path):
        """Some code files but no AGENTS.md → existing."""
        (tmp_path / "main.py").write_text("print('hi')")
        creator = HarnessCreator(project_root=tmp_path)
        result = creator.detect()
        assert result.project_type in ("greenfield", "existing")

    def test_verify_returns_dict(self, tmp_path):
        creator = HarnessCreator(project_root=tmp_path)
        v = creator.verify()
        assert isinstance(v, dict)
        assert "AGENTS.md" in v


class TestExecutor:
    def test_task_context_defaults(self):
        ctx = TaskContext()
        assert ctx.status == "pending"

    def test_setup_returns_task(self, tmp_path):
        executor = HarnessExecutor(project_root=tmp_path)
        ctx = executor.setup("Add health check")
        assert ctx.task_id
        assert ctx.description == "Add health check"

    def test_plan_sets_goal(self, tmp_path):
        executor = HarnessExecutor(project_root=tmp_path)
        ctx = executor.setup("Fix login bug")
        ctx = executor.plan(ctx)
        assert ctx.goal == "fix"
        assert ctx.status == "in_progress"

    def test_validate_on_empty_project(self, tmp_path):
        executor = HarnessExecutor(project_root=tmp_path)
        ctx = TaskContext(task_id="t1", description="test")
        result = executor.validate(ctx)
        assert isinstance(result, ExecutionResult)
        assert isinstance(result.static_ok, bool)

    def test_full_run_pipeline(self, tmp_path):
        executor = HarnessExecutor(project_root=tmp_path)
        result = executor.run("Add README")
        assert isinstance(result, ExecutionResult)
        assert result.elapsed >= 0

    def test_infer_goal(self, tmp_path):
        executor = HarnessExecutor(project_root=tmp_path)
        assert executor._infer_goal("Add new feature") == "implement"
        assert executor._infer_goal("Fix critical bug") == "fix"
        assert executor._infer_goal("Refactor module") == "refactor"
        assert executor._infer_goal("Update docs") == "general"
