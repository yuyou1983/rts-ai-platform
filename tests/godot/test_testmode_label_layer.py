from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_testmode_label_layer_exists() -> None:
    text = (ROOT / "godot/scripts/test_mode_label_layer.gd").read_text(encoding="utf-8")
    assert "class_name TestModeLabelLayer" in text
    assert "func set_labels" in text
    assert "func _draw" in text


def test_gallery_exposes_screen_labels() -> None:
    text = (ROOT / "godot/scripts/test_mode_gallery.gd").read_text(encoding="utf-8")
    assert "func get_screen_labels" in text
