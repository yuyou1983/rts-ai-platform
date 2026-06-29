"""Tests for P2: Zerg morph (Hydralisk->Lurker, Mutalisk->Guardian/Devourer)
   and Protoss merge (Templar+Templar->Archon, DarkTemplar+DarkTemplar->DarkArchon)."""
import math
import pytest
from simcore.spells import process_spells, _find_merge_partner, SPELL_CATEGORIES, SPELL_CONFIG
from simcore.construction import process_construction
from simcore.rules import resolve_combat

# Helper
T = 32.0  # _MAP_TILE_SIZE

def _e(eid, owner, utype, hp, px, py, **kw):
    """Build a minimal unit entity."""
    e = {
        "id": eid, "entity_id": eid, "owner": owner,
        "entity_type": "unit", "unit_type": utype,
        "pos_x": float(px), "pos_y": float(py),
        "health": hp, "max_health": hp,
        "shields": kw.get("shields", 0),
        "max_shields": kw.get("max_shields", 0),
        "speed": kw.get("speed", 2.5),
        "attack_ground": kw.get("attack_ground", 0),
        "attack_air": kw.get("attack_air", 0),
        "attack_range_ground": kw.get("attack_range_ground", 0),
        "attack_range_air": kw.get("attack_range_air", 0),
        "weapon_type_ground": kw.get("weapon_type_ground", "none"),
        "weapon_type_air": kw.get("weapon_type_air", "none"),
        "cooldown_ground": kw.get("cooldown_ground", 10),
        "cooldown_air": kw.get("cooldown_air", 0),
        "cooldown_timer": kw.get("cooldown_timer", 10),
        "armor": kw.get("armor", 0),
        "domain": kw.get("domain", "ground"),
        "is_idle": True, "carry_amount": 0, "carry_capacity": 0,
        "target_x": None, "target_y": None,
        "returning_to_base": False, "attack_target_id": "",
        "deposit_pending": False, "buffs": [],
        "is_spellcaster": kw.get("is_spellcaster", False),
        "energy": kw.get("energy", 0),
        "mp": kw.get("mp", kw.get("energy", 0)),
    }
    return e


# ═══════════════════════════════════════════════════════════
# Unit tests: _find_merge_partner
# ═══════════════════════════════════════════════════════════
class TestFindMergePartner:
    def test_finds_nearby_same_type(self):
        entities = {
            "t1": _e("t1", 1, "Templar", 40, 0, 0),
            "t2": _e("t2", 1, "Templar", 40, 2 * T, 0),
        }
        result = _find_merge_partner(entities, "t1", 1, "Templar", 3 * T)
        assert result == "t2"

    def test_ignores_wrong_owner(self):
        entities = {
            "t1": _e("t1", 1, "Templar", 40, 0, 0),
            "t2": _e("t2", 2, "Templar", 40, 2 * T, 0),
        }
        result = _find_merge_partner(entities, "t1", 1, "Templar", 3 * T)
        assert result is None

    def test_ignores_wrong_type(self):
        entities = {
            "t1": _e("t1", 1, "Templar", 40, 0, 0),
            "t2": _e("t2", 1, "DarkTemplar", 40, 2 * T, 0),
        }
        result = _find_merge_partner(entities, "t1", 1, "Templar", 3 * T)
        assert result is None

    def test_ignores_out_of_range(self):
        entities = {
            "t1": _e("t1", 1, "Templar", 40, 0, 0),
            "t2": _e("t2", 1, "Templar", 40, 10 * T, 0),
        }
        result = _find_merge_partner(entities, "t1", 1, "Templar", 3 * T)
        assert result is None

    def test_excludes_self(self):
        entities = {"t1": _e("t1", 1, "Templar", 40, 0, 0)}
        result = _find_merge_partner(entities, "t1", 1, "Templar", 10 * T)
        assert result is None

    def test_excludes_set(self):
        entities = {
            "t1": _e("t1", 1, "Templar", 40, 0, 0),
            "t2": _e("t2", 1, "Templar", 40, 2 * T, 0),
        }
        result = _find_merge_partner(entities, "t1", 1, "Templar", 3 * T,
                                       exclude={"t2"})
        assert result is None


# ═══════════════════════════════════════════════════════════
# Integration: Zerg morph
# ═══════════════════════════════════════════════════════════
class TestZergMorph:
    def test_hydralisk_to_lurker_spell(self):
        """Casting lurker_morph sets morph_target and freezes unit."""
        hydra = _e("h1", 1, "Hydralisk", 80, 0, 0,
                   attack_ground=10, attack_air=10, speed=2.5)
        entities = {"h1": hydra}
        cmds = [{"action": "spell", "caster_id": "h1", "spell": "lurker_morph"}]
        result, _ = process_spells(entities, {"p1_mineral": 1000}, cmds, tick=1)
        r = result["h1"]
        assert r["morphing"] is True
        assert r["morph_target"] == "Lurker"
        assert r["morph_timer"] > 0
        assert r["attack_ground"] == 0
        assert r["speed"] == 0

    def test_morph_completes_via_construction(self):
        """After morph_timer ticks, construction.py spawns the target unit."""
        hydra = _e("h1", 1, "Hydralisk", 80, 5 * T, 5 * T,
                   attack_ground=10, speed=2.5)
        # Pre-set morphing state (as if spell was already cast)
        hydra["morphing"] = True
        hydra["morph_target"] = "Lurker"
        hydra["morph_timer"] = 2
        hydra["attack_ground"] = 0
        hydra["speed"] = 0
        hydra["is_idle"] = True

        entities = {"h1": hydra}
        # Tick 1: timer decrements
        built, _ = process_construction(entities, {"p1_mineral": 1000}, [], tick=10)
        assert built.get("h1", {}).get("morph_timer") == 1

        # Tick 2: morph completes -> Lurker spawns, hydra removed
        built2, _ = process_construction(built, {"p1_mineral": 1000}, [], tick=11)
        assert "h1" not in built2
        lurker_id = [k for k in built2 if built2[k].get("unit_type") == "Lurker"]
        assert len(lurker_id) == 1
        lurker = built2[lurker_id[0]]
        assert lurker["owner"] == 1
        assert abs(lurker["pos_x"] - 5 * T) < 1
        assert lurker["attack_ground"] > 0

    def test_mutalisk_to_guardian(self):
        muta = _e("m1", 1, "Mutalisk", 120, 3 * T, 3 * T,
                  domain="air", attack_ground=9, attack_air=9, speed=3.0)
        muta["morphing"] = True
        muta["morph_target"] = "Guardian"
        muta["morph_timer"] = 2
        muta["attack_ground"] = 0
        muta["speed"] = 0

        entities = {"m1": muta}
        built, _ = process_construction(entities, {"p1_mineral": 1000}, [], tick=10)
        built2, _ = process_construction(built, {"p1_mineral": 1000}, [], tick=11)
        guardian_ids = [k for k in built2 if built2[k].get("unit_type") == "Guardian"]
        assert len(guardian_ids) == 1

    def test_morphing_unit_cannot_attack(self):
        """A morphing unit should not fire in combat."""
        hydra = _e("h1", 1, "Hydralisk", 80, 0, 0,
                   attack_ground=10, attack_air=10, speed=0,
                   cooldown_timer=100, cooldown_ground=10)
        hydra["morphing"] = True
        hydra["morph_target"] = "Lurker"
        hydra["morph_timer"] = 50
        hydra["attack_ground"] = 0
        hydra["attack_air"] = 0

        enemy = _e("e1", 2, "Marine", 200, 2 * T, 0,
                    attack_ground=5, attack_range_ground=4 * T,
                    cooldown_timer=100, cooldown_ground=10)

        result, _ = resolve_combat(
            {"h1": hydra, "e1": enemy},
            {"p1_mineral": 1000, "p2_mineral": 1000},
            [],
            tick=10
        )
        # Marine may attack hydra, but hydra deals 0 damage
        assert result["e1"]["health"] == 200


# ═══════════════════════════════════════════════════════════
# Integration: Protoss merge
# ═══════════════════════════════════════════════════════════
class TestProtossMeld:
    def test_templar_meld_creates_archon_cocoon(self):
        """Meld spell consumes 2 Templars and creates a morphing Archon."""
        t1 = _e("t1", 1, "Templar", 40, 0, 0, shields=40, max_shields=40,
                is_spellcaster=True, energy=50, mp=50)
        t2 = _e("t2", 1, "Templar", 40, 1 * T, 0, shields=40, max_shields=40,
                is_spellcaster=True, energy=50, mp=50)
        entities = {"t1": t1, "t2": t2}
        cmds = [{"action": "spell", "caster_id": "t1", "spell": "meld"}]
        result, _ = process_spells(entities, {"p1_mineral": 1000}, cmds, tick=1)
        # Both templars should be gone
        assert "t1" not in result
        assert "t2" not in result
        # Archon cocoon exists
        archon_ids = [k for k in result if result[k].get("unit_type") == "Archon"]
        assert len(archon_ids) == 1
        cocoon = result[archon_ids[0]]
        assert cocoon["morphing"] is True
        assert cocoon["morph_target"] == "Archon"
        assert cocoon["morph_timer"] > 0
        # Combined shields preserved
        assert cocoon["shields"] > 0

    def test_dark_templar_meld_creates_dark_archon(self):
        dt1 = _e("dt1", 1, "DarkTemplar", 80, 0, 0, shields=40, max_shields=40)
        dt2 = _e("dt2", 1, "DarkTemplar", 80, 1 * T, 0, shields=40, max_shields=40)
        entities = {"dt1": dt1, "dt2": dt2}
        cmds = [{"action": "spell", "caster_id": "dt1", "spell": "darkmeld"}]
        result, _ = process_spells(entities, {"p1_mineral": 1000}, cmds, tick=1)
        assert "dt1" not in result
        assert "dt2" not in result
        da_ids = [k for k in result if result[k].get("unit_type") == "DarkArchon"]
        assert len(da_ids) == 1
        da = result[da_ids[0]]
        assert da["morphing"] is True
        assert da["morph_target"] == "DarkArchon"

    def test_meld_no_partner_noop(self):
        """If no nearby Templar partner, meld does nothing."""
        t1 = _e("t1", 1, "Templar", 40, 0, 0, shields=40,
                is_spellcaster=True, energy=50, mp=50)
        entities = {"t1": t1}
        cmds = [{"action": "spell", "caster_id": "t1", "spell": "meld"}]
        result, _ = process_spells(entities, {"p1_mineral": 1000}, cmds, tick=1)
        # t1 should still exist (no partner found)
        assert "t1" in result

    def test_meld_cocoon_completes_to_archon(self):
        """After merge_ticks, construction morph processor spawns the full Archon."""
        t1 = _e("t1", 1, "Templar", 40, 0, 0, shields=40, max_shields=40)
        t2 = _e("t2", 1, "Templar", 40, 1 * T, 0, shields=40, max_shields=40)
        entities = {"t1": t1, "t2": t2}
        cmds = [{"action": "spell", "caster_id": "t1", "spell": "meld"}]
        result, _ = process_spells(entities, {"p1_mineral": 1000}, cmds, tick=1)

        # Find cocoon
        cocoon_id = [k for k in result if result[k].get("unit_type") == "Archon"][0]
        cocoon = result[cocoon_id]
        cocoon["morph_timer"] = 2  # speed up

        built, _ = process_construction(result, {"p1_mineral": 1000}, [], tick=10)
        built2, _ = process_construction(built, {"p1_mineral": 1000}, [], tick=11)

        # Cocoon should be gone, replaced by a full Archon
        assert cocoon_id not in built2
        archon_ids = [k for k in built2 if built2[k].get("unit_type") == "Archon"]
        assert len(archon_ids) == 1
        archon = built2[archon_ids[0]]
        assert archon["attack_ground"] > 0
        assert archon["speed"] > 0
        assert not archon.get("morphing", False)


# ═══════════════════════════════════════════════════════════
# Spell categories & config
# ═══════════════════════════════════════════════════════════
class TestSpellRegistry:
    def test_morph_spells_registered(self):
        assert SPELL_CATEGORIES["lurker_morph"] == "TRANSFORM"
        assert SPELL_CATEGORIES["guardian_morph"] == "TRANSFORM"
        assert SPELL_CATEGORIES["devourer_morph"] == "TRANSFORM"

    def test_meld_spells_registered(self):
        assert SPELL_CATEGORIES["meld"] == "SUMMON"
        assert SPELL_CATEGORIES["darkmeld"] == "SUMMON"

    def test_morph_configs_exist(self):
        for s in ("lurker_morph", "guardian_morph", "devourer_morph"):
            assert s in SPELL_CONFIG
            assert "morph_ticks" in SPELL_CONFIG[s]

    def test_meld_configs_exist(self):
        for s in ("meld", "darkmeld"):
            assert s in SPELL_CONFIG
            assert "merge_ticks" in SPELL_CONFIG[s]
