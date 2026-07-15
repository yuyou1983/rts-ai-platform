"""Dense subgoal reward shaping for RTS RL training (v11 curriculum).

Replaces the weak signal in gym_env._compute_reward("shaped") with
a rich set of milestone + per-tick rewards that guide the agent
through the early-mid game tech tree.

v11 curriculum design:
  Milestones are gated by curriculum phase based on training step.
  Phase 1 (0–50K steps):      first_mineral_gathered — economic foundation
  Phase 2 (50K–150K steps):   + first_barracks — start producing
  Phase 3 (150K–300K steps):  + first_combat_unit, first_attack_sent
  Phase 4 (300K+):            + first_enemy_killed, first_tech_upgrade
  This prevents the V10 failure mode where all milestones are active
  simultaneously and the policy converges to only hitting barracks.

  Building/combat-unit count delta rewards use diminishing returns:
  Nth building  → 0.2 × 0.7^(N-1)
  Nth combat unit → 0.5 × 0.8^(N-1)
  This prevents the strategy of repeatedly building the same structure.

Design principles:
  - Milestone rewards are one-shot booleans (never repeat).
  - Per-tick rewards are small but provide gradient signal every step.
  - All weights are configurable via RewardShapingConfig.
  - SubgoalTracker is per-episode state, reset in env.reset().

Reward components:
  ┌─────────────────────────────────────┬──────────┬──────────────────────┐
  │ Component                           │ Type     │ Default Weight       │
  ├─────────────────────────────────────┼──────────┼──────────────────────┤
  │ First mineral gathered (phase 1)    │ milestone│ +10.00              │
  │ First barracks completed (phase 2)  │ milestone│ +20.00              │
  │ First combat unit trained (phase 3) │ milestone│ +30.00              │
  │ First attack sent (phase 3)         │ milestone│ +15.00              │
  │ First enemy killed (phase 4)        │ milestone│ +100.00             │
  │ First tech upgrade (phase 4)        │ milestone│ +15.00              │
  │ Per-tick mineral income             │ tick     │ ×0.01               │
  │ Per-tick gas income                 │ tick     │ ×0.0005             │
  │ Per-tick building survival          │ tick     │ +0.005 per building │
  │ Per-tick military advantage         │ tick     │ diff × 0.003        │
  │ Territory coverage growth           │ tick     │ Δarea × 0.01       │
  │ Per-tick mineral count delta        │ tick     │ Δmineral × 0.01    │
  │ Per-tick supply headroom            │ tick     │ ratio × 0.005      │
  │ Per-tick building count delta        │ tick     │ 0.2 × 0.7^(N-1)   │
  │ Per-tick combat unit count delta     │ tick     │ 0.5 × 0.8^(N-1)   │
  │ Per-tick worker count delta          │ tick     │ Δworkers × 0.05    │
  │ Per-tick action diversity bonus      │ tick     │ +0.2/step          │
  │ Per-tick building under construction │ tick     │ +0.1/step          │
  │ Per-tick training queue active        │ tick     │ +0.05/step         │
  │ Per-tick idle unit penalty           │ tick     │ -0.05 per idle     │
  │ Failed command penalty              │ tick     │ -0.1 per fail      │
  │ Terminal win/loss                   │ terminal │ +10.0 / -10.0      │
  └─────────────────────────────────────┴──────────┴──────────────────────┘
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simcore.state import GameState


# ─── Configuration ──────────────────────────────────────────

@dataclass
class RewardShapingConfig:
    """All reward weights in one place — easy to sweep / anneal."""

    # Milestone (one-shot) rewards
    first_barracks: float = 20.0
    first_combat_unit: float = 30.0
    first_mineral_gathered: float = 10.0
    first_enemy_killed: float = 100.0   # v10: 50→100, stronger kill reward
    first_tech_upgrade: float = 15.0
    first_attack_sent: float = 15.0     # v10: new milestone — first attack command

    # Per-tick dense rewards — resource income
    mineral_income_weight: float = 0.01      # per mineral deposited per tick
    gas_income_weight: float = 0.0005        # per gas deposited per tick

    # Per-tick dense rewards — resource accumulation progress
    mineral_count_delta_weight: float = 0.01  # positive part of mineral change × weight
    supply_headroom_weight: float = 0.005     # available_supply / max_supply × weight

    # Per-tick dense rewards — building/unit deltas
    building_count_delta_weight: float = 0.2   # v10: 0.1→0.2, barracks more attractive than supply
    combat_unit_count_delta_weight: float = 0.5  # v10: 0.15→0.5, strong incentive to produce combat units
    worker_count_delta_weight: float = 0.05    # per worker added

    # Per-tick dense rewards — existing survival / advantage
    building_survival_weight: float = 0.005   # per alive building per tick
    military_advantage_weight: float = 0.003  # v10: 0.02→0.003, reduced from 74% to ~15% of total reward
    territory_growth_weight: float = 0.01     # Δ building_coverage_area per tick

    # Per-tick dense rewards — existence bonuses (v10 new)
    combat_unit_existence_weight: float = 0.01   # per alive combat unit per tick (retain combat units)
    barracks_existence_weight: float = 0.008     # per alive completed barracks per tick

    # Per-tick dense rewards — behaviour consistency
    action_diversity_bonus: float = 0.2       # +bonus/step if ≥3 cmd types used
    building_under_construction_bonus: float = 0.1  # +bonus/step if any building constructing
    training_queue_active_bonus: float = 0.05  # +bonus/step if training queue non-empty

    # Per-tick dense rewards — idle penalty
    idle_unit_penalty: float = -0.05            # v10: -0.01→-0.05, stronger idle penalty

    # Failed command penalty (build/train rejected due to resources/prereqs)
    failed_command_penalty: float = -0.1       # per rejected build or train command

    # Curriculum phase (0-4). 0 = all milestones active (legacy),
    # 1-4 = phased curriculum.  Set by get_curriculum_phase(step).
    curriculum_phase: int = 0

    # Diminishing-returns decay rates for repeated same-category items
    building_diminishing_base: float = 0.2      # reward for the Nth building: base × 0.7^(N-1)
    building_diminishing_decay: float = 0.7
    combat_unit_diminishing_base: float = 0.5   # reward for the Nth combat unit: base × 0.8^(N-1)
    combat_unit_diminishing_decay: float = 0.8

    # Terminal
    win_bonus: float = 10.0
    loss_penalty: float = -10.0
    draw_penalty: float = -0.3


# ─── Subgoal Tracker ────────────────────────────────────────

@dataclass
class SubgoalTracker:
    """Per-episode mutable state that records which milestones have fired.

    Reset in env.reset().  Read-only in _compute_reward().
    """
    # One-shot milestone flags
    first_barracks_done: bool = False
    first_combat_unit_done: bool = False
    first_mineral_gathered_done: bool = False
    first_enemy_killed_done: bool = False
    first_tech_upgrade_done: bool = False
    first_attack_sent_done: bool = False    # v10: new milestone

    # Running accumulators for per-tick features
    prev_mineral: int = 0
    prev_gas: int = 0
    prev_building_count: int = 0
    prev_territory_cells: int = 0   # number of map cells covered by P1 buildings
    prev_p1_unit_count: int = 0
    prev_p2_unit_count: int = 0

    # Running accumulators for new dense rewards
    prev_combat_unit_count: int = 0
    prev_worker_count: int = 0
    prev_supply_used: int = 0
    prev_supply_cap: int = 0

    # Action diversity tracking (per episode)
    command_types_used: set[str] = field(default_factory=set)

    # Goal diversity tracking (per episode, v10 new)
    goals_chosen: list[int] = field(default_factory=list)

    # Curriculum: current training step (global, not per-episode)
    # Updated by the training loop before each episode.
    current_training_step: int = 0

    # Diminishing-returns counters (per episode, reset each episode)
    cumulative_building_count: int = 0      # running total of buildings ever completed
    cumulative_combat_unit_count: int = 0   # running total of combat units ever produced

    # Cumulative reward breakdown (useful for logging / analysis)
    reward_breakdown: dict[str, float] = field(default_factory=lambda: {
        "milestone_barracks": 0.0,
        "milestone_combat_unit": 0.0,
        "milestone_first_mineral": 0.0,
        "milestone_first_kill": 0.0,
        "milestone_first_tech": 0.0,
        "milestone_first_attack_sent": 0.0,      # v10 new
        "curriculum_phase_mismatch_skip": 0.0,  # v11: milestones skipped due to phase
        "tick_mineral_income": 0.0,
        "tick_gas_income": 0.0,
        "tick_building_survival": 0.0,
        "tick_military_advantage": 0.0,
        "tick_territory_growth": 0.0,
        "tick_mineral_count_delta": 0.0,
        "tick_supply_headroom": 0.0,
        "tick_building_count_delta": 0.0,
        "tick_combat_unit_count_delta": 0.0,
        "tick_worker_count_delta": 0.0,
        "tick_action_diversity_bonus": 0.0,
        "tick_building_under_construction": 0.0,
        "tick_training_queue_active": 0.0,
        "tick_idle_unit_penalty": 0.0,
        "tick_failed_command": 0.0,
        "tick_combat_unit_existence": 0.0,       # v10 new
        "tick_barracks_existence": 0.0,          # v10 new
        "tick_goal_diversity_bonus": 0.0,        # v10 new
        "terminal": 0.0,
    })

    def reset(self) -> None:
        """Reset all state for a new episode."""
        self.first_barracks_done = False
        self.first_combat_unit_done = False
        self.first_mineral_gathered_done = False
        self.first_enemy_killed_done = False
        self.first_tech_upgrade_done = False
        self.first_attack_sent_done = False
        self.prev_mineral = 0
        self.prev_gas = 0
        self.prev_building_count = 0
        self.prev_territory_cells = 0
        self.prev_p1_unit_count = 0
        self.prev_p2_unit_count = 0
        self.prev_combat_unit_count = 0
        self.prev_worker_count = 0
        self.prev_supply_used = 0
        self.prev_supply_cap = 0
        self.command_types_used = set()
        self.goals_chosen = []
        self.cumulative_building_count = 0
        self.cumulative_combat_unit_count = 0
        for key in self.reward_breakdown:
            self.reward_breakdown[key] = 0.0


# ─── Helper queries on GameState ────────────────────────────

# Building types that count as "barracks" (production buildings for combat units)
_BARRACKS_TYPES = frozenset({
    "barracks", "Barracks", "Gateway", "SpawningPool",
    "Factory", "Starport",
})

# Unit types that count as "combat units" (not workers)
_COMBAT_UNIT_TYPES = frozenset({
    "soldier", "scout",  # simplified
    "Marine", "Firebat", "Ghost", "Medic", "Vulture", "Goliath",
    "SiegeTank", "Wraith", "Dropship", "Valkyrie", "Battlecruiser",
    "Zergling", "Hydralisk", "Mutalisk", "Scourge", "Queen",
    "Ultralisk", "Guardian", "Devourer", "Defiler",
    "Zealot", "Dragoon", "HighTemplar", "DarkTemplar", "Reaver",
    "Shuttle", "Corsair", "Scout", "Arbiter", "Carrier",
})

# Unit types that are workers
_WORKER_TYPES = frozenset({
    "worker", "SCV", "Drone", "Probe",
})


def _count_buildings(entities: dict[str, Any], owner: int) -> int:
    """Count alive, completed buildings owned by `owner`."""
    return sum(
        1 for e in entities.values()
        if e.get("owner") == owner
        and e.get("entity_type") == "building"
        and not e.get("is_constructing", False)
        and e.get("health", 0) > 0
    )


def _count_constructing_buildings(entities: dict[str, Any], owner: int) -> int:
    """Count buildings currently under construction owned by `owner`."""
    return sum(
        1 for e in entities.values()
        if e.get("owner") == owner
        and e.get("entity_type") == "building"
        and e.get("is_constructing", False)
        and e.get("health", 0) > 0
    )


def _has_barracks(entities: dict[str, Any], owner: int) -> bool:
    """Check if `owner` has at least one completed barracks-type building."""
    for e in entities.values():
        if e.get("owner") != owner:
            continue
        if e.get("entity_type") != "building":
            continue
        if e.get("is_constructing", False):
            continue
        if e.get("health", 0) <= 0:
            continue
        bt = e.get("building_type", "")
        if bt in _BARRACKS_TYPES:
            return True
        # Also check lowercase/underscore variants
        bt_norm = bt.lower().replace("_", "").replace(" ", "")
        if bt_norm in ("barracks", "gateway", "spawningpool", "factory", "starport"):
            return True
    return False


def _has_combat_units(entities: dict[str, Any], owner: int) -> bool:
    """Check if `owner` has at least one alive combat unit."""
    for e in entities.values():
        if e.get("owner") != owner:
            continue
        if e.get("health", 0) <= 0:
            continue
        etype = e.get("entity_type", "")
        utype = e.get("unit_type", "")
        # Simplified types
        if etype in ("soldier", "scout"):
            return True
        # SC1 types
        if utype in _COMBAT_UNIT_TYPES or etype in _COMBAT_UNIT_TYPES:
            return True
    return False


def _count_combat_units(entities: dict[str, Any], owner: int) -> int:
    """Count alive combat units owned by `owner`."""
    count = 0
    for e in entities.values():
        if e.get("owner") != owner:
            continue
        if e.get("health", 0) <= 0:
            continue
        etype = e.get("entity_type", "")
        utype = e.get("unit_type", "")
        if etype in ("soldier", "scout"):
            count += 1
        elif utype in _COMBAT_UNIT_TYPES or etype in _COMBAT_UNIT_TYPES:
            count += 1
    return count


def _count_workers(entities: dict[str, Any], owner: int) -> int:
    """Count alive worker units owned by `owner`."""
    count = 0
    for e in entities.values():
        if e.get("owner") != owner:
            continue
        if e.get("health", 0) <= 0:
            continue
        etype = e.get("entity_type", "")
        utype = e.get("unit_type", "")
        if etype == "worker":
            count += 1
        elif utype in _WORKER_TYPES:
            count += 1
    return count


def _count_all_units(entities: dict[str, Any], owner: int) -> int:
    """Count all alive mobile units (workers + combat) owned by `owner`."""
    count = 0
    for e in entities.values():
        if e.get("owner") != owner:
            continue
        if e.get("health", 0) <= 0:
            continue
        etype = e.get("entity_type", "")
        utype = e.get("unit_type", "")
        if etype in ("worker", "soldier", "scout", "unit"):
            count += 1
        elif utype in _COMBAT_UNIT_TYPES or utype in _WORKER_TYPES:
            count += 1
    return count


def _count_idle_units(entities: dict[str, Any], owner: int) -> int:
    """Count alive own units that are idle (no current order)."""
    count = 0
    for e in entities.values():
        if e.get("owner") != owner:
            continue
        if e.get("health", 0) <= 0:
            continue
        etype = e.get("entity_type", "")
        # Only count mobile units, not buildings
        if etype not in ("worker", "soldier", "scout", "unit"):
            utype = e.get("unit_type", "")
            if utype not in _COMBAT_UNIT_TYPES and utype not in _WORKER_TYPES:
                continue
        # Check if idle — no current order or explicit idle flag
        if e.get("is_idle", False) or not e.get("current_order", ""):
            count += 1
    return count


def _has_training_queue(entities: dict[str, Any], owner: int) -> bool:
    """Check if any of `owner`'s buildings has an active training queue."""
    for e in entities.values():
        if e.get("owner") != owner:
            continue
        if e.get("entity_type") != "building":
            continue
        if e.get("health", 0) <= 0:
            continue
        queue = e.get("training_queue", [])
        if isinstance(queue, (list, tuple)) and len(queue) > 0:
            return True
    return False


def _has_enemy_killed(prev: GameState, curr: GameState, tracker_owner: int = 1) -> bool:
    """Detect if any enemy (opponent of tracker_owner) unit was killed this tick.

    A kill is detected when an enemy entity existed in prev but is gone in curr,
    or its health dropped to ≤ 0.
    """
    enemy_owner = 2 if tracker_owner == 1 else 1
    for eid, e in prev.entities.items():
        if e.get("owner") != enemy_owner:
            continue
        if eid.startswith("__"):
            continue
        # Entity existed in prev but is gone or dead in curr
        curr_e = curr.entities.get(eid)
        if curr_e is None or curr_e.get("health", 0) <= 0:
            return True
    return False


def _has_tech_upgrade(prev: GameState, curr: GameState, owner: int = 1) -> bool:
    """Detect if a research/upgrade was completed this tick for `owner`.

    Checks the __completed_upgrades__ meta-key in entities.
    """
    prev_upgrades = prev.entities.get("__completed_upgrades__", {})
    curr_upgrades = curr.entities.get("__completed_upgrades__", {})
    # Both are {owner_str: [upgrade_name, ...]}
    owner_str = str(owner)
    prev_list = prev_upgrades.get(owner_str, []) if isinstance(prev_upgrades, dict) else []
    curr_list = curr_upgrades.get(owner_str, []) if isinstance(curr_upgrades, dict) else []
    if not isinstance(prev_list, list):
        prev_list = []
    if not isinstance(curr_list, list):
        curr_list = []
    return len(curr_list) > len(prev_list)


def _territory_coverage(entities: dict[str, Any], owner: int, map_size: int = 64) -> int:
    """Estimate territory coverage as number of map grid cells occupied by
    `owner`'s buildings + a radius around each building.

    Uses a coarse 8×8 grid (each cell = 8×8 world units) for speed.
    """
    grid_dim = 8
    cell_size = map_size / grid_dim
    covered = set()
    for e in entities.values():
        if e.get("owner") != owner:
            continue
        if e.get("entity_type") != "building":
            continue
        if e.get("health", 0) <= 0:
            continue
        bx = int(e.get("pos_x", 0) / cell_size)
        by = int(e.get("pos_y", 0) / cell_size)
        # Building itself + 1-cell radius
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                cx, cy = bx + dx, by + dy
                if 0 <= cx < grid_dim and 0 <= cy < grid_dim:
                    covered.add((cx, cy))
    return len(covered)


def _count_barracks(entities: dict[str, Any], owner: int) -> int:
    """Count alive, completed barracks-type buildings owned by `owner`."""
    count = 0
    for e in entities.values():
        if e.get("owner") != owner:
            continue
        if e.get("health", 0) <= 0:
            continue
        if e.get("entity_type") != "building":
            continue
        if e.get("is_constructing", False):
            continue
        bt = e.get("building_type", e.get("unit_type", ""))
        # Check against _BARRACKS_TYPES and normalised variants
        if bt in _BARRACKS_TYPES:
            count += 1
        else:
            bt_norm = bt.lower().replace("_", "").replace(" ", "")
            if bt_norm in ("barracks", "gateway", "spawningpool", "factory", "starport"):
                count += 1
    return count


# ─── Curriculum Phase Helper ──────────────────────────────────

# Milestone → minimum curriculum phase required for activation
_MILESTONE_REQUIRED_PHASE: dict[str, int] = {
    "first_mineral_gathered": 1,
    "first_barracks": 2,
    "first_combat_unit": 3,
    "first_attack_sent": 3,
    "first_enemy_killed": 4,
    "first_tech_upgrade": 4,
}

# Phase boundary thresholds (in training steps)
_CURRICULUM_PHASE_BOUNDARIES: list[tuple[int, int]] = [
    # (phase, upper_step_bound) — phase N is active for steps < bound
    (1, 50_000),
    (2, 150_000),
    (3, 300_000),
    # phase 4 has no upper bound
]


def get_curriculum_phase(step: int) -> int:
    """Return the curriculum phase (1-4) for a given training step.

    Phase 1 (0–50K):      first_mineral_gathered
    Phase 2 (50K–150K):   + first_barracks
    Phase 3 (150K–300K):  + first_combat_unit, first_attack_sent
    Phase 4 (300K+):      + first_enemy_killed, first_tech_upgrade
    """
    for phase, upper_bound in _CURRICULUM_PHASE_BOUNDARIES:
        if step < upper_bound:
            return phase
    return 4


# ─── Core Reward Computation ────────────────────────────────

def compute_dense_reward(
    prev: GameState | None,
    curr: GameState,
    tracker: SubgoalTracker,
    config: RewardShapingConfig | None = None,
    player_id: int = 1,
    agent_commands: list[dict] | None = None,
) -> float:
    """Compute dense shaped reward with subgoal milestones.

    Args:
        prev: Previous tick's GameState (None on first step).
        curr: Current tick's GameState.
        tracker: Per-episode mutable tracker for milestone flags.
        config: Reward weight configuration (uses defaults if None).
        player_id: Which player we compute reward for (default P1).
        agent_commands: The agent's original commands this tick (for failed-cmd penalty).

    Returns:
        Scalar reward for this step.
    """
    if prev is None:
        # Initialize tracker baseline from current state
        _sync_tracker_baseline(curr, tracker, player_id)
        return 0.0

    if config is None:
        config = RewardShapingConfig()

    enemy_id = 2 if player_id == 1 else 1
    reward = 0.0

    # Ensure tracker baseline is initialized from prev state if this is
    # the first real step (e.g. tracker just created with defaults of 0).
    if tracker.prev_mineral == 0 and tracker.prev_building_count == 0:
        _sync_tracker_baseline(prev, tracker, player_id)

    # ── Determine curriculum phase (v11) ────────────────────
    # Phase 0 = legacy mode (all milestones active).
    # Phase 1-4 = curriculum gating based on training step.
    if config.curriculum_phase == 0:
        current_phase = get_curriculum_phase(tracker.current_training_step)
    else:
        current_phase = config.curriculum_phase

    # ── Milestone: First Barracks ──────────────────────────
    if not tracker.first_barracks_done and _has_barracks(curr.entities, player_id):
        required = _MILESTONE_REQUIRED_PHASE["first_barracks"]
        if current_phase >= required:
            reward += config.first_barracks
            tracker.first_barracks_done = True
            tracker.reward_breakdown["milestone_barracks"] += config.first_barracks
        else:
            tracker.reward_breakdown["curriculum_phase_mismatch_skip"] += config.first_barracks

    # ── Milestone: First Combat Unit ───────────────────────
    if not tracker.first_combat_unit_done and _has_combat_units(curr.entities, player_id):
        required = _MILESTONE_REQUIRED_PHASE["first_combat_unit"]
        if current_phase >= required:
            reward += config.first_combat_unit
            tracker.first_combat_unit_done = True
            tracker.reward_breakdown["milestone_combat_unit"] += config.first_combat_unit
        else:
            tracker.reward_breakdown["curriculum_phase_mismatch_skip"] += config.first_combat_unit

    # ── Milestone: First Mineral Gathered ──────────────────
    curr_mineral = curr.resources.get(f"p{player_id}_mineral", 0)
    if not tracker.first_mineral_gathered_done and curr_mineral > tracker.prev_mineral:
        required = _MILESTONE_REQUIRED_PHASE["first_mineral_gathered"]
        if current_phase >= required:
            reward += config.first_mineral_gathered
            tracker.first_mineral_gathered_done = True
            tracker.reward_breakdown["milestone_first_mineral"] += config.first_mineral_gathered
        else:
            tracker.reward_breakdown["curriculum_phase_mismatch_skip"] += config.first_mineral_gathered

    # ── Milestone: First Enemy Killed ──────────────────────
    if not tracker.first_enemy_killed_done and _has_enemy_killed(prev, curr, player_id):
        required = _MILESTONE_REQUIRED_PHASE["first_enemy_killed"]
        if current_phase >= required:
            reward += config.first_enemy_killed
            tracker.first_enemy_killed_done = True
            tracker.reward_breakdown["milestone_first_kill"] += config.first_enemy_killed
        else:
            tracker.reward_breakdown["curriculum_phase_mismatch_skip"] += config.first_enemy_killed

    # ── Milestone: First Tech Upgrade ──────────────────────
    if not tracker.first_tech_upgrade_done and _has_tech_upgrade(prev, curr, player_id):
        required = _MILESTONE_REQUIRED_PHASE["first_tech_upgrade"]
        if current_phase >= required:
            reward += config.first_tech_upgrade
            tracker.first_tech_upgrade_done = True
            tracker.reward_breakdown["milestone_first_tech"] += config.first_tech_upgrade
        else:
            tracker.reward_breakdown["curriculum_phase_mismatch_skip"] += config.first_tech_upgrade

    # ── Milestone: First Attack Sent (v10 new) ────────────
    if not tracker.first_attack_sent_done and agent_commands:
        required = _MILESTONE_REQUIRED_PHASE["first_attack_sent"]
        for cmd in agent_commands:
            if cmd.get("action") == "attack":
                if current_phase >= required:
                    reward += config.first_attack_sent
                    tracker.first_attack_sent_done = True
                    tracker.reward_breakdown["milestone_first_attack_sent"] += config.first_attack_sent
                else:
                    tracker.reward_breakdown["curriculum_phase_mismatch_skip"] += config.first_attack_sent
                break

    # ── Per-tick: Mineral Income ───────────────────────────
    mineral_delta = curr_mineral - tracker.prev_mineral
    mineral_reward = max(0.0, mineral_delta) * config.mineral_income_weight
    reward += mineral_reward
    tracker.reward_breakdown["tick_mineral_income"] += mineral_reward

    # ── Per-tick: Gas Income ───────────────────────────────
    curr_gas = curr.resources.get(f"p{player_id}_gas", 0)
    gas_delta = curr_gas - tracker.prev_gas
    gas_reward = max(0.0, gas_delta) * config.gas_income_weight
    reward += gas_reward
    tracker.reward_breakdown["tick_gas_income"] += gas_reward

    # ── Per-tick: Mineral Count Delta (resource accumulation progress) ──
    mineral_count_delta_reward = max(0.0, mineral_delta) * config.mineral_count_delta_weight
    reward += mineral_count_delta_reward
    tracker.reward_breakdown["tick_mineral_count_delta"] += mineral_count_delta_reward

    # ── Per-tick: Supply Headroom ──────────────────────────
    supply_used = curr.resources.get(f"p{player_id}_supply_used", 0)
    supply_cap = curr.resources.get(f"p{player_id}_supply_cap", 0)
    if supply_cap > 0:
        headroom_ratio = (supply_cap - supply_used) / supply_cap
    else:
        headroom_ratio = 0.0
    supply_reward = headroom_ratio * config.supply_headroom_weight
    reward += supply_reward
    tracker.reward_breakdown["tick_supply_headroom"] += supply_reward

    # ── Per-tick: Building Count Delta (v11: diminishing returns) ──
    building_count = _count_buildings(curr.entities, player_id)
    building_delta = building_count - tracker.prev_building_count
    if building_delta > 0:
        # Each subsequent building of the same category yields less reward
        # Reward for Nth building = base × decay^(N-1)
        for n in range(1, building_delta + 1):
            nth = tracker.cumulative_building_count + n
            dim_reward = config.building_diminishing_base * (
                config.building_diminishing_decay ** (nth - 1)
            )
            reward += dim_reward
            tracker.reward_breakdown["tick_building_count_delta"] += dim_reward
        tracker.cumulative_building_count += building_delta
    # Note: building_delta ≤ 0 gives no reward (losses penalized elsewhere)

    # ── Per-tick: Combat Unit Count Delta (v11: diminishing returns) ──
    combat_unit_count = _count_combat_units(curr.entities, player_id)
    combat_delta = combat_unit_count - tracker.prev_combat_unit_count
    if combat_delta > 0:
        # Each subsequent combat unit yields less reward
        # Reward for Nth unit = base × decay^(N-1)
        for n in range(1, combat_delta + 1):
            nth = tracker.cumulative_combat_unit_count + n
            dim_reward = config.combat_unit_diminishing_base * (
                config.combat_unit_diminishing_decay ** (nth - 1)
            )
            reward += dim_reward
            tracker.reward_breakdown["tick_combat_unit_count_delta"] += dim_reward
        tracker.cumulative_combat_unit_count += combat_delta
    # Note: combat_delta ≤ 0 gives no reward (losses penalized elsewhere)

    # ── Per-tick: Worker Count Delta ───────────────────────
    worker_count = _count_workers(curr.entities, player_id)
    worker_delta = worker_count - tracker.prev_worker_count
    worker_delta_reward = max(0.0, worker_delta) * config.worker_count_delta_weight
    reward += worker_delta_reward
    tracker.reward_breakdown["tick_worker_count_delta"] += worker_delta_reward

    # ── Per-tick: Building Survival ─────────────────────────
    survival_reward = building_count * config.building_survival_weight
    reward += survival_reward
    tracker.reward_breakdown["tick_building_survival"] += survival_reward

    # ── Per-tick: Military Advantage ────────────────────────
    p1_units = _count_all_units(curr.entities, player_id)
    p2_units = _count_all_units(curr.entities, enemy_id)
    unit_diff = p1_units - p2_units
    military_reward = unit_diff * config.military_advantage_weight
    reward += military_reward
    tracker.reward_breakdown["tick_military_advantage"] += military_reward

    # ── Per-tick: Territory Coverage Growth ─────────────────
    map_size = curr.map_width
    curr_cells = _territory_coverage(curr.entities, player_id, map_size)
    territory_delta = curr_cells - tracker.prev_territory_cells
    territory_reward = max(0.0, territory_delta) * config.territory_growth_weight
    reward += territory_reward
    tracker.reward_breakdown["tick_territory_growth"] += territory_reward

    # ── Per-tick: Action Diversity Bonus ────────────────────
    # Track command types used across the episode
    if agent_commands:
        for cmd in agent_commands:
            cmd_type = cmd.get("action", cmd.get("command", ""))
            if cmd_type:
                tracker.command_types_used.add(cmd_type)
    if len(tracker.command_types_used) >= 3 and config.action_diversity_bonus != 0:
        diversity_reward = config.action_diversity_bonus
        reward += diversity_reward
        tracker.reward_breakdown["tick_action_diversity_bonus"] += diversity_reward

    # ── Per-tick: Building Under Construction Bonus ────────
    constructing_count = _count_constructing_buildings(curr.entities, player_id)
    if constructing_count > 0 and config.building_under_construction_bonus != 0:
        constructing_reward = config.building_under_construction_bonus
        reward += constructing_reward
        tracker.reward_breakdown["tick_building_under_construction"] += constructing_reward

    # ── Per-tick: Training Queue Active Bonus ──────────────
    if _has_training_queue(curr.entities, player_id) and config.training_queue_active_bonus != 0:
        training_reward = config.training_queue_active_bonus
        reward += training_reward
        tracker.reward_breakdown["tick_training_queue_active"] += training_reward

    # ── Per-tick: Idle Unit Penalty ────────────────────────
    idle_count = _count_idle_units(curr.entities, player_id)
    if idle_count > 0 and config.idle_unit_penalty != 0:
        idle_penalty = idle_count * config.idle_unit_penalty
        reward += idle_penalty
        tracker.reward_breakdown["tick_idle_unit_penalty"] += idle_penalty

    # ── Per-tick: Combat Unit Existence Bonus (v10 new) ───
    combat_count = _count_combat_units(curr.entities, player_id)
    if combat_count > 0 and config.combat_unit_existence_weight != 0:
        combat_exist_reward = combat_count * config.combat_unit_existence_weight
        reward += combat_exist_reward
        tracker.reward_breakdown["tick_combat_unit_existence"] += combat_exist_reward

    # ── Per-tick: Barracks Existence Bonus (v10 new) ──────
    barracks_count = _count_barracks(curr.entities, player_id)
    if barracks_count > 0 and config.barracks_existence_weight != 0:
        barracks_exist_reward = barracks_count * config.barracks_existence_weight
        reward += barracks_exist_reward
        tracker.reward_breakdown["tick_barracks_existence"] += barracks_exist_reward

    # ── Per-tick: Goal Diversity Bonus (v10 new) ──────────
    # If ≥4 distinct goals chosen in this episode, give +0.5/step
    n_distinct_goals = len(set(int(g) for g in tracker.goals_chosen))
    if n_distinct_goals >= 4:
        goal_div_reward = 0.5
        reward += goal_div_reward
        tracker.reward_breakdown["tick_goal_diversity_bonus"] += goal_div_reward

    # ── Per-tick: Failed Command Penalty ───────────────────
    # Penalize build/train commands that didn't change state
    failed_penalty = 0.0
    if agent_commands and config.failed_command_penalty != 0:
        for cmd in agent_commands:
            action = cmd.get("action", "")
            if action in ("build", "train"):
                # Check if entity counts changed for this player
                eid = (
                    cmd.get("entity_id") or cmd.get("unit_id")
                    or cmd.get("building_id") or cmd.get("builder_id")
                    or ""
                )
                # If the target entity doesn't exist or building count didn't grow, it failed
                if action == "build" and eid:
                    # A successful build creates a new entity; check prev→curr
                    if eid in prev.entities and eid in curr.entities:
                        # Still exists with same state = likely failed
                        if prev.entities[eid].get("is_constructing", False) == curr.entities[eid].get("is_constructing", False):
                            failed_penalty += config.failed_command_penalty
                    elif eid not in curr.entities:
                        # Entity vanished — definitely failed
                        failed_penalty += config.failed_command_penalty
                elif action == "train":
                    # Training succeeded iff a new unit appeared for this player
                    prev_units = _count_all_units(prev.entities, player_id)
                    curr_units = _count_all_units(curr.entities, player_id)
                    if curr_units <= prev_units:
                        failed_penalty += config.failed_command_penalty
    if failed_penalty != 0:
        reward += failed_penalty
        tracker.reward_breakdown["tick_failed_command"] += failed_penalty

    # ── Terminal Bonus ──────────────────────────────────────
    if curr.is_terminal:
        if curr.winner == player_id:
            terminal_reward = config.win_bonus
        elif curr.winner == enemy_id:
            terminal_reward = config.loss_penalty
        else:
            terminal_reward = config.draw_penalty
        reward += terminal_reward
        tracker.reward_breakdown["terminal"] += terminal_reward

    # ── Sync tracker for next tick ───────────────────────────
    _sync_tracker_baseline(curr, tracker, player_id)

    return reward


def _sync_tracker_baseline(
    state: GameState, tracker: SubgoalTracker, player_id: int
) -> None:
    """Update tracker's running accumulators from current state."""
    enemy_id = 2 if player_id == 1 else 1
    tracker.prev_mineral = state.resources.get(f"p{player_id}_mineral", 0)
    tracker.prev_gas = state.resources.get(f"p{player_id}_gas", 0)
    tracker.prev_building_count = _count_buildings(state.entities, player_id)
    tracker.prev_territory_cells = _territory_coverage(
        state.entities, player_id, state.map_width
    )
    tracker.prev_p1_unit_count = _count_all_units(state.entities, player_id)
    tracker.prev_p2_unit_count = _count_all_units(state.entities, enemy_id)
    tracker.prev_combat_unit_count = _count_combat_units(state.entities, player_id)
    tracker.prev_worker_count = _count_workers(state.entities, player_id)
    tracker.prev_supply_used = state.resources.get(f"p{player_id}_supply_used", 0)
    tracker.prev_supply_cap = state.resources.get(f"p{player_id}_supply_cap", 0)


def get_subgoal_info(tracker: SubgoalTracker) -> dict[str, Any]:
    """Return a dict of current milestone status + reward breakdown.

    Useful as part of `info` dict in env.step() for logging / TB.
    """
    current_phase = get_curriculum_phase(tracker.current_training_step)
    return {
        "milestones": {
            "first_barracks": tracker.first_barracks_done,
            "first_combat_unit": tracker.first_combat_unit_done,
            "first_mineral_gathered": tracker.first_mineral_gathered_done,
            "first_enemy_killed": tracker.first_enemy_killed_done,
            "first_tech_upgrade": tracker.first_tech_upgrade_done,
            "first_attack_sent": tracker.first_attack_sent_done,
        },
        "curriculum_phase": current_phase,
        "curriculum_training_step": tracker.current_training_step,
        "reward_breakdown": dict(tracker.reward_breakdown),
        "military_advantage": (
            tracker.prev_p1_unit_count - tracker.prev_p2_unit_count
        ),
        "territory_cells": tracker.prev_territory_cells,
        "building_count": tracker.prev_building_count,
        "combat_unit_count": tracker.prev_combat_unit_count,
        "worker_count": tracker.prev_worker_count,
        "command_types_used": len(tracker.command_types_used),
        "goals_chosen_count": len(set(int(g) for g in tracker.goals_chosen)),
    }
