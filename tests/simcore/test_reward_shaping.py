"""Tests for simcore.reward_shaping — dense subgoal reward computation."""
from __future__ import annotations

import pytest

from simcore.state import GameState
from simcore.reward_shaping import (
    RewardShapingConfig,
    SubgoalTracker,
    compute_dense_reward,
    get_subgoal_info,
    get_curriculum_phase,
    _count_buildings,
    _count_combat_units,
    _count_workers,
    _count_all_units,
    _count_idle_units,
    _count_constructing_buildings,
    _has_barracks,
    _has_combat_units,
    _has_enemy_killed,
    _has_training_queue,
    _territory_coverage,
    _MILESTONE_REQUIRED_PHASE,
)


# ── Fixtures ─────────────────────────────────────────────────────

def _make_state(
    tick: int = 0,
    entities: dict | None = None,
    resources: dict | None = None,
    is_terminal: bool = False,
    winner: int = 0,
    map_width: int = 64,
) -> GameState:
    return GameState(
        tick=tick,
        entities=entities or {},
        resources=resources or {},
        is_terminal=is_terminal,
        winner=winner,
        map_width=map_width,
        map_height=map_width,
    )


# ── SubgoalTracker tests ────────────────────────────────────────

class TestSubgoalTracker:
    def test_reset_clears_all_flags(self):
        t = SubgoalTracker()
        t.first_barracks_done = True
        t.first_combat_unit_done = True
        t.first_enemy_killed_done = True
        t.first_attack_sent_done = True   # v10
        t.reset()
        assert not t.first_barracks_done
        assert not t.first_combat_unit_done
        assert not t.first_enemy_killed_done
        assert not t.first_mineral_gathered_done
        assert not t.first_tech_upgrade_done
        assert not t.first_attack_sent_done   # v10
        assert all(v == 0.0 for v in t.reward_breakdown.values())

    def test_reset_clears_accumulators(self):
        t = SubgoalTracker()
        t.prev_mineral = 100
        t.prev_gas = 50
        t.prev_territory_cells = 5
        t.prev_combat_unit_count = 3
        t.prev_worker_count = 4
        t.prev_supply_used = 6
        t.prev_supply_cap = 10
        t.command_types_used.add("build")
        t.goals_chosen = [0, 1, 2, 3]   # v10
        t.reset()
        assert t.prev_mineral == 0
        assert t.prev_gas == 0
        assert t.prev_territory_cells == 0
        assert t.prev_combat_unit_count == 0
        assert t.prev_worker_count == 0
        assert t.prev_supply_used == 0
        assert t.prev_supply_cap == 0
        assert len(t.command_types_used) == 0
        assert len(t.goals_chosen) == 0   # v10


# ── Milestone detection helpers ─────────────────────────────────

class TestMilestoneDetection:
    def test_has_barracks_simplified(self):
        entities = {
            "b1": {
                "owner": 1, "entity_type": "building",
                "building_type": "barracks",
                "is_constructing": False, "health": 500,
            }
        }
        assert _has_barracks(entities, 1) is True
        assert _has_barracks(entities, 2) is False

    def test_has_barracks_sc1(self):
        entities = {
            "b1": {
                "owner": 1, "entity_type": "building",
                "building_type": "Barracks",
                "is_constructing": False, "health": 500,
            }
        }
        assert _has_barracks(entities, 1) is True

    def test_has_barracks_under_construction_not_counted(self):
        entities = {
            "b1": {
                "owner": 1, "entity_type": "building",
                "building_type": "barracks",
                "is_constructing": True, "health": 50,
            }
        }
        assert _has_barracks(entities, 1) is False

    def test_has_barracks_dead_not_counted(self):
        entities = {
            "b1": {
                "owner": 1, "entity_type": "building",
                "building_type": "barracks",
                "is_constructing": False, "health": 0,
            }
        }
        assert _has_barracks(entities, 1) is False

    def test_has_combat_units_simplified(self):
        entities = {
            "u1": {"owner": 1, "entity_type": "soldier", "health": 50},
        }
        assert _has_combat_units(entities, 1) is True

    def test_has_combat_units_worker_not_counted(self):
        entities = {
            "u1": {"owner": 1, "entity_type": "worker", "health": 50},
        }
        assert _has_combat_units(entities, 1) is False

    def test_has_combat_units_sc1(self):
        entities = {
            "u1": {"owner": 1, "entity_type": "unit", "unit_type": "Marine", "health": 50},
        }
        assert _has_combat_units(entities, 1) is True

    def test_has_enemy_killed(self):
        prev_entities = {
            "e1": {"owner": 2, "entity_type": "soldier", "health": 40},
        }
        curr_entities = {}  # e1 gone
        prev = _make_state(tick=0, entities=prev_entities)
        curr = _make_state(tick=1, entities=curr_entities)
        assert _has_enemy_killed(prev, curr, tracker_owner=1) is True

    def test_has_enemy_killed_hp_zero(self):
        prev_entities = {
            "e1": {"owner": 2, "entity_type": "soldier", "health": 40},
        }
        curr_entities = {
            "e1": {"owner": 2, "entity_type": "soldier", "health": 0},
        }
        prev = _make_state(tick=0, entities=prev_entities)
        curr = _make_state(tick=1, entities=curr_entities)
        assert _has_enemy_killed(prev, curr, tracker_owner=1) is True

    def test_no_enemy_killed(self):
        prev_entities = {
            "e1": {"owner": 2, "entity_type": "soldier", "health": 40},
        }
        curr_entities = {
            "e1": {"owner": 2, "entity_type": "soldier", "health": 30},
        }
        prev = _make_state(tick=0, entities=prev_entities)
        curr = _make_state(tick=1, entities=curr_entities)
        assert _has_enemy_killed(prev, curr, tracker_owner=1) is False


# ── Counter helpers ─────────────────────────────────────────────

class TestCounters:
    def test_count_buildings(self):
        entities = {
            "b1": {"owner": 1, "entity_type": "building", "is_constructing": False, "health": 500},
            "b2": {"owner": 1, "entity_type": "building", "is_constructing": True, "health": 50},
            "b3": {"owner": 2, "entity_type": "building", "is_constructing": False, "health": 500},
        }
        assert _count_buildings(entities, 1) == 1
        assert _count_buildings(entities, 2) == 1

    def test_count_constructing_buildings(self):
        entities = {
            "b1": {"owner": 1, "entity_type": "building", "is_constructing": True, "health": 50},
            "b2": {"owner": 1, "entity_type": "building", "is_constructing": False, "health": 500},
            "b3": {"owner": 2, "entity_type": "building", "is_constructing": True, "health": 30},
        }
        assert _count_constructing_buildings(entities, 1) == 1
        assert _count_constructing_buildings(entities, 2) == 1

    def test_count_combat_units(self):
        entities = {
            "u1": {"owner": 1, "entity_type": "soldier", "health": 50},
            "u2": {"owner": 1, "entity_type": "worker", "health": 40},
            "u3": {"owner": 2, "entity_type": "soldier", "health": 50},
        }
        assert _count_combat_units(entities, 1) == 1
        assert _count_combat_units(entities, 2) == 1

    def test_count_workers(self):
        entities = {
            "u1": {"owner": 1, "entity_type": "soldier", "health": 50},
            "u2": {"owner": 1, "entity_type": "worker", "health": 40},
            "u3": {"owner": 2, "entity_type": "worker", "health": 40},
        }
        assert _count_workers(entities, 1) == 1
        assert _count_workers(entities, 2) == 1

    def test_count_all_units(self):
        entities = {
            "u1": {"owner": 1, "entity_type": "soldier", "health": 50},
            "u2": {"owner": 1, "entity_type": "worker", "health": 40},
            "u3": {"owner": 2, "entity_type": "soldier", "health": 50},
        }
        assert _count_all_units(entities, 1) == 2
        assert _count_all_units(entities, 2) == 1

    def test_count_idle_units(self):
        entities = {
            "u1": {"owner": 1, "entity_type": "worker", "health": 40, "is_idle": True},
            "u2": {"owner": 1, "entity_type": "soldier", "health": 50, "current_order": "attack"},
            "u3": {"owner": 1, "entity_type": "worker", "health": 40, "is_idle": False, "current_order": "gather"},
            "u4": {"owner": 1, "entity_type": "worker", "health": 40},  # no order → idle
        }
        assert _count_idle_units(entities, 1) == 2  # u1 (is_idle) + u4 (no order)

    def test_has_training_queue(self):
        entities = {
            "b1": {"owner": 1, "entity_type": "building", "health": 500, "training_queue": ["Marine"]},
            "b2": {"owner": 1, "entity_type": "building", "health": 500, "training_queue": []},
        }
        assert _has_training_queue(entities, 1) is True

    def test_has_training_queue_empty(self):
        entities = {
            "b1": {"owner": 1, "entity_type": "building", "health": 500, "training_queue": []},
        }
        assert _has_training_queue(entities, 1) is False


# ── Territory coverage ─────────────────────────────────────────

class TestTerritoryCoverage:
    def test_empty_map(self):
        assert _territory_coverage({}, 1) == 0

    def test_single_building(self):
        entities = {
            "b1": {"owner": 1, "entity_type": "building", "pos_x": 32, "pos_y": 32, "health": 500},
        }
        # 1 building + 1-cell radius on 8×8 grid → at least 1 cell
        coverage = _territory_coverage(entities, 1, map_size=64)
        assert coverage >= 1

    def test_enemy_building_not_counted(self):
        entities = {
            "b1": {"owner": 2, "entity_type": "building", "pos_x": 32, "pos_y": 32, "health": 500},
        }
        assert _territory_coverage(entities, 1) == 0


# ── compute_dense_reward integration ───────────────────────────

class TestComputeDenseReward:
    def test_first_step_returns_zero(self):
        tracker = SubgoalTracker()
        curr = _make_state(tick=0)
        r = compute_dense_reward(None, curr, tracker)
        assert r == 0.0

    def test_milestone_first_barracks(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,  # v11: unlock all milestones for testing
            first_barracks=20.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev = _make_state(tick=0, entities={}, resources={"p1_mineral": 0, "p1_gas": 0})
        # Build a barracks
        curr_entities = {
            "b1": {
                "owner": 1, "entity_type": "building",
                "building_type": "barracks",
                "is_constructing": False, "health": 500,
                "pos_x": 10, "pos_y": 10,
            },
        }
        curr = _make_state(tick=1, entities=curr_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        assert r > 0.0
        assert tracker.first_barracks_done is True
        # First barracks only fires once
        r2 = compute_dense_reward(curr, curr, tracker, config=cfg)
        assert tracker.reward_breakdown["milestone_barracks"] == 20.0  # only once

    def test_milestone_first_combat_unit(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,  # v11: unlock all milestones for testing
            first_barracks=0.0,
            first_combat_unit=30.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev = _make_state(tick=0, entities={}, resources={"p1_mineral": 0, "p1_gas": 0})
        curr_entities = {
            "u1": {"owner": 1, "entity_type": "soldier", "health": 50, "pos_x": 10, "pos_y": 10},
        }
        curr = _make_state(tick=1, entities=curr_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        assert tracker.first_combat_unit_done is True
        assert r >= 30.0

    def test_milestone_first_mineral(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,  # v11: unlock all milestones for testing
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=10.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev = _make_state(tick=0, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, resources={"p1_mineral": 5, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        assert tracker.first_mineral_gathered_done is True
        assert r >= 10.0

    def test_milestone_first_kill(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,  # v11: unlock all milestones for testing
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=50.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev_entities = {"e1": {"owner": 2, "entity_type": "soldier", "health": 40}}
        prev = _make_state(tick=0, entities=prev_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        # Enemy unit destroyed
        curr_entities = {"e1": {"owner": 2, "entity_type": "soldier", "health": 0}}
        curr = _make_state(tick=1, entities=curr_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        assert tracker.first_enemy_killed_done is True
        assert r >= 50.0

    def test_per_tick_mineral_income(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.01,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev = _make_state(tick=0, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, resources={"p1_mineral": 10, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        # 10 minerals × 0.01 = 0.10
        assert abs(r - 0.10) < 1e-6

    def test_per_tick_building_survival(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.001,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        entities = {
            "b1": {"owner": 1, "entity_type": "building", "is_constructing": False, "health": 500, "pos_x": 10, "pos_y": 10},
            "b2": {"owner": 1, "entity_type": "building", "is_constructing": False, "health": 500, "pos_x": 30, "pos_y": 30},
        }
        prev = _make_state(tick=0, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        # 2 buildings × 0.001 = 0.002
        assert abs(r - 0.002) < 1e-6

    def test_military_advantage_positive(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.005,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        entities = {
            "u1": {"owner": 1, "entity_type": "soldier", "health": 50},
            "u2": {"owner": 2, "entity_type": "soldier", "health": 50},
            "u3": {"owner": 1, "entity_type": "worker", "health": 40},
        }
        # P1 has 2 units, P2 has 1 → diff = +1 × 0.005 = +0.005
        prev = _make_state(tick=0, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        assert r == pytest.approx(0.005)

    def test_terminal_win(self):
        tracker = SubgoalTracker()
        prev = _make_state(tick=0, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=100, resources={"p1_mineral": 0, "p1_gas": 0}, is_terminal=True, winner=1)
        r = compute_dense_reward(prev, curr, tracker)
        assert tracker.reward_breakdown["terminal"] == 10.0
        assert r >= 10.0

    def test_terminal_loss(self):
        tracker = SubgoalTracker()
        prev = _make_state(tick=0, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=100, resources={"p1_mineral": 0, "p1_gas": 0}, is_terminal=True, winner=2)
        r = compute_dense_reward(prev, curr, tracker)
        assert tracker.reward_breakdown["terminal"] == -10.0

    def test_milestones_fire_only_once(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,  # v11: unlock all milestones for testing
            first_barracks=20.0,
            first_mineral_gathered=10.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        entities = {
            "b1": {
                "owner": 1, "entity_type": "building",
                "building_type": "barracks",
                "is_constructing": False, "health": 500,
                "pos_x": 10, "pos_y": 10,
            },
        }
        prev = _make_state(tick=0, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=entities, resources={"p1_mineral": 5, "p1_gas": 0})
        r1 = compute_dense_reward(prev, curr, tracker, config=cfg)
        assert tracker.first_barracks_done is True
        # Second step — same state
        r2 = compute_dense_reward(curr, curr, tracker, config=cfg)
        # Barracks milestone should NOT fire again
        assert tracker.reward_breakdown["milestone_barracks"] == 20.0  # unchanged

    # ── New dense reward tests ──────────────────────────────

    def test_mineral_count_delta_reward(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.01,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev = _make_state(tick=0, resources={"p1_mineral": 100, "p1_gas": 0})
        curr = _make_state(tick=1, resources={"p1_mineral": 115, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        # delta = 15 × 0.01 = 0.15
        assert abs(r - 0.15) < 1e-6

    def test_supply_headroom_reward(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.005,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev = _make_state(tick=0, resources={"p1_mineral": 0, "p1_gas": 0, "p1_supply_used": 4, "p1_supply_cap": 10})
        curr = _make_state(tick=1, resources={"p1_mineral": 0, "p1_gas": 0, "p1_supply_used": 4, "p1_supply_cap": 10})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        # headroom = (10 - 4) / 10 = 0.6 × 0.005 = 0.003
        assert abs(r - 0.003) < 1e-6

    def test_building_count_delta_reward(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.1,
            building_diminishing_decay=1.0,  # no decay for simple test
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,  # v11: replaced by diminishing
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev_entities = {
            "b1": {"owner": 1, "entity_type": "building", "is_constructing": False, "health": 500, "pos_x": 10, "pos_y": 10},
        }
        curr_entities = {
            "b1": {"owner": 1, "entity_type": "building", "is_constructing": False, "health": 500, "pos_x": 10, "pos_y": 10},
            "b2": {"owner": 1, "entity_type": "building", "is_constructing": False, "health": 500, "pos_x": 30, "pos_y": 30},
        }
        prev = _make_state(tick=0, entities=prev_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=curr_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        # 1 new building (N=1), base=0.1, decay=1.0^0 = 0.1
        assert abs(r - 0.1) < 1e-6

    def test_combat_unit_count_delta_reward(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.15,
            combat_unit_diminishing_decay=1.0,  # no decay for simple test
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,  # v11: replaced by diminishing
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev_entities = {
            "u1": {"owner": 1, "entity_type": "soldier", "health": 50},
        }
        curr_entities = {
            "u1": {"owner": 1, "entity_type": "soldier", "health": 50},
            "u2": {"owner": 1, "entity_type": "soldier", "health": 50},
        }
        prev = _make_state(tick=0, entities=prev_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=curr_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        # 1 new combat unit (N=1), base=0.15, decay=1.0^0 = 0.15
        assert abs(r - 0.15) < 1e-6

    def test_worker_count_delta_reward(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.05,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        prev_entities = {
            "u1": {"owner": 1, "entity_type": "worker", "health": 40},
        }
        curr_entities = {
            "u1": {"owner": 1, "entity_type": "worker", "health": 40},
            "u2": {"owner": 1, "entity_type": "worker", "health": 40},
        }
        prev = _make_state(tick=0, entities=prev_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=curr_entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        # 1 new worker × 0.05 = 0.05
        assert abs(r - 0.05) < 1e-6

    def test_action_diversity_bonus(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            action_diversity_bonus=0.2,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        # Track command types across two steps
        prev = _make_state(tick=0, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, resources={"p1_mineral": 0, "p1_gas": 0})
        # First step: use 2 types
        cmds1 = [{"action": "build"}, {"action": "train"}]
        r1 = compute_dense_reward(prev, curr, tracker, config=cfg, agent_commands=cmds1)
        # Only 2 types → no bonus
        assert tracker.reward_breakdown["tick_action_diversity_bonus"] == 0.0
        # Second step: use 1 more type → now ≥3
        cmds2 = [{"action": "attack"}]
        r2 = compute_dense_reward(curr, curr, tracker, config=cfg, agent_commands=cmds2)
        assert tracker.reward_breakdown["tick_action_diversity_bonus"] == 0.2

    def test_building_under_construction_bonus(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            building_under_construction_bonus=0.1,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        entities = {
            "b1": {"owner": 1, "entity_type": "building", "is_constructing": True, "health": 50, "pos_x": 10, "pos_y": 10},
        }
        prev = _make_state(tick=0, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        assert tracker.reward_breakdown["tick_building_under_construction"] == 0.1

    def test_training_queue_active_bonus(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            training_queue_active_bonus=0.05,
            idle_unit_penalty=0.0,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        entities = {
            "b1": {"owner": 1, "entity_type": "building", "health": 500, "training_queue": ["Marine"], "pos_x": 10, "pos_y": 10},
        }
        prev = _make_state(tick=0, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        assert tracker.reward_breakdown["tick_training_queue_active"] == 0.05

    def test_idle_unit_penalty(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=-0.01,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        entities = {
            "u1": {"owner": 1, "entity_type": "worker", "health": 40, "is_idle": True},
            "u2": {"owner": 1, "entity_type": "soldier", "health": 50, "current_order": "attack"},
        }
        prev = _make_state(tick=0, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        # 1 idle unit × -0.01 = -0.01
        assert abs(tracker.reward_breakdown["tick_idle_unit_penalty"] - (-0.01)) < 1e-6

    def test_multiple_idle_units_penalty(self):
        cfg = RewardShapingConfig(
            curriculum_phase=4,
            first_barracks=0.0,
            first_combat_unit=0.0,
            first_mineral_gathered=0.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            mineral_income_weight=0.0,
            mineral_count_delta_weight=0.0,
            building_diminishing_base=0.0,
            combat_unit_diminishing_base=0.0,
            building_count_delta_weight=0.0,
            combat_unit_count_delta_weight=0.0,
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.0,
            building_survival_weight=0.0,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            idle_unit_penalty=-0.01,
            combat_unit_existence_weight=0.0,
            barracks_existence_weight=0.0,
        )
        tracker = SubgoalTracker()
        entities = {
            "u1": {"owner": 1, "entity_type": "worker", "health": 40, "is_idle": True},
            "u2": {"owner": 1, "entity_type": "worker", "health": 40, "is_idle": True},
            "u3": {"owner": 1, "entity_type": "soldier", "health": 50},  # no order → idle
        }
        prev = _make_state(tick=0, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        curr = _make_state(tick=1, entities=entities, resources={"p1_mineral": 0, "p1_gas": 0})
        r = compute_dense_reward(prev, curr, tracker, config=cfg)
        # 3 idle units × -0.01 = -0.03
        assert abs(tracker.reward_breakdown["tick_idle_unit_penalty"] - (-0.03)) < 1e-6

    def test_reward_breakdown_keys_complete(self):
        """Ensure all expected breakdown keys exist and are populated."""
        cfg = RewardShapingConfig(
            curriculum_phase=4,  # v11: unlock all milestones for testing
            first_barracks=20.0,
            first_combat_unit=30.0,
            first_mineral_gathered=10.0,
            first_enemy_killed=0.0,
            first_tech_upgrade=0.0,
            first_attack_sent=15.0,           # v10
            mineral_income_weight=0.01,
            mineral_count_delta_weight=0.01,
            building_diminishing_base=0.2,   # v11
            building_diminishing_decay=0.7,  # v11
            combat_unit_diminishing_base=0.5, # v11
            combat_unit_diminishing_decay=0.8, # v11
            building_count_delta_weight=0.0,   # v11: replaced by diminishing
            combat_unit_count_delta_weight=0.0, # v11: replaced by diminishing
            worker_count_delta_weight=0.0,
            supply_headroom_weight=0.005,
            building_survival_weight=0.005,
            military_advantage_weight=0.0,
            territory_growth_weight=0.0,
            combat_unit_existence_weight=0.01,  # v10
            barracks_existence_weight=0.008,    # v10
            action_diversity_bonus=0.2,
            building_under_construction_bonus=0.1,
            training_queue_active_bonus=0.05,
            idle_unit_penalty=-0.05,            # v10: -0.01→-0.05
        )
        tracker = SubgoalTracker()
        prev_entities = {}
        curr_entities = {
            "b1": {
                "owner": 1, "entity_type": "building",
                "building_type": "barracks",
                "is_constructing": False, "health": 500,
                "pos_x": 10, "pos_y": 10,
                "training_queue": ["Marine"],
            },
            "u1": {"owner": 1, "entity_type": "worker", "health": 40, "is_idle": False, "current_order": "gather"},
            "u2": {"owner": 1, "entity_type": "soldier", "health": 50, "current_order": "attack"},  # v10: combat unit
        }
        prev = _make_state(tick=0, entities=prev_entities, resources={"p1_mineral": 0, "p1_gas": 0, "p1_supply_used": 1, "p1_supply_cap": 10})
        curr = _make_state(tick=1, entities=curr_entities, resources={"p1_mineral": 50, "p1_gas": 0, "p1_supply_used": 1, "p1_supply_cap": 10})
        cmds = [{"action": "build"}, {"action": "train"}, {"action": "gather"}, {"action": "attack"}]
        r = compute_dense_reward(prev, curr, tracker, config=cfg, agent_commands=cmds)
        # Check that all new keys exist in breakdown
        expected_keys = {
            "milestone_barracks", "milestone_combat_unit", "milestone_first_mineral",
            "milestone_first_kill", "milestone_first_tech", "milestone_first_attack_sent",
            "curriculum_phase_mismatch_skip",  # v11 new
            "tick_mineral_income", "tick_gas_income",
            "tick_building_survival", "tick_military_advantage",
            "tick_territory_growth",
            "tick_mineral_count_delta", "tick_supply_headroom",
            "tick_building_count_delta", "tick_combat_unit_count_delta",
            "tick_worker_count_delta",
            "tick_action_diversity_bonus",
            "tick_building_under_construction",
            "tick_training_queue_active",
            "tick_idle_unit_penalty",
            "tick_failed_command",
            "tick_combat_unit_existence",
            "tick_barracks_existence",
            "tick_goal_diversity_bonus",
            "terminal",
        }
        assert set(tracker.reward_breakdown.keys()) == expected_keys


# ── get_subgoal_info ────────────────────────────────────────────

class TestGetSubgoalInfo:
    def test_returns_milestone_dict(self):
        tracker = SubgoalTracker()
        info = get_subgoal_info(tracker)
        assert "milestones" in info
        assert "reward_breakdown" in info
        assert info["milestones"]["first_barracks"] is False
        tracker.first_barracks_done = True
        info2 = get_subgoal_info(tracker)
        assert info2["milestones"]["first_barracks"] is True

    def test_includes_military_and_territory(self):
        tracker = SubgoalTracker()
        tracker.prev_p1_unit_count = 5
        tracker.prev_p2_unit_count = 3
        info = get_subgoal_info(tracker)
        assert info["military_advantage"] == 2

    def test_includes_new_dense_fields(self):
        tracker = SubgoalTracker()
        tracker.prev_combat_unit_count = 3
        tracker.prev_worker_count = 4
        tracker.command_types_used = {"build", "train", "attack"}
        info = get_subgoal_info(tracker)
        assert info["combat_unit_count"] == 3
        assert info["worker_count"] == 4
        assert info["command_types_used"] == 3
