"""AgentScope Compat — lightweight compatibility layer.

Implements the core AgentScope interfaces (AgentBase, Msg, MsgHub) without
requiring the full agentscope package (which pulls in LLM SDKs, vector DBs,
etc.). When the project is ready for production AgentScope, just set:

    RTAS_USE_REAL_AGENTSCOPE=1

and install `pip install agentscope`. The import wrappers will delegate
to the real package transparently.
"""
from __future__ import annotations

import os

_USE_REAL = os.getenv("RTAS_USE_REAL_AGENTSCOPE", "0") == "1"

if _USE_REAL:
    try:
        from agentscope.agent import AgentBase
        from agentscope.message import Msg
        from agentscope.pipeline import MsgHub

        _REAL_AVAILABLE = True
    except ImportError:
        _REAL_AVAILABLE = False
        import warnings
        warnings.warn(
            "RTAS_USE_REAL_AGENTSCOPE=1 but agentscope not installed, "
            "falling back to compat layer",
            stacklevel=2,
        )

if not _USE_REAL or not _REAL_AVAILABLE:
    from ._agent_base import AgentBase
    from ._msg import Msg
    from ._msghub import MsgHub

__all__ = ["AgentBase", "Msg", "MsgHub"]
