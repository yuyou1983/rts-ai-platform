"""Passive AI — does nothing every tick."""


class PassiveAI:
    """Does nothing every tick — used as a punching bag."""

    def decide(self, obs: dict) -> list[dict]:
        return []
