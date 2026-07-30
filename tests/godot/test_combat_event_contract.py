"""Task 6: Static contract test for Godot combat event pipeline.

Verifies that game_view.gd passes combat_events to CombatVisualController,
and that the controller no longer relies on HP-delta inference.
"""
from __future__ import annotations

from pathlib import Path

import pytest

GODOT_DIR = Path(__file__).parent.parent.parent / "godot" / "scripts"


def _read_script(name: str) -> str:
    path = GODOT_DIR / name
    if not path.exists():
        pytest.fail(f"{name} not found at {path}")
    return path.read_text()


class TestCombatEventContract:
    """Static assertions on GDScript source for combat event pipeline."""

    def test_game_view_passes_combat_events(self):
        """game_view.gd must pass combat_events from state to controller."""
        src = _read_script("game_view.gd")
        assert 'combat_events' in src, \
            "game_view.gd must reference 'combat_events' from state"
        assert 'process_combat_events' in src, \
            "game_view.gd must call process_combat_events on the controller"

    def test_controller_has_process_combat_events(self):
        """CombatVisualController must expose process_combat_events."""
        src = _read_script("combat_visual_controller.gd")
        assert 'func process_combat_events' in src, \
            "CombatVisualController must have process_combat_events function"

    def test_controller_has_current_action_for(self):
        """CombatVisualController must expose current_action_for."""
        src = _read_script("combat_visual_controller.gd")
        assert 'func current_action_for' in src, \
            "CombatVisualController must have current_action_for function"

    def test_controller_has_clear_seen_events(self):
        """CombatVisualController must expose clear_seen_events."""
        src = _read_script("combat_visual_controller.gd")
        assert 'func clear_seen_events' in src, \
            "CombatVisualController must have clear_seen_events function"

    def test_controller_has_seen_event_ids(self):
        """Controller must have _seen_event_ids dedup cache."""
        src = _read_script("combat_visual_controller.gd")
        assert '_seen_event_ids' in src, \
            "CombatVisualController must have _seen_event_ids for dedup"

    def test_controller_no_attack_cooldown_inference(self):
        """Controller must NOT rely on attack_cooldown for event generation."""
        src = _read_script("combat_visual_controller.gd")
        # The old HP-delta approach should be gone or feature-flagged off
        assert 'attack_cooldown' not in src, \
            "CombatVisualController must not use attack_cooldown for event inference"

    def test_controller_no_shield_inference(self):
        """Controller must NOT infer shield hit events from shield deltas."""
        src = _read_script("combat_visual_controller.gd")
        # Remove the old 'cur.get("shield"' pattern — replaced by event-driven
        assert 'cur.get("shield"' not in src, \
            "CombatVisualController must not infer shield hits from entity state"

    def test_game_view_uses_current_action_for(self):
        """game_view.gd must use current_action_for for animation key."""
        src = _read_script("game_view.gd")
        assert 'current_action_for' in src, \
            "game_view.gd must call current_action_for for animation lookup"
