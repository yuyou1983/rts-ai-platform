from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_game_view_has_test_mode_isolation_hook() -> None:
    text = (ROOT / "godot/scripts/game_view.gd").read_text(encoding="utf-8")
    assert "func _set_test_mode_isolation" in text
    assert "_set_test_mode_isolation(" in text


def test_hud_overlay_has_isolation_api() -> None:
    text = (ROOT / "godot/scripts/hud_overlay_renderer.gd").read_text(encoding="utf-8")
    assert "func set_test_mode_isolation" in text
    assert "func is_test_mode_isolation" in text


def test_isolation_toggles_visibility() -> None:
    text = (ROOT / "godot/scripts/game_view.gd").read_text(encoding="utf-8")
    assert "_hud.visible" in text or "_hud" in text
    assert "_mm_rect_node.visible" in text or "_mm_rect_node" in text
