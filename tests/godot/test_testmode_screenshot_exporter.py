from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_screenshot_exporter_exists() -> None:
    path = ROOT / "godot/scripts/testmode_screenshot_exporter.gd"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "class_name TestmodeScreenshotExporter" in text
    assert "func export_all_modes" in text


def test_gallery_has_pagination() -> None:
    text = (ROOT / "godot/scripts/test_mode_gallery.gd").read_text(encoding="utf-8")
    assert "TESTMODE_ITEMS_PER_PAGE" in text
    assert "_test_page" in text
    assert "_prev_page_btn" in text or "_on_prev_page" in text
