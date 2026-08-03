#!/usr/bin/env python3
"""DEPRECATED: Use scripts/audit_sc1_combat_data.py instead.

This script is superseded by the effective-DAT audit pipeline.
It remains as a compatibility shim that redirects to the new auditor.
"""
import sys
import warnings

warnings.warn(
    "audit_combat_reference.py is deprecated. Use scripts/audit_sc1_combat_data.py.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export key functions from the new auditor for any legacy callers
from scripts.audit_sc1_combat_data import (  # noqa: E402,F401
    load_effective_dat,
    resolve_effective_weapon,
    build_reference,
)

if __name__ == "__main__":
    print("This script is deprecated. Run: python3 scripts/audit_sc1_combat_data.py --write-reference --write-report")
    sys.exit(0)
