#!/usr/bin/env bash
# Run pytest with the project's standard options.
# Usage: scripts/run_tests.sh [test_path ...]
# If no paths given, runs the full suite.
set -euo pipefail

cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo .)"

PYTHONPATH=harness:. python3 -m pytest "$@" -q -n 4