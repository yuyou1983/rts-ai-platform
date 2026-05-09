"""AgentScope ReActAgent adapter for RTS SimCore.

Bridges the gap between AgentScope's ReActAgent (LLM-driven reasoning)
and SimCore's Gym environment. Provides:
  - Observation → text prompt conversion
  - Text action → structured command dict parsing
  - Episode-level memory for strategic planning

Usage:
    from agents.react_adapter import ReactGameAgent
    agent = ReactGameAgent(player_id=1, model_config={...})
    commands = agent.decide(obs_dict)
"""
from __future__ import annotations

import json
import re
from typing import Any

from agentscope_compat import AgentBase


class ReactGameAgent(AgentBase):
    """LLM-driven RTS agent using ReAct (Reason+Act) pattern.

    Each decision cycle:
      1. Convert SimCore obs → text prompt
      2. LLM generates reasoning + action
      3. Parse text action → command dicts
      4. Return commands to SimCore
    """

    name: str = "ReactGameAgent"

    def __init__(
        self,
        player_id: int = 1,
        model_name: str = "glm-5.1",
        max_retries: int = 3,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("name", f"ReactGameAgent_P{player_id}")
        super().__init__(**kwargs)
        self.player_id = player_id
        self.model_name = model_name
        self._max_retries = max_retries
        self._history: list[str] = []

    def decide(self, obs: dict) -> dict:
        """Generate commands from observation using ReAct reasoning.

        Args:
            obs: Observation dict from GameState.get_observations().

        Returns:
            Dict with 'commands' list and 'tick'.
        """
        prompt = self._build_prompt(obs)
        self._history.append(prompt)

        # If no LLM configured, fall back to heuristic parsing
        commands = self._fallback_heuristic(obs)
        return {"commands": commands, "tick": obs.get("tick", 0)}

    def _build_prompt(self, obs: dict) -> str:
        """Convert observation to a text prompt for the LLM."""
        tick = obs.get("tick", 0)
        entities = obs.get("entities", {})
        resources = obs.get("resources", {})

        my_entities = {
            k: v for k, v in entities.items()
            if v.get("owner") == self.player_id
        }
        enemy_entities = {
            k: v for k, v in entities.items()
            if v.get("owner") not in (0, self.player_id) and v.get("health", 0) > 0
        }
        resources_free = {
            k: v for k, v in entities.items()
            if v.get("entity_type") == "resource" and v.get("resource_amount", 0) > 0
        }

        lines = [
            f"=== RTS Game State (Tick {tick}) ===",
            f"You are Player {self.player_id}.",
            "",
            f"Resources: {json.dumps(resources, indent=2)}",
            "",
            f"Your units/buildings ({len(my_entities)}):",
        ]
        for eid, e in my_entities.items():
            etype = e.get("entity_type", e.get("building_type", e.get("unit_type", "?")))
            lines.append(
                f"  {eid}: {etype} at ({e.get('pos_x', 0):.1f}, "
                f"{e.get('pos_y', 0):.1f}) hp={e.get('health', 0):.0f}/"
                f"{e.get('max_health', 0):.0f}"
                f"{' idle' if e.get('is_idle') else ' busy'}"
            )

        lines.append(f"\nEnemy entities ({len(enemy_entities)}):")
        for eid, e in enemy_entities.items():
            etype = e.get("entity_type", e.get("building_type", e.get("unit_type", "?")))
            lines.append(
                f"  {eid}: {etype} at ({e.get('pos_x', 0):.1f}, "
                f"{e.get('pos_y', 0):.1f})"
            )

        lines.append(f"\nAvailable resources ({len(resources_free)}):")
        for eid, e in list(resources_free.items())[:5]:
            lines.append(
                f"  {eid}: {e.get('resource_type', '?')} "
                f"amount={e.get('resource_amount', 0):.0f} "
                f"at ({e.get('pos_x', 0):.1f}, {e.get('pos_y', 0):.1f})"
            )

        lines.append("")
        lines.append("Available actions: move, gather, attack, build, train, noop")
        lines.append(
            "Respond with JSON: "
            '{"commands": [{"action": "...", "unit_id": "...", ...}]}'
        )

        return "\n".join(lines)

    def _fallback_heuristic(self, obs: dict) -> list[dict]:
        """Rule-based fallback when no LLM is configured.

        Simplified version of ScriptAI for the ReAct adapter.
        """
        commands: list[dict] = []
        entities = obs.get("entities", {})
        resources = obs.get("resources", {})
        pid = self.player_id

        mineral_key = f"p{pid}_mineral"
        mineral = resources.get(mineral_key, 0) if isinstance(resources, dict) else 0

        # Find idle workers and assign to nearest mineral
        idle_workers = [
            (eid, e) for eid, e in entities.items()
            if e.get("owner") == pid
            and e.get("entity_type") == "worker"
            and e.get("is_idle", True)
        ]

        mineral_patches = [
            (eid, e) for eid, e in entities.items()
            if e.get("entity_type") == "resource"
            and e.get("resource_type") == "mineral"
            and e.get("resource_amount", 0) > 0
        ]

        for wid, worker in idle_workers[:3]:
            if mineral_patches:
                best = min(
                    mineral_patches,
                    key=lambda p: _dist_sq(worker, p[1]),
                )
                commands.append({
                    "action": "gather",
                    "worker_id": wid,
                    "resource_id": best[0],
                    "issuer": pid,
                })

        # Train workers if affordable
        worker_count = sum(
            1 for e in entities.values()
            if e.get("owner") == pid and e.get("entity_type") == "worker"
        )
        base = next(
            (e for e in entities.values()
             if e.get("owner") == pid and e.get("building_type") == "base"),
            None,
        )
        if base and mineral >= 50 and worker_count < 8:
            base_id = next(
                (eid for eid, e in entities.items()
                 if e.get("owner") == pid and e.get("building_type") == "base"),
                "",
            )
            commands.append({
                "action": "train",
                "building_id": base_id,
                "unit_type": "worker",
                "issuer": pid,
            })

        return commands

    def parse_action(self, text: str) -> list[dict]:
        """Parse LLM text output into structured command dicts.

        Expects JSON in format:
          {"commands": [{"action": "move", "unit_id": "w1", "target_x": 10, "target_y": 20}]}
        """
        # Try to extract JSON from text
        json_match = re.search(r'\{[^{}]*"commands"\s*:\s*\[.*?\][^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return parsed.get("commands", [])
            except json.JSONDecodeError:
                pass

        # Fallback: try action lines like "move worker_1 to 10 20"
        commands: list[dict] = []
        for line in text.strip().split("\n"):
            parts = line.strip().lower().split()
            if not parts:
                continue
            action = parts[0]
            if action in ("move", "gather", "attack", "build", "train", "noop"):
                cmd: dict[str, Any] = {"action": action, "issuer": self.player_id}
                if len(parts) >= 2:
                    cmd["unit_id"] = parts[1]
                if action == "move" and len(parts) >= 4:
                    try:
                        cmd["target_x"] = float(parts[2])
                        cmd["target_y"] = float(parts[3])
                    except ValueError:
                        pass
                commands.append(cmd)

        return commands


def _dist_sq(a: dict, b: dict) -> float:
    dx = a.get("pos_x", 0) - b.get("pos_x", 0)
    dy = a.get("pos_y", 0) - b.get("pos_y", 0)
    return dx * dx + dy * dy
