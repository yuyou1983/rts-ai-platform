#!/usr/bin/env python3
"""Architecture dependency linter for RTS-AI-Platform.

Enforces four-layer import constraints:
  L0 (proto/) → nothing
  L1 (simcore/) → L0 only
  L2 (agents/) → L0, L1
  L3 (godot/) → L0, L1, L2

Usage:
  python3 scripts/lint_deps.py [dirs...]
  python3 scripts/lint_deps.py simcore/ agents/ proto/
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

LAYERS = {
    "proto": 0,
    "simcore": 1,
    "agents": 2,
    "godot": 3,
}

FORBIDDEN = {
    0: {"simcore", "agents", "godot"},
    1: {"agents", "godot"},
    2: {"godot"},
    3: set(),
}

errors = 0


def get_layer(filepath: Path, root: Path) -> int | None:
    """Determine which architecture layer a file belongs to."""
    try:
        rel = filepath.relative_to(root)
        parts = rel.parts
        if parts:
            top = parts[0]
            return LAYERS.get(top)
    except ValueError:
        pass
    return None


def check_file(filepath: Path, root: Path) -> None:
    """Check a single Python file for forbidden imports."""
    global errors
    file_layer = get_layer(filepath, root)
    if file_layer is None:
        return

    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return

    forbidden = FORBIDDEN.get(file_layer, set())

    for node in ast.walk(tree):
        # import X
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                mod_layer = LAYERS.get(mod)
                if mod_layer is not None and mod in forbidden:
                    print(
                        f"❌ {filepath.relative_to(root)}:{node.lineno} "
                        f"imports {alias.name} (L{mod_layer}) "
                        f"from L{file_layer} — forbidden"
                    )
                    errors += 1
        # from X import Y
        elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.split(".")[0]
                mod_layer = LAYERS.get(mod)
                if mod_layer is not None and mod in forbidden:
                    print(
                        f"❌ {filepath.relative_to(root)}:{node.lineno} "
                        f"from {node.module} (L{mod_layer}) "
                        f"in L{file_layer} — forbidden"
                    )
                    errors += 1


def main() -> None:
    root = Path.cwd()
    dirs = sys.argv[1:] or ["simcore", "agents", "proto"]

    for d in dirs:
        path = root / d
        if not path.is_dir():
            continue
        for py_file in path.rglob("*.py"):
            check_file(py_file, root)

    if errors:
        print(f"\n❌ {errors} architecture violation(s) found")
        sys.exit(1)
    else:
        print("✓ Architecture checks passed")


if __name__ == "__main__":
    main()
