#!/usr/bin/env python3
"""Tests for domain context glossaries."""
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CONTEXT_MAP = REPO / "CONTEXT-MAP.md"
DOMAIN_DIR = REPO / "docs" / "domain"

REQUIRED_TERMS = {
    "simcore-context.md": ["Authoritative Game State", "CombatEvent", "Determinism", "Production Entity"],
    "godot-presentation-context.md": ["Presentation State", "CombatVisualController", "Test Mode Fixture", "Visual Manifest"],
    "skill-harness-context.md": ["SkillTrial", "Candidate Patch", "Silent Bypass", "Held-out Trial", "Promotion"],
    "sc1-source-truth-context.md": ["Effective MPQ Overlay", "Semantic Weapon ID", "Reference Artifact", "Presentation Asset"],
}

def test_context_map_exists():
    assert CONTEXT_MAP.exists(), "CONTEXT-MAP.md not found"

def test_context_map_references_all_four():
    content = CONTEXT_MAP.read_text()
    for name in REQUIRED_TERMS:
        assert name in content, f"CONTEXT-MAP.md does not reference {name}"

class TestGlossaries:
    @pytest.mark.parametrize("filename,terms", REQUIRED_TERMS.items())
    def test_glossary_exists(self, filename, terms):
        assert (DOMAIN_DIR / filename).exists(), f"{filename} not found"

    @pytest.mark.parametrize("filename,terms", REQUIRED_TERMS.items())
    def test_required_terms_present(self, filename, terms):
        content = (DOMAIN_DIR / filename).read_text()
        for term in terms:
            assert term in content, f"{filename} missing term '{term}'"

    @pytest.mark.parametrize("filename,terms", REQUIRED_TERMS.items())
    def test_entries_use_canonical_shape(self, filename, terms):
        content = (DOMAIN_DIR / filename).read_text()
        assert "Definition:" in content, f"{filename} must use 'Definition:' format"
        assert "Not the same as:" in content, f"{filename} must use 'Not the same as:' format"
        assert "Boundary example:" in content, f"{filename} must use 'Boundary example:' format"
