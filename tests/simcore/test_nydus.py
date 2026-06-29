"""Tests for P3-3: Nydus Canal — link pairing and unit teleport."""
import math
import pytest
from simcore.transport import process_nydus

T = 32.0  # _MAP_TILE_SIZE


def _canal(eid: str, owner: int = 1, pos_x: float = 0, pos_y: float = 0,
           constructing: bool = False, hp: float = 250) -> dict:
    return {
        "id": eid, "owner": owner,
        "entity_type": "building", "building_type": "NydusCanal",
        "unit_type": "NydusCanal",
        "pos_x": pos_x, "pos_y": pos_y,
        "health": hp, "max_health": 250,
        "is_constructing": constructing,
        "nydus_partner_id": "",
    }


def _unit(eid: str, owner: int = 1, pos_x: float = 0, pos_y: float = 0,
          domain: str = "ground", stasis: bool = False, hp: float = 40) -> dict:
    return {
        "id": eid, "owner": owner,
        "entity_type": "soldier", "unit_type": "Zergling",
        "pos_x": pos_x, "pos_y": pos_y,
        "health": hp, "max_health": 40,
        "domain": domain, "stasis": stasis,
        "is_idle": True,
        "target_x": None, "target_y": None,
        "attack_target_id": "", "returning_to_base": False,
        "deposit_pending": False,
    }


def _run(entities: dict, commands: list, tick: int = 1):
    res = {"p1_mineral": 1000}
    return process_nydus(entities, res, commands, tick)


class TestNydusLink:
    def test_link_two_canals(self):
        ents = {"nc1": _canal("nc1"), "nc2": _canal("nc2", pos_x=1000)}
        cmds = [{"action": "nydus_link", "canal_id": "nc1", "partner_id": "nc2"}]
        result, _ = _run(ents, cmds)
        assert result["nc1"]["nydus_partner_id"] == "nc2"
        assert result["nc2"]["nydus_partner_id"] == "nc1"

    def test_link_different_owner_rejected(self):
        ents = {"nc1": _canal("nc1", owner=1), "nc2": _canal("nc2", owner=2)}
        cmds = [{"action": "nydus_link", "canal_id": "nc1", "partner_id": "nc2"}]
        result, _ = _run(ents, cmds)
        assert result["nc1"]["nydus_partner_id"] == ""
        assert result["nc2"]["nydus_partner_id"] == ""

    def test_link_constructing_rejected(self):
        ents = {"nc1": _canal("nc1", constructing=True), "nc2": _canal("nc2")}
        cmds = [{"action": "nydus_link", "canal_id": "nc1", "partner_id": "nc2"}]
        result, _ = _run(ents, cmds)
        assert result["nc1"]["nydus_partner_id"] == ""

    def test_link_dead_canal_rejected(self):
        ents = {"nc1": _canal("nc1", hp=0), "nc2": _canal("nc2")}
        cmds = [{"action": "nydus_link", "canal_id": "nc1", "partner_id": "nc2"}]
        result, _ = _run(ents, cmds)
        assert result["nc2"].get("nydus_partner_id", "") == ""

    def test_link_non_nydus_rejected(self):
        b = {"id": "b1", "owner": 1, "entity_type": "building",
             "building_type": "Hatchery", "unit_type": "Hatchery",
             "health": 500, "is_constructing": False, "nydus_partner_id": ""}
        ents = {"nc1": _canal("nc1"), "b1": b}
        cmds = [{"action": "nydus_link", "canal_id": "nc1", "partner_id": "b1"}]
        result, _ = _run(ents, cmds)
        assert result["nc1"]["nydus_partner_id"] == ""


class TestNydusEnter:
    def test_teleport_ground_unit(self):
        """Unit near nc1 teleports to nc2's position."""
        nc1 = _canal("nc1", pos_x=100, pos_y=100)
        nc2 = _canal("nc2", owner=1, pos_x=2000, pos_y=3000)
        nc1["nydus_partner_id"] = "nc2"
        nc2["nydus_partner_id"] = "nc1"
        u = _unit("u1", pos_x=120, pos_y=110)  # within 1.5 tiles (~48px)
        ents = {"nc1": nc1, "nc2": nc2, "u1": u}
        cmds = [{"action": "nydus_enter", "unit_id": "u1", "canal_id": "nc1"}]
        result, _ = _run(ents, cmds)
        assert result["u1"]["pos_x"] == 2000
        assert result["u1"]["pos_y"] == 3000
        assert result["u1"]["is_idle"] is True
        assert result["u1"]["attack_target_id"] == ""

    def test_flying_unit_rejected(self):
        nc1 = _canal("nc1", pos_x=100, pos_y=100)
        nc2 = _canal("nc2", owner=1, pos_x=2000, pos_y=3000)
        nc1["nydus_partner_id"] = "nc2"
        nc2["nydus_partner_id"] = "nc1"
        u = _unit("u1", domain="air", pos_x=110, pos_y=105)
        ents = {"nc1": nc1, "nc2": nc2, "u1": u}
        cmds = [{"action": "nydus_enter", "unit_id": "u1", "canal_id": "nc1"}]
        result, _ = _run(ents, cmds)
        assert result["u1"]["pos_x"] == 110  # not teleported

    def test_out_of_range_rejected(self):
        nc1 = _canal("nc1", pos_x=100, pos_y=100)
        nc2 = _canal("nc2", owner=1, pos_x=2000, pos_y=3000)
        nc1["nydus_partner_id"] = "nc2"
        nc2["nydus_partner_id"] = "nc1"
        u = _unit("u1", pos_x=500, pos_y=500)  # far away
        ents = {"nc1": nc1, "nc2": nc2, "u1": u}
        cmds = [{"action": "nydus_enter", "unit_id": "u1", "canal_id": "nc1"}]
        result, _ = _run(ents, cmds)
        assert result["u1"]["pos_x"] == 500

    def test_no_partner_rejected(self):
        nc1 = _canal("nc1", pos_x=100, pos_y=100)
        u = _unit("u1", pos_x=110, pos_y=105)
        ents = {"nc1": nc1, "u1": u}
        cmds = [{"action": "nydus_enter", "unit_id": "u1", "canal_id": "nc1"}]
        result, _ = _run(ents, cmds)
        assert result["u1"]["pos_x"] == 110

    def test_stasis_unit_rejected(self):
        nc1 = _canal("nc1", pos_x=100, pos_y=100)
        nc2 = _canal("nc2", owner=1, pos_x=2000, pos_y=3000)
        nc1["nydus_partner_id"] = "nc2"
        nc2["nydus_partner_id"] = "nc1"
        u = _unit("u1", stasis=True, pos_x=110, pos_y=105)
        ents = {"nc1": nc1, "nc2": nc2, "u1": u}
        cmds = [{"action": "nydus_enter", "unit_id": "u1", "canal_id": "nc1"}]
        result, _ = _run(ents, cmds)
        assert result["u1"]["pos_x"] == 110

    def test_wrong_owner_rejected(self):
        nc1 = _canal("nc1", owner=1, pos_x=100, pos_y=100)
        nc2 = _canal("nc2", owner=1, pos_x=2000, pos_y=3000)
        nc1["nydus_partner_id"] = "nc2"
        nc2["nydus_partner_id"] = "nc1"
        u = _unit("u1", owner=2, pos_x=110, pos_y=105)
        ents = {"nc1": nc1, "nc2": nc2, "u1": u}
        cmds = [{"action": "nydus_enter", "unit_id": "u1", "canal_id": "nc1"}]
        result, _ = _run(ents, cmds)
        assert result["u1"]["pos_x"] == 110


class TestNydusPartnerCleanup:
    def test_dead_partner_cleared(self):
        nc1 = _canal("nc1", pos_x=100, pos_y=100)
        nc2 = _canal("nc2", owner=1, pos_x=2000, pos_y=3000, hp=0)
        nc1["nydus_partner_id"] = "nc2"
        nc2["nydus_partner_id"] = "nc1"
        ents = {"nc1": nc1, "nc2": nc2}
        result, _ = _run(ents, [])
        assert result["nc1"]["nydus_partner_id"] == ""

    def test_removed_partner_cleared(self):
        nc1 = _canal("nc1", pos_x=100, pos_y=100)
        nc1["nydus_partner_id"] = "nc_gone"
        ents = {"nc1": nc1}
        result, _ = _run(ents, [])
        assert result["nc1"]["nydus_partner_id"] == ""
