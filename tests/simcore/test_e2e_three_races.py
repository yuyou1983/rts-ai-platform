"""P3-5: End-to-end three-race feature validation.

Validates that each race's unique P3 features work correctly in
integrated scenarios (transport, nydus, scarab, spell, morph, meld).
Uses direct function calls to keep tests fast and deterministic.
"""
import math
import pytest
from simcore.transport import process_transport, process_nydus
from simcore.construction import process_construction
from simcore.rules import resolve_combat
from simcore.spells import process_spells

T = 32.0  # tile size


# ─── Helpers ────────────────────────────────────────────

def _transport(tid="ds1", owner=1, utype="Dropship", pos=(200, 200),
               loaded=None, capacity=8, flying=True, abilities=None):
    return {
        "id": tid, "owner": owner, "entity_type": "unit", "unit_type": utype,
        "pos_x": pos[0], "pos_y": pos[1],
        "health": 150, "max_health": 150,
        "is_transport": True, "loaded_units": loaded or [],
        "cargo_capacity": capacity, "cargo_used": len(loaded or []),
        "is_flying": flying, "is_idle": True, "attack_target_id": "",
        "domain": "air" if flying else "ground",
        "abilities": abilities or [],
    }


def _unit(uid="u1", owner=1, utype="Marine", pos=(200, 203),
          hp=40, domain="ground", flying=False, **kw):
    return {
        "id": uid, "owner": owner, "entity_type": "unit", "unit_type": utype,
        "pos_x": pos[0], "pos_y": pos[1],
        "health": hp, "max_health": hp,
        "armor": kw.get("armor", 0), "domain": domain,
        "attack_ground": kw.get("attack_ground", 6),
        "attack_air": kw.get("attack_air", 0),
        "cooldown_ground": kw.get("cooldown_ground", 15),
        "cooldown_air": kw.get("cooldown_air", 0),
        "attack_range_ground": kw.get("attack_range_ground", 128),
        "attack_range_air": kw.get("attack_range_air", 0),
        "cooldown_timer": kw.get("cooldown_timer", 15),
        "base_speed": kw.get("base_speed", 3.0),
        "is_idle": kw.get("is_idle", True),
        "attack_target_id": kw.get("attack_target_id", ""),
        "target_x": None, "target_y": None,
        "returning_to_base": False, "deposit_pending": False,
        "is_flying": flying, "is_transport": False,
        "loaded_units": [], "cargo_capacity": 0, "cargo_used": 0,
        "stasis": False, "morphing": False,
        "scarab_count": kw.get("scarab_count", 0),
        "scarab_capacity": kw.get("scarab_capacity", 0),
        "scarab_building": False, "scarab_timer": 0,
        "energy": kw.get("energy", 0),
        "max_energy": kw.get("max_energy", 200),
        "is_spellcaster": kw.get("is_spellcaster", False),
        "shields": kw.get("shields", 0),
    }


def _building(bid="b1", owner=1, btype="Barracks", pos=(100, 100),
              hp=1000, constructing=False, **kw):
    return {
        "id": bid, "owner": owner, "entity_type": "building",
        "building_type": btype, "unit_type": btype,
        "pos_x": pos[0], "pos_y": pos[1],
        "health": hp, "max_health": hp,
        "is_constructing": constructing,
        "production_queue": kw.get("production_queue", []),
        "production_timers": kw.get("production_timers", []),
        "nydus_partner_id": kw.get("nydus_partner_id", ""),
    }


def _res(p1m=1000, p1g=0, p2m=1000, p2g=0):
    return {"p1_mineral": p1m, "p1_gas": p1g, "p2_mineral": p2m, "p2_gas": p2g}


# ─── Terran: Dropship + Bunker ───────────────────────────

class TestTerranTransport:
    def test_dropship_load_unload_marine(self):
        ds = _transport(tid="ds1", utype="Dropship")
        marine = _unit(uid="m1", utype="Marine")
        ents = {"ds1": ds, "m1": marine}
        # NOTE: process_transport uses "unit_ids" (list), not "unit_id"
        cmds = [{"action": "load", "transport_id": "ds1", "unit_ids": ["m1"]}]
        r, _ = process_transport(ents, _res(), cmds, 1)
        assert "m1" not in r  # Marine loaded into dropship
        assert r["ds1"]["cargo_used"] == 1
        # loaded_units stores passenger snapshots, not bare IDs
        assert len(r["ds1"]["loaded_units"]) == 1
        assert r["ds1"]["loaded_units"][0]["id"] == "m1"

        # Unload
        ucmds = [{"action": "unload", "transport_id": "ds1",
                  "unit_id": "m1", "target_x": 210, "target_y": 210}]
        r2, _ = process_transport(r, _res(), ucmds, 2)
        assert "m1" in r2
        assert r2["ds1"]["cargo_used"] == 0

    def test_bunker_load_unload_marine(self):
        bunker = _transport(tid="bk1", utype="Bunker", capacity=4,
                            flying=False, pos=(200, 200))
        marine = _unit(uid="m1", utype="Marine")
        ents = {"bk1": bunker, "m1": marine}
        cmds = [{"action": "load", "transport_id": "bk1", "unit_ids": ["m1"]}]
        r, _ = process_transport(ents, _res(), cmds, 1)
        assert r["bk1"]["cargo_used"] == 1
        assert len(r["bk1"]["loaded_units"]) == 1
        assert r["bk1"]["loaded_units"][0]["id"] == "m1"

    def test_dropship_full_rejects_load(self):
        ds = _transport(tid="ds1", utype="Dropship", capacity=1,
                        loaded=["m0"])
        ds["cargo_used"] = 1
        marine = _unit(uid="m1", utype="Marine")
        ents = {"ds1": ds, "m1": marine}
        cmds = [{"action": "load", "transport_id": "ds1", "unit_ids": ["m1"]}]
        r, _ = process_transport(ents, _res(), cmds, 1)
        # Marine NOT loaded (full)
        assert "m1" in r
        assert r["ds1"]["cargo_used"] == 1


# ─── Protoss: Shuttle + Reaver Scarab ──────────────────

class TestProtossTransportAndScarab:
    def test_shuttle_load_unload_zealot(self):
        shuttle = _transport(tid="sh1", utype="Shuttle", capacity=8)
        zealot = _unit(uid="z1", utype="Zealot", hp=100, shields=60)
        ents = {"sh1": shuttle, "z1": zealot}
        cmds = [{"action": "load", "transport_id": "sh1", "unit_ids": ["z1"]}]
        r, _ = process_transport(ents, _res(), cmds, 1)
        assert "z1" not in r
        assert r["sh1"]["cargo_used"] == 1

    def test_reaver_fires_consumes_scarab(self):
        reaver = _unit(uid="rv1", utype="Reaver", hp=100,
                       attack_ground=100, cooldown_ground=22,
                       attack_range_ground=256, cooldown_timer=22,
                       scarab_count=5, scarab_capacity=10,
                       is_spellcaster=True, energy=0)
        target = _unit(uid="t1", owner=2, utype="Ultralisk", hp=400,
                       armor=1, pos=(300, 100))
        reaver["attack_target_id"] = "t1"
        reaver["is_idle"] = False
        ents = {"rv1": reaver, "t1": target}
        r, _ = resolve_combat(ents, _res(), [], 1)
        assert r["rv1"]["scarab_count"] == 4
        assert r["t1"]["health"] == 400 - (100 - 1)  # 99 dmg after armor

    def test_reaver_no_scarab_cannot_fire(self):
        reaver = _unit(uid="rv1", utype="Reaver", hp=100,
                       attack_ground=100, cooldown_ground=22,
                       attack_range_ground=256, cooldown_timer=22,
                       scarab_count=0, scarab_capacity=10,
                       is_spellcaster=True, energy=0)
        target = _unit(uid="t1", owner=2, utype="Ultralisk", hp=400,
                       armor=1, pos=(300, 100))
        reaver["attack_target_id"] = "t1"
        reaver["is_idle"] = False
        ents = {"rv1": reaver, "t1": target}
        r, _ = resolve_combat(ents, _res(), [], 1)
        assert r["t1"]["health"] == 400  # no damage

    def test_reaver_build_scarab_deducts_mineral(self):
        reaver = _unit(uid="rv1", utype="Reaver", hp=100,
                       scarab_count=3, scarab_capacity=10)
        ents = {"rv1": reaver}
        cmds = [{"action": "build_scarab", "unit_id": "rv1"}]
        r, res = process_construction(ents, _res(p1m=100), cmds, 1)
        assert res["p1_mineral"] == 85
        assert r["rv1"]["scarab_building"] is True


# ─── Zerg: Overlord + Nydus Canal ───────────────────────

class TestZergTransportAndNydus:
    def test_overlord_load_with_transport_ability(self):
        ov = _transport(tid="ov1", utype="Overlord", capacity=8,
                        flying=True, pos=(200, 200),
                        abilities=["transport"])
        drone = _unit(uid="d1", utype="Drone", hp=40, pos=(200, 203))
        ents = {"ov1": ov, "d1": drone}
        cmds = [{"action": "load", "transport_id": "ov1", "unit_ids": ["d1"]}]
        r, _ = process_transport(ents, _res(), cmds, 1)
        assert r["ov1"]["cargo_used"] == 1
        assert "d1" not in r

    def test_overlord_rejects_without_transport_ability(self):
        ov = _transport(tid="ov1", utype="Overlord", capacity=8,
                        flying=True, pos=(200, 200),
                        abilities=[])  # No transport ability
        drone = _unit(uid="d1", utype="Drone", hp=40, pos=(200, 203))
        ents = {"ov1": ov, "d1": drone}
        cmds = [{"action": "load", "transport_id": "ov1", "unit_ids": ["d1"]}]
        r, _ = process_transport(ents, _res(), cmds, 1)
        assert r["ov1"]["cargo_used"] == 0
        assert "d1" in r  # drone NOT loaded

    def test_nydus_link_and_teleport(self):
        ca = _building(bid="nc1", btype="NydusCanal", owner=1, pos=(100, 100))
        cb = _building(bid="nc2", btype="NydusCanal", owner=1, pos=(800, 800))
        zerg = _unit(uid="z1", owner=1, utype="Zergling", hp=35, pos=(101, 101))
        ents = {"nc1": ca, "nc2": cb, "z1": zerg}
        res = _res()

        # Link — API uses "canal_id" + "partner_id" (bidirectional)
        cmds = [{"action": "nydus_link", "canal_id": "nc1", "partner_id": "nc2"}]
        r, _ = process_nydus(ents, res, cmds, 1)
        assert r["nc1"]["nydus_partner_id"] == "nc2"
        assert r["nc2"]["nydus_partner_id"] == "nc1"

        # Enter
        enter = [{"action": "nydus_enter", "unit_id": "z1", "canal_id": "nc1"}]
        r2, _ = process_nydus(r, res, enter, 2)
        assert abs(r2["z1"]["pos_x"] - 800) < 2 * T
        assert abs(r2["z1"]["pos_y"] - 800) < 2 * T


# ─── Spells: cross-race validation ──────────────────────

class TestSpellIntegration:
    def test_stasis_field_blocks_damage(self):
        caster = _unit(uid="da1", owner=1, utype="DarkArchon",
                       energy=150, is_spellcaster=True, pos=(100, 100))
        victim = _unit(uid="v1", owner=2, utype="Marine", hp=40, pos=(120, 100))
        ents = {"da1": caster, "v1": victim}

        # Cast stasisfield (AREA type, needs target_x/target_y)
        cmds = [{"action": "spell", "caster_id": "da1", "spell": "stasisfield",
                 "target_id": "v1", "target_x": 120, "target_y": 100}]
        r, _ = process_spells(ents, _res(), cmds, 1)
        # stasisfield is AREA, affects units in radius
        assert r["v1"].get("stasis") is True

        # Try attacking stasis'd unit
        attacker = _unit(uid="a1", owner=1, utype="Zealot",
                         attack_ground=8, cooldown_ground=22,
                         attack_range_ground=32, cooldown_timer=22,
                         attack_target_id="v1", is_idle=False, pos=(130, 100))
        combat_ents = {**r, "a1": attacker}
        cr, _ = resolve_combat(combat_ents, _res(), [], 2)
        # No damage to stasis'd unit
        assert cr["v1"]["health"] == 40

    def test_irradiate_marks_target(self):
        caster = _unit(uid="sv1", owner=1, utype="ScienceVessel",
                       energy=100, is_spellcaster=True, pos=(100, 100))
        target = _unit(uid="h1", owner=2, utype="Hydralisk", hp=80, pos=(120, 100))
        ents = {"sv1": caster, "h1": target}

        cmds = [{"action": "spell", "caster_id": "sv1", "spell": "irradiate",
                 "target_id": "h1", "target_x": 120, "target_y": 100}]
        r, _ = process_spells(ents, _res(), cmds, 1)
        # Irradiate adds a buff to target's buffs list
        buffs = r["h1"].get("buffs", [])
        irradiate_buffs = [b for b in buffs if b.get("type") == "irradiate"]
        assert len(irradiate_buffs) == 1
        assert irradiate_buffs[0]["remaining"] == 120

    def test_mind_control_switches_owner(self):
        caster = _unit(uid="da1", owner=1, utype="DarkArchon",
                       energy=150, is_spellcaster=True, pos=(100, 100))
        target = _unit(uid="w1", owner=2, utype="SCV", hp=60, pos=(120, 100))
        ents = {"da1": caster, "w1": target}

        cmds = [{"action": "spell", "caster_id": "da1", "spell": "mindcontrol",
                 "target_id": "w1", "target_x": 120, "target_y": 100}]
        r, _ = process_spells(ents, _res(), cmds, 1)
        assert r["w1"]["owner"] == 1  # switched sides


# ─── Combat + economy integration ───────────────────────

class TestCombatEconomyIntegration:
    def test_marine_vs_hydralisk_damage(self):
        marine = _unit(uid="m1", owner=1, utype="Marine",
                       attack_ground=6, cooldown_ground=15,
                       attack_range_ground=128, cooldown_timer=15,
                       attack_target_id="h1", is_idle=False, pos=(200, 100))
        hydra = _unit(uid="h1", owner=2, utype="Hydralisk", hp=80,
                       armor=1, pos=(250, 100))
        ents = {"m1": marine, "h1": hydra}
        r, _ = resolve_combat(ents, _res(), [], 1)
        # Marine fires: 6 dmg - 1 armor = 5 net
        assert r["h1"]["health"] == 75

    def test_zealot_vs_zergling_dual_strike(self):
        zealot = _unit(uid="z1", owner=1, utype="Zealot",
                       attack_ground=8, cooldown_ground=22,
                       attack_range_ground=32, cooldown_timer=22,
                       attack_target_id="zl1", is_idle=False, pos=(200, 100))
        zergling = _unit(uid="zl1", owner=2, utype="Zergling", hp=35,
                          armor=0, pos=(210, 100))
        ents = {"z1": zealot, "zl1": zergling}
        r, _ = resolve_combat(ents, _res(), [], 1)
        # Zealot deals 8 damage (2x4 blades in SC1, simplified to 8 here)
        assert r["zl1"]["health"] == 35 - 8

    def test_siege_tank_splash(self):
        tank = _unit(uid="st1", owner=1, utype="SiegeTank",
                     attack_ground=70, cooldown_ground=50,
                     attack_range_ground=384, cooldown_timer=50,
                     attack_target_id="h1", is_idle=False, pos=(200, 100))
        # Siege Tank only splashes in siege mode
        tank["siege_mode"] = True
        hydra = _unit(uid="h1", owner=2, utype="Hydralisk", hp=80,
                      armor=1, pos=(280, 100))
        # Nearby unit for splash — must be within splash radius (in tiles)
        drone = _unit(uid="d1", owner=2, utype="Drone", hp=40,
                      armor=0, pos=(290, 100))
        ents = {"st1": tank, "h1": hydra, "d1": drone}
        r, _ = resolve_combat(ents, _res(), [], 1)
        # Primary target takes heavy damage
        assert r["h1"]["health"] < 80
        # Splash target (40 HP) may be killed by splash — removed from result
        assert "d1" not in r or r["d1"]["health"] < 40
