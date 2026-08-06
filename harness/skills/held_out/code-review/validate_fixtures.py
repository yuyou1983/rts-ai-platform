#!/usr/bin/env python3
"""Validate the concrete code-review held-out fixture contract."""
from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_AXES = {"Standards", "Specification", "Source Truth"}


def validate() -> list[str]:
    issues: list[str] = []
    fixture_dirs = sorted(path for path in FIXTURES_DIR.iterdir() if path.is_dir())
    if len(fixture_dirs) != 2:
        issues.append(f"expected exactly two code-review fixtures, found {len(fixture_dirs)}")

    for fixture_dir in fixture_dirs:
        for filename in ("spec.md", "change.diff", "expected.json"):
            path = fixture_dir / filename
            if not path.is_file() or not path.read_text(encoding="utf-8").strip():
                issues.append(f"missing or empty fixture file: {path}")
        expected_path = fixture_dir / "expected.json"
        if expected_path.is_file():
            expected = json.loads(expected_path.read_text(encoding="utf-8"))
            if set(expected) != EXPECTED_AXES:
                issues.append(
                    f"{expected_path}: expected axes {sorted(EXPECTED_AXES)}, "
                    f"found {sorted(expected)}"
                )
    return issues


def main() -> int:
    issues = validate()
    if issues:
        for issue in issues:
            print(f"FAIL: {issue}")
        return 1
    print("OK - code-review held-out fixtures are complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
