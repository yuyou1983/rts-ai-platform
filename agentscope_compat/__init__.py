"""AgentScope Compat — lightweight compatibility layer.

Implements the core AgentScope interfaces (AgentBase, Msg, MsgHub) without
requiring the full agentscope package (which pulls in LLM SDKs, vector DBs,
etc.).

Three import strategies (tried in order):

1. **RTAS_USE_REAL_AGENTSCOPE=1** — import from the fully-installed
   ``agentscope`` package (``pip install agentscope``).
2. **Auto-detect local clone** — if ``~/code/agentscope/src`` exists,
   add it to ``sys.path`` and import the three sub-modules directly,
   bypassing the heavy top-level ``agentscope/__init__.py``.
3. **Local shim** — use the lightweight implementations shipped in
   this package (``_agent_base``, ``_msg``, ``_msghub``).
"""
from __future__ import annotations

import importlib
import os
import sys
import warnings
from pathlib import Path

_USE_REAL = os.getenv("RTAS_USE_REAL_AGENTSCOPE", "0") == "1"
_LOCAL_CLONE_SRC = Path.home() / "code" / "agentscope" / "src"

# ---------------------------------------------------------------------------
# Strategy 1: fully-installed agentscope package
# ---------------------------------------------------------------------------
if _USE_REAL:
    try:
        from agentscope.agent import AgentBase  # type: ignore[import-untyped]
        from agentscope.message import Msg  # type: ignore[import-untyped]
        from agentscope.pipeline import MsgHub  # type: ignore[import-untyped]

        _REAL_AVAILABLE = True
    except ImportError:
        _REAL_AVAILABLE = False
        warnings.warn(
            "RTAS_USE_REAL_AGENTSCOPE=1 but agentscope not importable, "
            "falling back to compat layer",
            stacklevel=2,
        )

# ---------------------------------------------------------------------------
# Strategy 2: local clone at ~/code/agentscope/src — bypass heavy __init__
# ---------------------------------------------------------------------------
if not _USE_REAL or not _REAL_AVAILABLE:
    _LOCAL_AVAILABLE = False
    if _LOCAL_CLONE_SRC.is_dir() and str(_LOCAL_CLONE_SRC) not in sys.path:
        # Insert at front so sub-module imports take priority
        sys.path.insert(0, str(_LOCAL_CLONE_SRC))
        try:
            # Import ONLY the three leaf modules we need — this skips
            # agentscope/__init__.py which drags in model/LLM deps.
            # Note: even leaf modules have transitive deps (json_repair,
            # shortuuid, etc.), so this may still fail.  That's fine —
            # we'll fall back to the local shim gracefully.
            _agent_mod = importlib.import_module("agentscope.agent._agent_base")
            _msg_mod = importlib.import_module("agentscope.message._message_base")
            _hub_mod = importlib.import_module("agentscope.pipeline._msghub")

            AgentBase = _agent_mod.AgentBase  # type: ignore[assignment]
            Msg = _msg_mod.Msg  # type: ignore[assignment]
            MsgHub = _hub_mod.MsgHub  # type: ignore[assignment]
            _LOCAL_AVAILABLE = True
        except Exception:
            # Remove from path if import failed
            if str(_LOCAL_CLONE_SRC) in sys.path:
                sys.path.remove(str(_LOCAL_CLONE_SRC))

# ---------------------------------------------------------------------------
# Strategy 3: local shim (always available)
# ---------------------------------------------------------------------------
if not _USE_REAL or not _REAL_AVAILABLE:
    if not _LOCAL_AVAILABLE:
        from ._agent_base import AgentBase  # type: ignore[assignment]
        from ._msg import Msg  # type: ignore[assignment]
        from ._msghub import MsgHub  # type: ignore[assignment]


def is_upstream_loaded() -> bool:
    """Return True if the real agentscope symbols are being used."""
    return _USE_REAL and _REAL_AVAILABLE


__all__ = ["AgentBase", "Msg", "MsgHub", "is_upstream_loaded"]
