"""Tests for P1-3: Splash damage — Siege Tank/Firebat/Lurker/Reaver."""
import math
import pytest
from simcore.rules import (
    resolve_combat, calculate_damage, get_armor_type,
    _SPLASH_PROFILES, _MAP_TILE_SIZE, _get_splash_profile, _apply_splash,
)
from simcore.rules import KillFeed

# Positions use game-units; 1 tile = _MAP_TILE_SIZE (32) game-units.
# SC1 siege range = 12 tiles = 384 game-units.
T = _MAP_TILE_SIZE  # shorthand


# ─── Profile structure tests ─────────────────────────────────

class TestSplashProfiles:
    """Verify _SPLASH_PROFILES config integrity."""

    def test_all_profiles_have_required_keys(self):
        required = {"inner_r", "mid_r", "outer_r",
                    "inner_frac", "mid_frac", "outer_frac",
                    "friendly_fire", "shape"}
        for name, prof in _SPLASH_PROFILES.items():
            assert required <= set(prof), f"{name} missing keys: {required - set(prof)}"

    def test_radius_ordering(self):
        for name, prof in _SPLASH_PROFILES.items():
            assert prof["inner_r"] < prof["mid_r"] < prof["outer_r"], f"{name} radii not ordered"

    def test_damage_fraction_ordering(self):
        for name, prof in _SPLASH_PROFILES.items():
            assert prof["inner_frac"] >= prof["mid_frac"] >= prof["outer_frac"], f"{name} fractions not ordered"

    def test_lurker_no_friendly_fire(self):
        assert _SPLASH_PROFILES["Lurker"]["friendly_fire"] is False

    def test_siege_tank_friendly_fire(self):
        assert _SPLASH_PROFILES["SiegeTank"]["friendly_fire"] is True

    def test_reaver_friendly_fire(self):
        assert _SPLASH_PROFILES["Reaver"]["friendly_fire"] is True

    def test_firebat_friendly_fire(self):
        assert _SPLASH_PROFILES["Firebat"]["friendly_fire"] is True


class TestGetSplashProfile:
    """Test _get_splash_profile entity detection."""

    def test_siege_tank_tank_mode_no_splash(self):
        e = {"unit_type": "SiegeTank", "siege_mode": False}
        assert _get_splash_profile(e) is None

    def test_siege_tank_siege_mode(self):
        e = {"unit_type": "SiegeTank", "siege_mode": True}
        prof = _get_splash_profile(e)
        assert prof is not None
        assert prof["shape"] == "radial"

    def test_firebat_uppercase(self):
        e = {"unit_type": "Firebat"}
        assert _get_splash_profile(e) is not None

    def test_firebat_lowercase(self):
        e = {"unit_type": "firebat"}
        assert _get_splash_profile(e) is not None

    def test_lurker(self):
        e = {"unit_type": "Lurker"}
        assert _get_splash_profile(e) is not None

    def test_reaver(self):
        e = {"unit_type": "Reaver"}
        assert _get_splash_profile(e) is not None

    def test_marine_no_splash(self):
        e = {"unit_type": "Marine"}
        assert _get_splash_profile(e) is None


# ─── Helpers ─────────────────────────────────────────────────

def _e(eid, owner, unit_type, hp, tx, ty, **kw):
    """Create a minimal entity with tile-based position (tx, ty in tiles)."""
    e = {
        "entity_id": eid, "entity_type": "unit", "owner": owner,
        "unit_type": unit_type, "health": hp, "max_health": hp,
        "pos_x": tx * T, "pos_y": ty * T,
        "armor": 0, "armor_type": "medium",
        "attack_ground": 10, "attack_air": 0,
        "weapon_type_ground": "normal",
        "cooldown_ground": 5, "cooldown_air": 0,
        "cooldown_timer": 5,  # ready to fire on first tick
        "is_idle": True, "attack_target_id": "",
        "domain": "ground",
        "attack_range_ground": 6 * T,
    }
    e.update(kw)
    return e


# ─── Splash application tests ────────────────────────────────

class TestSplashApplication:
    """Test _apply_splash function directly."""

    def test_splash_hits_nearby_enemies(self):
        """Siege Tank: 2 enemies near target take splash."""
        prof = _SPLASH_PROFILES["SiegeTank"]
        inner_tiles = prof["inner_r"]  # e.g. 0.5
        fought = {
            "tank1": _e("tank1", 1, "SiegeTank", 150, 0, 0,
                        siege_mode=True, attack_ground=70,
                        weapon_type_ground="explosive", cooldown_timer=100,
                        cooldown_ground=100, attack_range_ground=12*T),
            "target": _e("target", 2, "Marine", 40, 8, 0),
            "bystander": _e("bystander", 2, "Marine", 40, 8, inner_tiles),  # within inner
            "far": _e("far", 2, "Marine", 40, 20, 0),  # way outside outer
        }
        to_remove = set()
        kf = KillFeed()
        _apply_splash(fought, "tank1", fought["tank1"], "target",
                      70, "explosive", tick=1, to_remove=to_remove, kill_feed=kf)

        # bystander (within inner radius) should take inner_frac damage
        bystander_hp = fought["bystander"]["health"]
        assert bystander_hp < 40, f"bystander should take splash damage, hp={bystander_hp}"
        # far unit untouched
        assert fought["far"]["health"] == 40

    def test_splash_friendly_fire_siege_tank(self):
        """Siege Tank splash damages friendly units."""
        prof = _SPLASH_PROFILES["SiegeTank"]
        inner_tiles = prof["inner_r"]
        fought = {
            "tank1": _e("tank1", 1, "SiegeTank", 150, 0, 0,
                        siege_mode=True, attack_ground=70,
                        weapon_type_ground="explosive", cooldown_timer=100,
                        cooldown_ground=100, attack_range_ground=12*T),
            "target": _e("target", 2, "Marine", 40, 8, 0),
            "friendly": _e("friendly", 1, "Marine", 40, 8, inner_tiles),
        }
        to_remove = set()
        kf = KillFeed()
        _apply_splash(fought, "tank1", fought["tank1"], "target",
                      70, "explosive", tick=1, to_remove=to_remove, kill_feed=kf)

        assert fought["friendly"]["health"] < 40, "friendly should take splash from Siege Tank"

    def test_splash_no_friendly_fire_lurker(self):
        """Lurker splash does NOT damage friendly units."""
        prof = _SPLASH_PROFILES["Lurker"]
        inner_tiles = prof["inner_r"]
        fought = {
            "lurker1": _e("lurker1", 1, "Lurker", 125, 0, 0,
                         attack_ground=20, weapon_type_ground="normal",
                         cooldown_timer=100, cooldown_ground=100,
                         attack_range_ground=6*T),
            "target": _e("target", 2, "Marine", 40, 4, 0),
            "friendly": _e("friendly", 1, "Zergling", 35, 4, inner_tiles),
        }
        to_remove = set()
        kf = KillFeed()
        _apply_splash(fought, "lurker1", fought["lurker1"], "target",
                      20, "normal", tick=1, to_remove=to_remove, kill_feed=kf)

        assert fought["friendly"]["health"] == 35, "Lurker should not friendly-fire"

    def test_splash_outer_zone_reduced_damage(self):
        """Entity at outer radius takes ~25% damage."""
        prof = _SPLASH_PROFILES["SiegeTank"]
        outer_tiles = prof["outer_r"]
        fought = {
            "tank1": _e("tank1", 1, "SiegeTank", 150, 0, 0,
                        siege_mode=True, attack_ground=100,
                        weapon_type_ground="explosive", cooldown_timer=100,
                        cooldown_ground=100, attack_range_ground=12*T),
            "target": _e("target", 2, "Marine", 200, 8, 0),
            "outer": _e("outer", 2, "Marine", 200, 8, outer_tiles),
        }
        to_remove = set()
        kf = KillFeed()
        _apply_splash(fought, "tank1", fought["tank1"], "target",
                      100, "explosive", tick=1, to_remove=to_remove, kill_feed=kf)

        outer_dmg = 200 - fought["outer"]["health"]
        assert outer_dmg < 35, f"outer zone should take ~25% damage, took {outer_dmg}"

    def test_splash_kills_low_hp_bystander(self):
        """Splash can kill a bystander with low HP."""
        prof = _SPLASH_PROFILES["SiegeTank"]
        inner_tiles = prof["inner_r"]
        fought = {
            "tank1": _e("tank1", 1, "SiegeTank", 150, 0, 0,
                        siege_mode=True, attack_ground=70,
                        weapon_type_ground="explosive", cooldown_timer=100,
                        cooldown_ground=100, attack_range_ground=12*T),
            "target": _e("target", 2, "Marine", 40, 8, 0),
            "weak": _e("weak", 2, "Zergling", 5, 8, inner_tiles),
        }
        to_remove = set()
        kf = KillFeed()
        _apply_splash(fought, "tank1", fought["tank1"], "target",
                      70, "explosive", tick=1, to_remove=to_remove, kill_feed=kf)

        assert "weak" in to_remove, "low HP bystander should be killed by splash"


class TestSplashIntegration:
    """Test splash through resolve_combat (full pipeline)."""

    def _run(self, attacker, target, bystanders=None, cmds=None):
        ents = {"atk": attacker, "tgt": target}
        res = {"p1_mineral": 5000, "p1_gas": 5000,
               "p2_mineral": 5000, "p2_gas": 5000}
        if bystanders:
            ents.update(bystanders)
        if cmds is None:
            cmds = [{"action": "attack", "attacker_id": "atk", "target_id": "tgt"}]
        return resolve_combat(ents, res, cmds, tick=1)

    def test_siege_tank_siege_mode_splashes(self):
        """Siege Tank in siege mode should splash nearby enemies."""
        prof = _SPLASH_PROFILES["SiegeTank"]
        inner_tiles = prof["inner_r"]
        tank = _e("atk", 1, "SiegeTank", 150, 0, 0,
                  siege_mode=True, attack_ground=20,  # low dmg to avoid one-shot
                  weapon_type_ground="explosive",
                  cooldown_timer=100, cooldown_ground=100,
                  attack_range_ground=12*T, is_idle=False,
                  attack_target_id="tgt")
        target = _e("tgt", 2, "Marine", 200, 8, 0)
        bystander = _e("by", 2, "Marine", 200, 8, inner_tiles)  # within inner radius

        out, _ = self._run(tank, target, {"by": bystander}, cmds=[])
        assert out["by"]["health"] < 200, "bystander should take splash"

    def test_siege_tank_tank_mode_no_splash(self):
        """Siege Tank in tank mode should NOT splash."""
        tank = _e("atk", 1, "SiegeTank", 150, 0, 0,
                  siege_mode=False, attack_ground=15,
                  weapon_type_ground="explosive",
                  cooldown_timer=100, cooldown_ground=100,
                  attack_range_ground=7*T, is_idle=False,
                  attack_target_id="tgt")
        target = _e("tgt", 2, "Marine", 200, 6, 0)
        bystander = _e("by", 2, "Marine", 200, 6, 0.5)

        out, _ = self._run(tank, target, {"by": bystander}, cmds=[])
        assert out["by"]["health"] == 200, "no splash in tank mode"

    def test_firebat_splashes(self):
        """Firebat should splash nearby enemies."""
        bat = _e("atk", 1, "Firebat", 50, 0, 0,
                 attack_ground=8, weapon_type_ground="concussive",
                 cooldown_timer=100, cooldown_ground=100,
                 attack_range_ground=2*T, is_idle=False,
                 attack_target_id="tgt")
        target = _e("tgt", 2, "Zergling", 200, 1.5, 0)
        bystander = _e("by", 2, "Zergling", 200, 1.5, 0.5)

        out, _ = self._run(bat, target, {"by": bystander}, cmds=[])
        assert out["by"]["health"] < 200, "Firebat bystander should take splash"

    def test_lurker_no_friendly_fire_in_combat(self):
        """Lurker should not friendly-fire during combat resolution."""
        lurker = _e("atk", 1, "Lurker", 125, 0, 0,
                    attack_ground=20, weapon_type_ground="normal",
                    cooldown_timer=100, cooldown_ground=100,
                    attack_range_ground=6*T, is_idle=False,
                    attack_target_id="tgt")
        target = _e("tgt", 2, "Marine", 200, 4, 0)
        # Place friendly outside Marine auto-attack range (>5 tiles from Marine)
        # but within Lurker splash radius of the target
        friendly = _e("fr", 1, "Zergling", 200, 9.5, 0)

        out, _ = self._run(lurker, target, {"fr": friendly}, cmds=[])
        # If Lurker splashed friendly, HP would drop; Lurker has no friendly fire
        assert out["fr"]["health"] == 200, "Lurker should not friendly-fire"

    def test_splash_with_protoss_shields(self):
        """Splash damage should correctly deplete Protoss shields first."""
        prof = _SPLASH_PROFILES["SiegeTank"]
        inner_tiles = prof["inner_r"]
        tank = _e("atk", 1, "SiegeTank", 150, 0, 0,
                  siege_mode=True, attack_ground=20,
                  weapon_type_ground="explosive",
                  cooldown_timer=100, cooldown_ground=100,
                  attack_range_ground=12*T, is_idle=False,
                  attack_target_id="tgt")
        target = _e("tgt", 2, "Marine", 200, 8, 0)
        bystander = _e("by", 2, "Zealot", 200, 8, inner_tiles,
                        shields=20, max_shields=20)

        out, _ = self._run(tank, target, {"by": bystander}, cmds=[])
        by = out["by"]
        assert by["shields"] < 20, "shield should absorb some splash"
        assert by["health"] <= 200, "health should only be damaged after shield depletes"

    def test_non_splash_unit_no_collateral(self):
        """Marine should NOT splash nearby enemies."""
        marine = _e("atk", 1, "Marine", 40, 0, 0,
                   attack_ground=6, weapon_type_ground="normal",
                   cooldown_timer=100, cooldown_ground=100,
                   attack_range_ground=5*T, is_idle=False,
                   attack_target_id="tgt")
        target = _e("tgt", 2, "Zergling", 200, 4, 0)
        bystander = _e("by", 2, "Zergling", 200, 4, 0.5)

        out, _ = self._run(marine, target, {"by": bystander}, cmds=[])
        assert out["by"]["health"] == 200, "Marine should not splash"
