"""Msg — compatible with AgentScope's message format."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal

import shortuuid


class Msg:
    """A message object compatible with AgentScope's Msg class.

    Attributes:
        name: Sender name.
        content: Text content or list of content blocks.
        role: One of "user", "assistant", "system".
        metadata: Optional dict for structured data (e.g. commands, observations).
    """

    def __init__(
        self,
        name: str,
        content: str | Sequence[Any],
        role: Literal["user", "assistant", "system"] = "assistant",
        metadata: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> None:
        self.name = name
        self.content = content
        self.role = role
        self.metadata = metadata or {}
        self.id = shortuuid.uuid()
        self.timestamp = timestamp or datetime.now(
            tz=UTC
        ).isoformat()

    def __repr__(self) -> str:
        preview = str(self.content)[:80]
        return f"Msg(name={self.name!r}, role={self.role!r}, content={preview!r})"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "role": self.role,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }
