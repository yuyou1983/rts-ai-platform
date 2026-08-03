"""Tests for P3-1: Medical/support spells — irradiate, feedback, mind_control,
   maelstrom, stasis invulnerability, restoration parasite clear."""
import math
import pytest
from simcore.spells import process_spells, process_dots
from simcore.rules import resolve_combat

T = 32.0  # _MAP_TILE_SIZE


def _caster(energy=200, owner=1, eid="c1", x=100, y=100, spellcaster=True):
    return {
        "id": eid, "entity_id": eid, "owner": owner,
        "entity_type": "unit", "energy": energy,
        "pos_x": x, "pos_y": y, "max_health": 200, "health": 200,
        "is_spellcaster": spellcaster, "cooldown_timer": 99,
        "attack_ground": 0, "attack_air": 0, "base_speed": 3.0,
        "buffs": [], "is_idle": True, "attack_target_id": "",
    }


def _target(owner=2, eid="t1", x=200, y=200, hp=200, organic=True, mechanical=False, energy=0):
    return {
        "id": eid, "entity_id": eid, "owner": owner,
        "entity_type": "unit", "health": hp, "max_health": 200,
        "pos_x": x, "pos_y": y, "is_organic": organic,
        "is_mechanical": mechanical, "energy": energy,
        "is_spellcaster": energy > 0,
        "attack_ground": 8, "attack_air": 0, "base_speed": 3.0,
        "buffs": [], "is_idle": True, "attack_target_id": "",
        "cooldown_timer": 99, "cooldown_ground": 10,
        "sight": 8, "armor": 0, "shields": 0,
        "domain": "ground",
    }


class TestIrradiate:
    def test_irradiate_applies_dot_buff(self):
        caster = _caster(eid="c1", x=100, y=100)
        target = _target(eid="t1", x=132, y=100, hp=200)  # within 1 tile
        ents = {"c1": caster, "t1": target}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "irradiate", "target_id": "t1"}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        t = result["t1"]
        assert any(b["type"] == "irradiate" for b in t["buffs"])
        assert t["health"] == 200  # no instant damage

    def test_irradiate_dot_deals_damage(self):
        caster = _caster(eid="c1")
        target = _target(eid="t1", x=132, y=100, hp=200)
        # Manually add irradiate buff, then process_dots
        dot_per_tick = 250 / 120  # ~2.08
        target["buffs"] = [{"type": "irradiate", "remaining": 120,
                            "dot_per_tick": dot_per_tick, "source_owner": 1}]
        result = process_dots({"t1": target}, tick=2)
        assert result["t1"]["health"] < 200

    def test_irradiate_splash_hurts_nearby_enemy_organic(self):
        """Irradiate should also damage nearby enemy organic units."""
        caster = _caster(eid="c1")
        target = _target(eid="t1", x=100, y=100, hp=200)
        bystander = _target(eid="b1", x=120, y=100, hp=200, owner=2)
        dot_per_tick = 250 / 120
        target["buffs"] = [{"type": "irradiate", "remaining": 120,
                            "dot_per_tick": dot_per_tick, "source_owner": 1}]
        ents = {"t1": target, "b1": bystander}
        result = process_dots(ents, tick=2)
        assert result["b1"]["health"] < 200  # splash damaged

    def test_irradiate_no_friendly_fire(self):
        """Irradiate splash does NOT damage same-team units."""
        target = _target(eid="t1", x=100, y=100, hp=200, owner=1)
        friendly = _target(eid="f1", x=120, y=100, hp=200, owner=1)
        dot_per_tick = 250 / 120
        target["buffs"] = [{"type": "irradiate", "remaining": 120,
                            "dot_per_tick": dot_per_tick, "source_owner": 1}]
        ents = {"t1": target, "f1": friendly}
        result = process_dots(ents, tick=2)
        assert result["f1"]["health"] == 200  # not damaged


class TestFeedback:
    def test_feedback_drains_energy_and_deals_damage(self):
        caster = _caster(eid="c1")
        target = _target(eid="t1", hp=200, energy=100)
        target["is_spellcaster"] = True
        ents = {"c1": caster, "t1": target}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "feedback", "target_id": "t1"}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert result["t1"]["energy"] == 0
        # Energy regen (+0.75) happens before feedback, so actual energy at cast = 100.75
        assert result["t1"]["health"] == pytest.approx(200 - 100.75, abs=0.5)

    def test_feedback_no_effect_on_non_spellcaster(self):
        caster = _caster(eid="c1")
        target = _target(eid="t1", hp=200, energy=100)
        target["is_spellcaster"] = False
        ents = {"c1": caster, "t1": target}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "feedback", "target_id": "t1"}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert result["t1"]["health"] == 200
        assert result["t1"]["energy"] == pytest.approx(100.75, abs=0.5)  # +0.75 regen


class TestMindControl:
    def test_mind_control_changes_owner(self):
        caster = _caster(eid="c1", owner=1)
        target = _target(eid="t1", owner=2, hp=200)
        ents = {"c1": caster, "t1": target}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "mindcontrol", "target_id": "t1"}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert result["t1"]["owner"] == 1
        assert result["t1"]["is_idle"] is True

    def test_mind_control_same_team_no_effect(self):
        caster = _caster(eid="c1", owner=1)
        target = _target(eid="t1", owner=1, hp=200)
        ents = {"c1": caster, "t1": target}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "mindcontrol", "target_id": "t1"}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert result["t1"]["owner"] == 1  # unchanged


class TestMaelstrom:
    def test_maelstrom_stuns_organic_enemies(self):
        caster = _caster(eid="c1", x=100, y=100)
        enemy = _target(eid="e1", x=200, y=100, hp=200, owner=2, organic=True)
        ents = {"c1": caster, "e1": enemy}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "maelstrom",
                 "target_x": 200, "target_y": 100}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert result["e1"].get("stasis") is True
        assert result["e1"]["speed"] == 0

    def test_maelstrom_no_effect_on_mechanical(self):
        caster = _caster(eid="c1", x=100, y=100)
        enemy = _target(eid="e1", x=200, y=100, hp=200, owner=2,
                        organic=False, mechanical=True)
        ents = {"c1": caster, "e1": enemy}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "maelstrom",
                 "target_x": 200, "target_y": 100}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert result["e1"].get("stasis") is None  # not stunned


class TestStasisField:
    def test_stasis_makes_invulnerable(self):
        """Stasis'd units should not be attackable."""
        attacker = {
            "id": "a1", "entity_id": "a1", "owner": 1,
            "entity_type": "unit", "pos_x": 100, "pos_y": 100,
            "attack_ground": 10, "attack_air": 0,
            "attack_range_ground": 200, "weapon_type_ground": "normal",
            "cooldown_ground": 1, "cooldown_timer": 99,
            "health": 100, "max_health": 100,
            "buffs": [], "is_idle": False, "attack_target_id": "t1",
            "armor": 0, "shields": 0,
        }
        target = {
            "id": "t1", "entity_id": "t1", "owner": 2,
            "entity_type": "unit", "pos_x": 150, "pos_y": 100,
            "health": 80, "max_health": 80,
            "stasis": True,  # in stasis — invulnerable
            "attack_ground": 0, "attack_air": 0,
            "base_speed": 0, "buffs": [{"type": "stasis", "remaining": 120}],
            "is_idle": True, "attack_target_id": "",
            "armor": 0, "shields": 0,
            "domain": "ground",
        }
        ents = {"a1": attacker, "t1": target}
        result, _ = resolve_combat(ents, {"p1_mineral": 1000, "p2_mineral": 1000}, [], tick=1)
        # Target should NOT take damage (stasis = invulnerable)
        assert result["t1"]["health"] == 80

    def test_stasis_units_cannot_attack(self):
        """Stasis'd units should not auto-attack."""
        stasised = {
            "id": "s1", "entity_id": "s1", "owner": 1,
            "entity_type": "unit", "pos_x": 100, "pos_y": 100,
            "attack_ground": 10, "attack_air": 0,
            "attack_range_ground": 200, "weapon_type_ground": "normal",
            "cooldown_ground": 1, "cooldown_timer": 99,
            "health": 100, "max_health": 100,
            "stasis": True, "base_speed": 0,
            "buffs": [{"type": "stasis", "remaining": 120}],
            "is_idle": True, "attack_target_id": "",
            "armor": 0, "shields": 0,
        }
        enemy = {
            "id": "e1", "entity_id": "e1", "owner": 2,
            "entity_type": "unit", "pos_x": 150, "pos_y": 100,
            "health": 100, "max_health": 100,
            "attack_ground": 0, "attack_air": 0, "base_speed": 0,
            "buffs": [], "is_idle": True, "attack_target_id": "",
            "armor": 0, "shields": 0, "domain": "ground",
        }
        ents = {"s1": stasised, "e1": enemy}
        result, _ = resolve_combat(ents, {"p1_mineral": 1000, "p2_mineral": 1000}, [], tick=1)
        # Stasis'd unit should not have attacked
        assert result["e1"]["health"] == 100  # no damage

    def test_stasis_expires_unit_resumes(self):
        """When stasis buff expires, unit should resume normal behavior."""
        unit = _target(eid="u1", owner=1, hp=200, x=100, y=100)
        unit["stasis"] = True
        unit["buffs"] = [{"type": "stasis", "remaining": 1}]
        # process_buffs should decrement remaining to 0, then remove buff + revert stasis
        from simcore.spells import process_buffs
        result = process_buffs({"u1": unit}, tick=1)
        assert result["u1"].get("stasis") is False or result["u1"].get("stasis") is None


class TestRestorationParasite:
    def test_restoration_clears_parasite(self):
        caster = _caster(eid="c1")
        target = _target(eid="t1", hp=200)
        target["parasited_by"] = 2
        ents = {"c1": caster, "t1": target}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "restoration", "target_id": "t1"}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert result["t1"]["parasited_by"] is None

    def test_restoration_clears_irradiate_buff(self):
        caster = _caster(eid="c1")
        target = _target(eid="t1", hp=200)
        target["buffs"] = [{"type": "irradiate", "remaining": 60, "dot_per_tick": 2.0}]
        ents = {"c1": caster, "t1": target}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "restoration", "target_id": "t1"}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert not any(b["type"] == "irradiate" for b in result["t1"]["buffs"])

    def test_restoration_clears_maelstrom_buff(self):
        caster = _caster(eid="c1")
        target = _target(eid="t1", hp=200)
        target["buffs"] = [{"type": "maelstrom", "remaining": 30}]
        target["stasis"] = True
        ents = {"c1": caster, "t1": target}
        cmds = [{"action": "spell", "caster_id": "c1", "spell": "restoration", "target_id": "t1"}]
        result, _ = process_spells(ents, {"p1_mineral": 5000}, cmds, tick=1)
        assert not any(b["type"] == "maelstrom" for b in result["t1"]["buffs"])


# ── Psionic Storm lifecycle tests (Task 7) ──────────────────────────────────


class TestPsionicStorm:
    """SC1 Psionic Storm: 8 damage ticks × 14 dmg = 112 total, routed through
    resolve_weapon_impact(). Cast tick deals NO damage; storm advances on
    subsequent ticks even with an empty command list."""

    def _setup(self):
        """Caster at (0,0), target at (10,0) — outside Storm radius (5)."""
        caster = _caster(eid="ht1", x=0, y=0, energy=200)
        target = _target(eid="m1", x=10, y=0, hp=200)
        target["armor_type"] = "light"
        target["armor"] = 0
        target["shields"] = 0
        entities = {"ht1": caster, "m1": target}
        cmd = [{"action": "spell", "spell": "psionicstorm",
                "caster_id": "ht1", "target_x": 10.0, "target_y": 0.0}]
        return entities, cmd

    def test_storm_emits_spell_resolved_on_cast(self):
        """Cast emits exactly one SPELL_RESOLVED event with weapon_id."""
        from simcore.combat_events import SPELL_RESOLVED
        entities, cmd = self._setup()
        events = []
        process_spells(entities, {}, cmd, tick=1, combat_events=events)
        spells = [e for e in events if e["event_type"] == SPELL_RESOLVED]
        assert len(spells) == 1
        assert spells[0]["weapon_id"] == "protoss_psionic_storm"

    def test_storm_no_damage_on_cast_tick(self):
        """Cast tick deals zero damage — first impact is on tick 2."""
        from simcore.combat_events import IMPACT_RESOLVED
        entities, cmd = self._setup()
        events = []
        result, _ = process_spells(entities, {}, cmd, tick=1, combat_events=events)
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        assert len(impacts) == 0, f"Expected 0 impacts on cast tick, got {len(impacts)}"
        assert result["m1"]["health"] == 200, "Target should not be damaged on cast tick"

    def test_storm_advances_without_new_spell_command(self):
        """Storm continues to deal damage on ticks 2-9 with empty command list."""
        from simcore.combat_events import IMPACT_RESOLVED
        entities, cmd = self._setup()
        events = []
        result, _ = process_spells(entities, {}, cmd, tick=1, combat_events=events)
        hp_after_cast = result["m1"]["health"]
        for t in range(2, 10):
            result, _ = process_spells(result, {}, [], tick=t, combat_events=events)
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        assert len(impacts) == 8, f"Expected 8 impacts over 8 ticks, got {len(impacts)}"
        assert result["m1"]["health"] < hp_after_cast, "Target should have taken damage"

    def test_storm_total_damage_8_ticks_14_each(self):
        """8 impacts × 14 base damage = 112 total."""
        from simcore.combat_events import IMPACT_RESOLVED
        # Use a target with enough HP to survive all 8 ticks
        entities, cmd = self._setup()
        entities["m1"]["health"] = 200
        entities["m1"]["max_health"] = 200
        events = []
        result, _ = process_spells(entities, {}, cmd, tick=1, combat_events=events)
        for t in range(2, 12):
            result, _ = process_spells(result, {}, [], tick=t, combat_events=events)
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        assert len(impacts) == 8
        # Each impact should have base_damage = 14
        for imp in impacts:
            assert imp["base_damage"] == 14
        # Total damage = 8 × 14 = 112; with 0 armor and light vs normal (100%), health = 200 - 112 = 88
        assert result["m1"]["health"] == 88, f"Expected HP=88, got {result['m1']['health']}"

    def test_storm_expires_after_8_damage_ticks(self):
        """After 8 damage ticks, storm effect is removed and no more damage occurs."""
        from simcore.combat_events import IMPACT_RESOLVED
        entities, cmd = self._setup()
        entities["m1"]["health"] = 500  # ensure survival
        entities["m1"]["max_health"] = 500
        events = []
        result, _ = process_spells(entities, {}, cmd, tick=1, combat_events=events)
        # Advance through all 8 damage ticks
        for t in range(2, 12):
            result, _ = process_spells(result, {}, [], tick=t, combat_events=events)
        hp_after_8_ticks = result["m1"]["health"]
        # Continue for several more ticks — no additional damage
        for t in range(12, 20):
            result, _ = process_spells(result, {}, [], tick=t, combat_events=events)
        impacts = [e for e in events if e["event_type"] == IMPACT_RESOLVED]
        assert len(impacts) == 8, f"Expected exactly 8 impacts, got {len(impacts)}"
        assert result["m1"]["health"] == hp_after_8_ticks, "No damage after storm expired"
        # Storm effect entity should be gone
        storm_entities = [e for e in result.values() if e.get("effect_type") == "psionic_storm"]
        assert len(storm_entities) == 0, "Storm effect should have been removed"
