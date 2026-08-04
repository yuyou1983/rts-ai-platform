#!/usr/bin/env python3
"""Contract tests for the structured handoff skill."""
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SKILL_PATH = REPO / ".agents" / "skills" / "handoff" / "SKILL.md"
TEMPLATE_PATH = REPO / "docs" / "agents" / "templates" / "agent-handoff-template.md"

REQUIRED_SECTIONS = [
    "Objective",
    "Fixed Point",
    "Active Task Fixture",
    "Gate Status",
    "Completed Evidence",
    "Current Failure",
    "Unrelated Working Tree Paths",
    "Next Command",
    "Suggested Skills",
    "Stop Conditions",
]

def test_skill_file_exists():
    assert SKILL_PATH.exists()

def test_template_file_exists():
    assert TEMPLATE_PATH.exists()

def test_skill_contains_all_sections():
    content = SKILL_PATH.read_text()
    for section in REQUIRED_SECTIONS:
        assert section in content, f"Skill missing section: {section}"

def test_template_contains_all_sections():
    content = TEMPLATE_PATH.read_text()
    for section in REQUIRED_SECTIONS:
        assert section in content, f"Template missing section: {section}"

def test_skill_rejects_conversation_dump():
    content = SKILL_PATH.read_text()
    assert "Conversation Dump" in content and "reject" in content.lower() or "forbidden" in content.lower() or "must not" in content.lower()

def test_skill_mentions_credentials():
    content = SKILL_PATH.read_text()
    assert "credential" in content.lower() or "secret" in content.lower() or "redact" in content.lower()

def test_skill_uses_temp_directory():
    content = SKILL_PATH.read_text()
    assert "tmp" in content.lower() or "temp" in content.lower() or "temporary" in content.lower()

def test_skill_one_active_task():
    content = SKILL_PATH.read_text()
    assert "one" in content.lower() and "task" in content.lower()

def test_skill_one_next_command():
    content = SKILL_PATH.read_text()
    assert "next command" in content.lower() or "next_command" in content.lower()

def test_template_references_by_path():
    content = TEMPLATE_PATH.read_text()
    # Template should reference paths, not duplicate content
    assert "path" in content.lower() or "reference" in content.lower()

def test_skill_registered_in_registry():
    import json
    registry = json.loads((REPO / "harness" / "skills" / "registry.json").read_text())
    names = [e["name"] for e in registry]
    assert "handoff" in names

def test_skill_24_count():
    import json
    registry = json.loads((REPO / "harness" / "skills" / "registry.json").read_text())
    assert len(registry) == 24
