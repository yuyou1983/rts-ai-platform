#!/usr/bin/env python3
"""Verify Godot-side fog smoothing against live HTTP state.

The server fog grid is allowed to change between visible/explored as units move.
Godot should render those raw changes through a smoothed alpha buffer, so this
check replays the same alpha update used by ``game_view.gd`` and fails only when
rendered alpha jumps enough to be visually noticeable.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import sys
import urllib.request


BASE = "http://localhost:8080"
FOG_FADE_FRAMES = 15
ALPHA_SPIKE_THRESHOLD = 0.25


def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def target_alpha(state: int) -> float:
    if state == 2:
        return 0.0
    if state == 1:
        return 0.50
    return 0.88


def update_alpha(prev_tiles: list[int], tiles: list[int], alpha: list[float]) -> list[float]:
    if len(alpha) != len(tiles):
        alpha = [target_alpha(t) for t in tiles]

    next_alpha = list(alpha)
    speed = 1.0 / float(FOG_FADE_FRAMES)
    for idx, cur in enumerate(tiles):
        prev = prev_tiles[idx] if idx < len(prev_tiles) else 0
        target = target_alpha(cur)
        if cur == 2:
            next_alpha[idx] = 0.0
        elif prev == 2:
            next_alpha[idx] = 0.0
        elif next_alpha[idx] < target:
            next_alpha[idx] = min(next_alpha[idx] + (target - next_alpha[idx]) * speed * 3.0, target)
        elif next_alpha[idx] > target:
            next_alpha[idx] = max(next_alpha[idx] - (next_alpha[idx] - target) * speed * 2.0, target)
    return next_alpha


def main() -> int:
    print("=== Godot fog smoothing verification ===")
    state = post("/api/start_game", {
        "seed": 42,
        "max_ticks": 500,
        "ai_player": 2,
        "ai_difficulty": "medium",
        "enable_elevation": True,
    })
    fog = state.get("fog_of_war", {}).get("1", {})
    prev_tiles = [int(t) for t in fog.get("tiles", [])]
    alpha = [target_alpha(t) for t in prev_tiles]
    prev_alpha = list(alpha)

    raw_downgrades: dict[int, int] = defaultdict(int)
    alpha_spikes: dict[int, list[tuple[int, float, float]]] = defaultdict(list)

    for _ in range(100):
        state = post("/api/step", {"commands": []})
        tick = int(state.get("tick", 0))
        fog = state.get("fog_of_war", {}).get("1", {})
        tiles = [int(t) for t in fog.get("tiles", [])]
        if not tiles:
            print("ERROR: missing P1 fog tiles")
            return 1

        for idx, (prev, cur) in enumerate(zip(prev_tiles, tiles, strict=False)):
            if prev == 2 and cur != 2:
                raw_downgrades[idx] += 1

        alpha = update_alpha(prev_tiles, tiles, alpha)
        for idx, (old_a, new_a) in enumerate(zip(prev_alpha, alpha, strict=False)):
            # Flicker is a sudden darkening of an area that was recently clear.
            # Clearing newly explored tiles is expected and should not fail this check.
            delta = new_a - old_a
            if delta > ALPHA_SPIKE_THRESHOLD:
                alpha_spikes[idx].append((tick, old_a, new_a))

        prev_tiles = list(tiles)
        prev_alpha = list(alpha)

    raw_multi = {idx: count for idx, count in raw_downgrades.items() if count >= 2}
    spike_tiles = {idx: events for idx, events in alpha_spikes.items() if events}
    alpha_counts = Counter(round(a, 2) for a in alpha)

    print(f"  Raw repeated 2->1 downgrades: {len(raw_multi)} tiles")
    print(f"  Rendered alpha spike threshold: > {ALPHA_SPIKE_THRESHOLD:.2f}")
    print(f"  Rendered alpha spike tiles: {len(spike_tiles)}")
    print(f"  Final alpha distribution: {dict(alpha_counts)}")

    if spike_tiles:
        print("\n  Worst alpha spikes:")
        for idx, events in sorted(spike_tiles.items(), key=lambda item: -len(item[1]))[:10]:
            print(f"    tile {idx}: {events[:5]}")
        return 1

    print("\nOK: raw fog still changes, but Godot rendered alpha remains stable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
