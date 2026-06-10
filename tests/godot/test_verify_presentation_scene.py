from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts/verify_presentation_scene.py"


def _load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_presentation_scene", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_check_handles_nested_abstract_unit_mappings() -> None:
    verifier = _load_verify_module()

    issues = verifier.check_manifest()

    assert isinstance(issues, list)
