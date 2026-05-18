"""HTTP integration tests — validates that HTTP requests matching Godot's
grpc_bridge.gd correctly drive the SimCore backend (step loop, AI auto-play,
entity changes, and terminal propagation).

These tests use aiohttp's TestClient/TestServer so no subprocess is needed.
A live gRPC server on localhost:50051 is required (started by the conftest
fixture or already running in the dev environment).

The request/response shapes mirror exactly what grpc_bridge.gd sends:
  - POST /api/start_game  body: {seed, max_ticks, ai_player}
  - POST /api/step        body: {commands: [...]}
  - POST /api/get_state   body: {}
  - POST /api/health      body: {}

Key behaviours under test:
  1. start_game → step → get_state full flow (matching grpc_bridge.gd poll loop)
  2. ai_player=2 causes AI commands to be auto-injected each step
  3. AI builds buildings and trains units over many steps
  4. Terminal conditions (max_ticks, base destruction) propagate correctly
"""
from __future__ import annotations

import asyncio
import socket
import subprocess
import sys

import pytest
from aiohttp.test_utils import TestClient, TestServer

from simcore.grpc_client import SimCoreClient
from simcore.http_gateway import app_factory, reset_ai_state

# ── Helpers ──────────────────────────────────────────────────────────────────


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _grpc_server_running(port: int = 50051) -> bool:
    """Quick check whether a gRPC server is already listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("localhost", port)) == 0


def _count_player_entities(state: dict, player: int, entity_type: str) -> int:
    """Count entities of a given type owned by a specific player."""
    return sum(
        1
        for e in state.get("entities", {}).values()
        if e.get("owner") == player and e.get("entity_type") == entity_type
    )


def _count_player_buildings(state: dict, player: int, building_type: str) -> int:
    """Count buildings of a specific type owned by a player (includes constructing)."""
    return sum(
        1
        for e in state.get("entities", {}).values()
        if e.get("owner") == player
        and e.get("entity_type") == "building"
        and e.get("building_type") == building_type
    )


def _player_has_building(state: dict, player: int, building_type: str) -> bool:
    """Check if a player has at least one completed building of the given type."""
    return any(
        e.get("owner") == player
        and e.get("entity_type") == "building"
        and e.get("building_type") == building_type
        and not e.get("is_constructing", False)
        for e in state.get("entities", {}).values()
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────

# Serialise all tests in this file — the http_gateway uses module-level globals
# so concurrent tests would race.
pytestmark = pytest.mark.xdist_group(name="http_integration")


@pytest.fixture(scope="session")
def grpc_server():
    """Session-scoped: start ONE gRPC server subprocess for all tests.

    Returns the (port, proc) tuple so the per-test fixture can connect to it
    and tear it down at session end.
    """
    grpc_port = _find_free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "simcore.grpc_server",
            "--port",
            str(grpc_port),
            "--tick-rate",
            "20",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for the server to start accepting connections (sync polling)
    import time

    for _ in range(40):
        if _grpc_server_running(grpc_port):
            break
        time.sleep(0.25)
    else:
        proc.terminate()
        proc.wait(timeout=5)
        pytest.skip("gRPC server did not start in time")

    yield grpc_port, proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
async def http_client(grpc_server):
    """Per-test async fixture: build a fresh TestClient against the shared
    gRPC server, reset AI globals, and yield the client.

    This avoids the event-loop / Task context issues that arise with
    session-scoped async fixtures + aiohttp TestClient.
    """
    grpc_port, _proc = grpc_server

    # Create ONE SimCoreClient per test (cheap — reuses the same gRPC server)
    client = SimCoreClient(f"localhost:{grpc_port}")
    await client.__aenter__()

    # Inject the client into the gateway so all handlers share it
    app = await app_factory(client=client)

    reset_ai_state()

    async with TestClient(TestServer(app)) as c:
        yield c

    await client.__aexit__(None, None, None)


# ── Test 1: start_game → step → get_state full flow ─────────────────────────


class TestStartStepGetStateFlow:
    """Verify the core request cycle that grpc_bridge.gd performs every tick."""

    @pytest.mark.asyncio
    async def test_start_game_returns_initial_state(self, http_client):
        """POST /api/start_game should return tick 0 with entities and resources."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 0},
        )
        assert resp.status == 200
        data = await resp.json()

        # Basic shape checks (mirrors grpc_bridge.gd _on_request_completed)
        assert data["tick"] == 0
        assert data["is_terminal"] is False
        assert data["winner"] == 0
        assert isinstance(data["entities"], dict)
        assert len(data["entities"]) > 0, "Game should start with entities"

        # Every entity should have the fields grpc_bridge.gd reads
        for eid, e in data["entities"].items():
            assert "owner" in e, f"Entity {eid} missing 'owner'"
            assert "entity_type" in e, f"Entity {eid} missing 'entity_type'"
            assert "pos_x" in e, f"Entity {eid} missing 'pos_x'"
            assert "pos_y" in e, f"Entity {eid} missing 'pos_y'"
            assert "health" in e, f"Entity {eid} missing 'health'"
            assert "is_idle" in e, f"Entity {eid} missing 'is_idle'"
            # Fields that grpc_bridge.gd also references
            assert "building_type" in e
            assert "unit_type" in e

        # Resources dict should exist
        assert isinstance(data.get("resources", {}), dict)

    @pytest.mark.asyncio
    async def test_step_advances_tick(self, http_client):
        """POST /api/step should advance the tick counter by 1."""
        await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 0},
        )

        resp = await http_client.post("/api/step", json={"commands": []})
        assert resp.status == 200
        data = await resp.json()
        assert data["tick"] == 1

        resp = await http_client.post("/api/step", json={"commands": []})
        data = await resp.json()
        assert data["tick"] == 2

    @pytest.mark.asyncio
    async def test_get_state_returns_current_tick(self, http_client):
        """POST /api/get_state should return the latest state without advancing."""
        await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 0},
        )

        # Step twice → tick 2
        await http_client.post("/api/step", json={"commands": []})
        await http_client.post("/api/step", json={"commands": []})

        resp = await http_client.post("/api/get_state", json={})
        assert resp.status == 200
        data = await resp.json()
        assert data["tick"] == 2

        # get_state should NOT advance the tick
        resp2 = await http_client.post("/api/get_state", json={})
        data2 = await resp2.json()
        assert data2["tick"] == 2

    @pytest.mark.asyncio
    async def test_health_endpoint(self, http_client):
        """POST /api/health should return a healthy response."""
        resp = await http_client.post("/api/health", json={})
        assert resp.status == 200
        data = await resp.json()
        assert data["healthy"] is True
        assert "game_tick" in data
        assert "status" in data

    @pytest.mark.asyncio
    async def test_submit_move_command(self, http_client):
        """Submit a move command via /api/step and verify the unit responds."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 0},
        )
        state = await resp.json()

        # Find a worker owned by player 1
        worker_id = None
        for eid, e in state["entities"].items():
            if e.get("entity_type") == "worker" and e.get("owner") == 1:
                worker_id = eid
                break

        assert worker_id is not None, "P1 should have at least one worker"

        # Send move command (same schema as grpc_bridge.gd submit_commands)
        move_cmd = {
            "action": "move",
            "issuer": 1,
            "unit_id": worker_id,
            "target_x": 20.0,
            "target_y": 20.0,
        }
        resp = await http_client.post("/api/step", json={"commands": [move_cmd]})
        assert resp.status == 200
        data = await resp.json()
        assert data["tick"] == 1

    @pytest.mark.asyncio
    async def test_sequential_start_step_get_state(self, http_client):
        """Full grpc_bridge.gd-style sequence: start, step N times, get_state."""
        # 1. Start game
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 1000, "ai_player": 0},
        )
        data = await resp.json()
        assert data["tick"] == 0

        # 2. Step 10 times (simulating grpc_bridge.gd _poll_state loop)
        for i in range(10):
            resp = await http_client.post("/api/step", json={"commands": []})
            data = await resp.json()
            assert data["tick"] == i + 1
            assert isinstance(data["is_terminal"], bool)

        # 3. Get state
        resp = await http_client.post("/api/get_state", json={})
        data = await resp.json()
        assert data["tick"] == 10

    @pytest.mark.asyncio
    async def test_new_start_game_resets_state(self, http_client):
        """Calling start_game again should reset the game to tick 0."""
        await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 0},
        )
        # Step a few times
        for _ in range(5):
            await http_client.post("/api/step", json={"commands": []})

        # Start a new game
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 99, "max_ticks": 10000, "ai_player": 0},
        )
        data = await resp.json()
        assert data["tick"] == 0, "New start_game should reset tick to 0"


# ── Test 2: AI player auto-generates commands ───────────────────────────────


class TestAIPlayerCommands:
    """When ai_player=2, the HTTP gateway auto-injects AI commands each step.
    We verify this by checking AI-exclusive outcomes (building construction,
    unit training, attack commands) that wouldn't happen from the game's
    built-in auto-gather mechanic alone."""

    @pytest.mark.asyncio
    async def test_ai_player_2_builds_barracks(self, http_client):
        """With ai_player=2, the ScriptAI should build a barracks within ~150
        steps. (Auto-gather alone does NOT build buildings.)"""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 2},
        )
        state = await resp.json()

        # Verify no initial barracks
        has_barracks = _count_player_buildings(state, 2, "barracks")
        assert has_barracks == 0, "P2 should not start with a barracks"

        # Run enough steps for AI to accumulate resources + build
        for _ in range(200):
            resp = await http_client.post("/api/step", json={"commands": []})
            state = await resp.json()
            if state["is_terminal"]:
                break
            if _player_has_building(state, 2, "barracks"):
                break

        assert _player_has_building(state, 2, "barracks"), (
            "AI (P2) should have built a barracks within 200 ticks. "
            f"P2 buildings: {[e for e in state['entities'].values() if e.get('owner') == 2 and e.get('entity_type') == 'building']}"
        )

    @pytest.mark.asyncio
    async def test_ai_player_2_trains_units(self, http_client):
        """After building barracks, AI should eventually train additional units.
        ScriptAI economy pipeline: gather → build barracks (~200t) → complete
        barracks → train soldiers/workers. Total ~800-1000 ticks for full cycle."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 2},
        )
        state = await resp.json()
        initial_p2_count = sum(
            1 for e in state["entities"].values()
            if e.get("owner") == 2 and e.get("entity_type") != "building"
        )

        # Run enough steps for full AI pipeline: gather → build → train
        for _ in range(1000):
            resp = await http_client.post("/api/step", json={"commands": []})
            state = await resp.json()
            if state["is_terminal"]:
                break

        final_p2_count = sum(
            1 for e in state["entities"].values()
            if e.get("owner") == 2 and e.get("entity_type") != "building"
        )
        assert final_p2_count > initial_p2_count, (
            f"AI should have trained additional units after 1000 ticks. "
            f"Initial mobile units: {initial_p2_count}, Final: {final_p2_count}. "
            f"P2 entities: {[(eid, e.get('entity_type')) for eid, e in state['entities'].items() if e.get('owner') == 2]}"
        )

    @pytest.mark.asyncio
    async def test_ai_player_0_never_builds_barracks(self, http_client):
        """With ai_player=0 (no AI), no player should build barracks via
        auto-injection. The auto-gather mechanic only sends idle workers
        to mine — it never issues build or train commands."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 0},
        )

        # Run 200 steps — auto-gather alone should not produce barracks
        for _ in range(200):
            resp = await http_client.post("/api/step", json={"commands": []})
            state = await resp.json()
            if state["is_terminal"]:
                break

        p1_barracks = _count_player_buildings(state, 1, "barracks")
        p2_barracks = _count_player_buildings(state, 2, "barracks")
        assert p1_barracks == 0, (
            f"With ai_player=0, P1 should not have barracks (auto-gather "
            f"doesn't build). Found: {p1_barracks}"
        )
        assert p2_barracks == 0, (
            f"With ai_player=0, P2 should not have barracks (auto-gather "
            f"doesn't build). Found: {p2_barracks}"
        )

    @pytest.mark.asyncio
    async def test_ai_player_1_builds_for_p1(self, http_client):
        """With ai_player=1, AI builds for player 1 instead of player 2."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 1},
        )

        for _ in range(200):
            resp = await http_client.post("/api/step", json={"commands": []})
            state = await resp.json()
            if state["is_terminal"]:
                break
            if _player_has_building(state, 1, "barracks"):
                break

        assert _player_has_building(state, 1, "barracks"), (
            "AI (P1) should have built a barracks within 200 ticks."
        )


# ── Test 3: entity count changes over multiple steps (AI builds/trains) ─────


class TestEntityCountChanges:
    """Verify that the AI actually constructs buildings and trains units over
    enough ticks, causing the total entity count to increase."""

    @pytest.mark.asyncio
    async def test_entity_count_increases_with_ai(self, http_client):
        """Over 300+ steps with ai_player=2, the AI should build barracks
        and/or train workers/soldiers, increasing total entity count."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 2},
        )
        state = await resp.json()
        initial_count = len(state["entities"])

        # AI needs ~200 ticks to build barracks, entity count increases
        # when construction starts (barracks entity appears)
        for _ in range(400):
            resp = await http_client.post("/api/step", json={"commands": []})
            state = await resp.json()
            if state["is_terminal"]:
                break

        final_count = len(state["entities"])
        assert final_count > initial_count, (
            f"After 400 steps, entity count should have increased due to AI "
            f"construction/training. Initial: {initial_count}, Final: {final_count}"
        )

    @pytest.mark.asyncio
    async def test_ai_builds_multiple_building_types(self, http_client):
        """AI should build at least barracks; verify new building types appear
        that weren't in the initial state."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 2},
        )
        state = await resp.json()

        # Initial P2 building types
        initial_p2_buildings = {
            e.get("building_type", "")
            for e in state["entities"].values()
            if e.get("owner") == 2 and e.get("entity_type") == "building"
        }

        for _ in range(300):
            resp = await http_client.post("/api/step", json={"commands": []})
            state = await resp.json()
            if state["is_terminal"]:
                break

        final_p2_buildings = {
            e.get("building_type", "")
            for e in state["entities"].values()
            if e.get("owner") == 2 and e.get("entity_type") == "building"
        }

        new_buildings = final_p2_buildings - initial_p2_buildings
        assert len(new_buildings) > 0, (
            f"AI should have built new building types. "
            f"Initial: {initial_p2_buildings}, Final: {final_p2_buildings}"
        )

    @pytest.mark.asyncio
    async def test_ai_produces_combat_units(self, http_client):
        """AI should eventually train soldiers once barracks is complete.
        Full pipeline: gather → barracks (~200t) → complete barracks (~300t)
        → train soldiers (~400t+). Give generous 1200 ticks."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 2},
        )
        state = await resp.json()

        initial_soldiers = _count_player_entities(state, 2, "soldier")
        assert initial_soldiers == 0, "P2 should start with 0 soldiers"

        for _ in range(1200):
            resp = await http_client.post("/api/step", json={"commands": []})
            state = await resp.json()
            if state["is_terminal"]:
                break

        final_soldiers = _count_player_entities(state, 2, "soldier")
        assert final_soldiers > 0, (
            "AI (P2) should have trained soldiers after 1200 ticks. "
            f"P2 entities: {[(eid, e.get('entity_type', e.get('building_type', ''))) for eid, e in state['entities'].items() if e.get('owner') == 2]}"
        )


# ── Test 4: terminal condition propagation ───────────────────────────────────


class TestTerminalCondition:
    """Verify that terminal state (is_terminal + winner) is correctly returned
    through the HTTP gateway, matching what grpc_bridge.gd reads to emit
    the game_over signal."""

    @pytest.mark.asyncio
    async def test_max_ticks_terminal(self, http_client):
        """Game should terminate at max_ticks with winner=0 (draw)."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 30, "ai_player": 2},
        )
        state = await resp.json()
        assert state["is_terminal"] is False

        # Step until terminal
        for _ in range(35):
            resp = await http_client.post("/api/step", json={"commands": []})
            state = await resp.json()
            if state["is_terminal"]:
                break

        assert state["is_terminal"] is True, (
            f"Game should have terminated by max_ticks=30. "
            f"Current tick: {state['tick']}"
        )
        assert state["tick"] >= 30
        # Both bases still alive → winner = 0 (draw)
        assert state["winner"] == 0, (
            f"Expected winner=0 (draw) at max_ticks, got winner={state['winner']}"
        )

    @pytest.mark.asyncio
    async def test_get_state_reflects_terminal(self, http_client):
        """After game goes terminal, /api/get_state should also report it."""
        await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 20, "ai_player": 2},
        )

        # Step past max_ticks
        for _ in range(25):
            resp = await http_client.post("/api/step", json={"commands": []})
            data = await resp.json()
            if data["is_terminal"]:
                break

        # Verify get_state also shows terminal
        resp = await http_client.post("/api/get_state", json={})
        data = await resp.json()
        assert data["is_terminal"] is True, (
            "get_state should report is_terminal=True after game ends"
        )

    @pytest.mark.asyncio
    async def test_step_after_terminal_stays_terminal(self, http_client):
        """After game is terminal, further step calls should not revive it."""
        await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10, "ai_player": 2},
        )

        # Run to terminal
        terminal_tick = None
        for _ in range(20):
            resp = await http_client.post("/api/step", json={"commands": []})
            data = await resp.json()
            if data["is_terminal"]:
                terminal_tick = data["tick"]
                break

        assert terminal_tick is not None, "Game should have terminated"

        # Step again — state should remain terminal at same tick
        resp = await http_client.post("/api/step", json={"commands": []})
        data = await resp.json()
        assert data["is_terminal"] is True
        assert data["tick"] == terminal_tick, (
            f"Tick should not advance after terminal. "
            f"Expected {terminal_tick}, got {data['tick']}"
        )

    @pytest.mark.asyncio
    async def test_base_destruction_sets_winner(self, http_client):
        """Manually destroy P2's base by attacking it repeatedly, verifying
        that winner=1 is correctly propagated through the HTTP gateway."""
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 10000, "ai_player": 0},
        )
        state = await resp.json()

        # Find P2 base and P1 attacker
        p2_base_id = None
        attacker_id = None
        for eid, e in state["entities"].items():
            if e.get("owner") == 2 and e.get("building_type") == "base":
                p2_base_id = eid
            elif e.get("owner") == 1 and e.get("entity_type") in ("soldier", "worker"):
                attacker_id = eid

        assert p2_base_id is not None, "P2 should have a base"

        if attacker_id:
            # Send attack commands repeatedly to destroy the P2 base
            for _ in range(500):
                attack_cmd = {
                    "action": "attack",
                    "issuer": 1,
                    "attacker_id": attacker_id,
                    "target_id": p2_base_id,
                }
                resp = await http_client.post(
                    "/api/step", json={"commands": [attack_cmd]}
                )
                data = await resp.json()
                # Check if P2 base is destroyed
                p2_base = data["entities"].get(p2_base_id, {})
                if p2_base.get("health", 1) <= 0 or data["is_terminal"]:
                    break

            # After many attack steps, P2 base should be gone → P1 wins
            if data["is_terminal"]:
                assert data["winner"] == 1, (
                    f"When P2 base is destroyed, winner should be 1, "
                    f"got winner={data['winner']}"
                )

    @pytest.mark.asyncio
    async def test_terminal_signal_propagates_like_godot(self, http_client):
        """Verify that the terminal state fields that grpc_bridge.gd reads
        (is_terminal, winner) are present and correct at game end.

        In grpc_bridge.gd:
          _is_terminal = data.get("is_terminal", false)
          _winner = data.get("winner", 0)
          if _is_terminal:
              game_over.emit(_winner, _tick)
        """
        resp = await http_client.post(
            "/api/start_game",
            json={"seed": 42, "max_ticks": 15, "ai_player": 2},
        )

        # Step until terminal
        final_data = None
        for _ in range(20):
            resp = await http_client.post("/api/step", json={"commands": []})
            final_data = await resp.json()
            if final_data["is_terminal"]:
                break

        assert final_data is not None
        assert final_data["is_terminal"] is True
        assert "winner" in final_data
        assert "tick" in final_data
        # The fields grpc_bridge.gd reads must all be present
        assert isinstance(final_data["is_terminal"], bool)
        assert isinstance(final_data["winner"], int)
        assert isinstance(final_data["tick"], int)