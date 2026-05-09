#!/usr/bin/env python3
"""Code quality linter for RTS-AI-Platform.

Checks for common code quality issues that Ruff doesn't catch.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

warnings = 0


def check_file(filepath: Path, root: Path) -> None:
    """Check a single Python file for quality issues."""
    global warnings
    rel = filepath.relative_to(root)

    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return

    # Check 1: No bare except clauses
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            print(f"⚠ {rel}:{node.lineno} — "
                  f"bare `except:` catches everything (use specific exception)")
            warnings += 1

    # Check 2: No TODO without issue reference
    for i, line in enumerate(source.splitlines(), 1):
        if re.search(r"#\s*TODO(?!\(#?\d+\))", line, re.IGNORECASE):
            print(f"⚠ {rel}:{i} — TODO without issue reference (use TODO(#123))")
            warnings += 1

    # Check 3: No print() in non-test files
    if "tests" not in rel.parts:
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"):
                # Allow print in __main__ blocks
                print(f"⚠ {rel}:{node.lineno} — print() found (use logging instead)")
                warnings += 1


def main() -> None:
    root = Path.cwd()
    dirs = sys.argv[1:] or ["simcore", "agents"]

    for d in dirs:
        path = root / d
        if not path.is_dir():
            continue
        for py_file in path.rglob("*.py"):
            check_file(py_file, root)

    if warnings:
        print(f"\n⚠ {warnings} quality warning(s)")
    else:
        print("✓ Quality checks passed")


if __name__ == "__main__":
    main()
