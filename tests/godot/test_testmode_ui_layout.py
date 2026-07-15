from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_testmode_ui_controller_exists() -> None:
    path = ROOT / "godot/scripts/test_mode_ui_controller.gd"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "class_name TestModeUIController" in text
    assert "ModeSidebar" in text
    assert "FilterPanel" in text


def test_gallery_uses_world_safe_area_constants() -> None:
    text = (ROOT / "godot/scripts/test_mode_gallery.gd").read_text(encoding="utf-8")
    assert "TESTMODE_WORLD_ORIGIN" in text
    assert "TESTMODE_WORLD_RIGHT_LIMIT" in text
    assert "TESTMODE_WORLD_BOTTOM_LIMIT" in text
