#!/usr/bin/env python3
"""Tests for held-out suite coverage and quality."""
import json
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HELD_OUT_DIR = REPO / "harness" / "skills" / "held_out"
REGISTRY_PATH = REPO / "harness" / "skills" / "registry.json"

def test_registered_skill_count():
    reg = json.loads(REGISTRY_PATH.read_text())
    assert len(reg) == 24

def test_held_out_skill_count():
    reg = json.loads(REGISTRY_PATH.read_text())
    covered = [e for e in reg if e.get("held_out_suite")]
    assert len(covered) >= 12

def test_coverage_ratio():
    reg = json.loads(REGISTRY_PATH.read_text())
    covered = [e for e in reg if e.get("held_out_suite")]
    assert len(covered) / len(reg) >= 0.50

class TestSuiteQuality:
    def _suites(self):
        suites = []
        for path in HELD_OUT_DIR.rglob("suite.json"):
            if path.parent.name == "held_out":
                continue
            data = json.loads(path.read_text())
            suites.append((path.parent.name, data))
        return suites

    def test_every_suite_has_at_least_two_scenarios(self):
        for name, suite in self._suites():
            assert len(suite.get("scenarios", [])) >= 2, f"{name}: needs >= 2 scenarios"

    def test_scenario_ids_are_unique(self):
        for name, suite in self._suites():
            ids = [s["id"] for s in suite.get("scenarios", [])]
            assert len(ids) == len(set(ids)), f"{name}: duplicate scenario IDs"

    def test_scenario_ids_prefixed(self):
        for name, suite in self._suites():
            for s in suite.get("scenarios", []):
                assert s["id"].startswith("held-out/"), f"{name}/{s['id']}: ID must start with held-out/"

    def test_every_scenario_has_validation_command(self):
        for name, suite in self._suites():
            for s in suite.get("scenarios", []):
                assert len(s.get("validation_commands", [])) >= 1, f"{name}/{s['id']}: needs validation command"

    def test_every_scenario_has_pass_criteria(self):
        for name, suite in self._suites():
            for s in suite.get("scenarios", []):
                assert "pass_criteria" in s, f"{name}/{s['id']}: needs pass_criteria"

    def test_no_existence_only_checks(self):
        """No scenario should rely solely on file existence or import checks."""
        for name, suite in self._suites():
            for s in suite.get("scenarios", []):
                cmds = s.get("validation_commands", [])
                for cmd in cmds:
                    cmd_lower = cmd.lower()
                    # File existence alone is not behavioral
                    if cmd_lower.startswith("test -f") or cmd_lower.startswith("ls "):
                        assert len(cmds) > 1, f"{name}/{s['id']}: relies solely on existence check"

    def test_validate_held_out_suites_script_passes(self):
        import subprocess
        result = subprocess.run(
            ["python3", "harness/skills/validate_held_out_suites.py"],
            capture_output=True, text=True, cwd=str(REPO)
        )
        assert result.returncode == 0, f"validate_held_out_suites.py failed:\n{result.stdout}\n{result.stderr}"
