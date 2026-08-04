#!/usr/bin/env python3
"""Contract tests for sprint-plan and harness-run skills."""
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

SPRINT_PLAN = REPO / ".agents" / "skills" / "sprint-plan" / "SKILL.md"
HARNESS_RUN = REPO / ".agents" / "skills" / "harness-run" / "SKILL.md"

class TestSprintPlanContract:
    def test_file_exists(self):
        assert SPRINT_PLAN.exists()

    def test_contains_vertical_slice(self):
        content = SPRINT_PLAN.read_text()
        assert "vertical slice" in content.lower()

    def test_contains_blocked_by(self):
        content = SPRINT_PLAN.read_text()
        assert "blocked_by" in content or "blocked by" in content.lower()

    def test_contains_verification_seams(self):
        content = SPRINT_PLAN.read_text()
        assert "verification_seams" in content or "verification seam" in content.lower()

    def test_contains_evidence_outputs(self):
        content = SPRINT_PLAN.read_text()
        assert "evidence_outputs" in content or "evidence output" in content.lower()

    def test_ticket_format_has_required_fields(self):
        content = SPRINT_PLAN.read_text()
        for field in ["Status:", "Blocked by:", "Source specification:", "What it delivers:", "Acceptance criteria:", "Verification seams:", "Evidence outputs:", "Owner skill:"]:
            assert field in content, f"Missing ticket field: {field}"

class TestHarnessRunContract:
    def test_file_exists(self):
        assert HARNESS_RUN.exists()

    def test_contains_red_capable(self):
        content = HARNESS_RUN.read_text()
        assert "red" in content.lower() and "capable" in content.lower()

    def test_contains_minimise(self):
        content = HARNESS_RUN.read_text()
        assert "minimise" in content.lower() or "minimize" in content.lower()

    def test_contains_one_hypothesis(self):
        content = HARNESS_RUN.read_text()
        assert "one hypothesis" in content.lower() or "hypothesis at a time" in content.lower()

    def test_contains_regression(self):
        content = HARNESS_RUN.read_text()
        assert "regression" in content.lower()

    def test_contains_handoff(self):
        content = HARNESS_RUN.read_text()
        assert "handoff" in content.lower()

    def test_execution_order_present(self):
        content = HARNESS_RUN.read_text()
        # Check for the tight feedback loop steps
        assert "Read source specification" in content or "source specification" in content.lower()
        assert "Reproduce" in content or "reproduce" in content.lower()
        assert "smallest fix" in content.lower() or "minimal fix" in content.lower()
