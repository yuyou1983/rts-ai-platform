#!/bin/bash
# Wrapper: ensures project venv python3 is used when Godot calls py_bridge.py
# Godot calls: run_bridge.sh <address> <method> <json_params>
cd "$(dirname "$0")/../../"
# Use the same python3 that can import simcore
exec python3 godot/scripts/py_bridge.py "$@"