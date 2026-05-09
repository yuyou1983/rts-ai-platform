"""AgentBase — compatible with AgentScope's agent interface."""
from __future__ import annotations

from typing import Any

from ._msg import Msg


class AgentBase:
    """Base class for all RTS agents.

    Subclasses must implement ``reply`` which receives the current
    observation as a Msg and returns a Msg containing commands.
    """

    def __init__(self, name: str, player_id: int = 0, **kwargs: Any) -> None:
        self.name = name
        self.player_id = player_id
        self._memory: list[Msg] = []

    async def observe(self, msg: Msg | list[Msg] | None) -> None:
        """Receive a message (observation) and store it in memory."""
        if msg is None:
            return
        if isinstance(msg, list):
            self._memory.extend(msg)
        else:
            self._memory.append(msg)

    async def reply(self, *args: Any, **kwargs: Any) -> Msg:
        """Generate a reply based on current state. Subclasses must override."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement reply()"
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Synchronous wrapper — calls ``reply`` via a simple event loop."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # We're already inside an async context — schedule and block
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run, self.reply(*args, **kwargs)
                ).result()
        return asyncio.run(self.reply(*args, **kwargs))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, player_id={self.player_id})"
