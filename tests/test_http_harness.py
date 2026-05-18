"""HTTP integration tests for the 4 new harness endpoints.

Endpoints under test:
  1. GET  /api/replay/{match_id}       — replay data from JSONL file
  2. GET  /api/league/ranking          — ELO leaderboard
  3. POST /api/league/match            — create & run a League match
  4. POST /api/league/submit_result    — submit result → update ELO

Uses aiohttp TestClient/TestServer with a mock SimCoreClient so that
no real gRPC server is needed.  The harness.league and harness.pool
modules are imported directly (pure Python, no external AI deps).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from simcore.http_gateway import app_factory, reset_ai_state

# ── Serialisation group (module-level globals) ──────────────────────────────
pytestmark = pytest.mark.xdist_group(name="http_integration")


# ── Helpers ──────────────────────────────────────────────────────────────────


class _MockClient:
    """Minimal mock of SimCoreClient — just enough for app_factory() to accept it.

    All handler methods that actually call _client are patched individually
    in the tests that need it (e.g. replay fallback).
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset():
    """Reset gateway globals before every test."""
    reset_ai_state()
    yield
    reset_ai_state()


@pytest.fixture()
async def http_client(tmp_path):
    """Build a TestClient with a mock _client injected.

    Also overrides the replay directory to a tmp_path so tests can
    create/destroy JSONL files without polluting the project tree.
    """
    mock_client = _MockClient()
    app = await app_factory(client=mock_client)  # type: ignore[arg-type]

    # Point _replay_dir at the temp directory
    import simcore.http_gateway as gw

    gw._replay_dir = tmp_path  # type: ignore[attr-defined]

    async with TestClient(TestServer(app)) as c:
        yield c


# ── 1. GET /api/replay/{match_id} ───────────────────────────────────────────


class TestReplayEndpoint:
    """Tests for GET /api/replay/{match_id}."""

    @pytest.mark.asyncio
    async def test_replay_not_found(self, http_client):
        """Non-existent match_id → 200 with empty ticks (graceful fallback).

        The endpoint returns 200 with an empty tick list rather than 404
        because it falls back to the gRPC client when the file is missing.
        With our mock (no gRPC data), ticks is [].
        """
        resp = await http_client.get("/api/replay/nonexistent_match_999")
        assert resp.status == 200
        data = await resp.json()
        assert data["match_id"] == "nonexistent_match_999"
        assert data["ticks"] == []
        assert data["tick_count"] == 0

    @pytest.mark.asyncio
    async def test_replay_from_file(self, http_client, tmp_path):
        """Create a temporary JSONL replay file and verify the endpoint reads it."""
        match_id = "test_match_001"
        replay_file = tmp_path / f"{match_id}.jsonl"

        # Write 3 tick lines
        ticks_data = [
            {"tick": 0, "entities": {"e1": {"owner": 1}}},
            {"tick": 1, "entities": {"e1": {"owner": 1}, "e2": {"owner": 2}}},
            {"tick": 2, "entities": {"e1": {"owner": 1}, "e2": {"owner": 2}, "e3": {"owner": 1}}},
        ]
        with open(replay_file, "w") as f:
            for tick in ticks_data:
                f.write(json.dumps(tick) + "\n")

        resp = await http_client.get(f"/api/replay/{match_id}")
        assert resp.status == 200
        data = await resp.json()
        assert data["match_id"] == match_id
        assert data["tick_count"] == 3
        assert len(data["ticks"]) == 3
        assert data["ticks"][0]["tick"] == 0
        assert data["ticks"][2]["tick"] == 2
        # Verify entity data survived the JSON round-trip
        assert "e3" in data["ticks"][2]["entities"]


# ── 2. GET /api/league/ranking ──────────────────────────────────────────────


class TestLeagueRanking:
    """Tests for GET /api/league/ranking."""

    @pytest.mark.asyncio
    async def test_league_ranking_empty(self, http_client):
        """No versions registered → empty versions list."""
        resp = await http_client.get("/api/league/ranking")
        assert resp.status == 200
        data = await resp.json()
        assert data["versions"] == []


# ── 3. POST /api/league/submit_result ──────────────────────────────────────


class TestLeagueSubmitResult:
    """Tests for POST /api/league/submit_result."""

    @pytest.mark.asyncio
    async def test_league_submit_result(self, http_client):
        """Submit a match result and verify ELO is updated."""
        payload = {
            "p1_version": "script-v1",
            "p2_version": "script-v2",
            "winner": 1,
            "ticks": 500,
        }
        resp = await http_client.post("/api/league/submit_result", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True

        # P1 won → ELO should go up from the starting 1000
        assert data["p1_elo"] > 1000.0
        # P2 lost → ELO should go down
        assert data["p2_elo"] < 1000.0

    @pytest.mark.asyncio
    async def test_league_ranking_after_submit(self, http_client):
        """After submitting a result, the ranking endpoint includes the versions."""
        # Submit a result first
        payload = {
            "p1_version": "alpha-v1",
            "p2_version": "beta-v1",
            "winner": 1,
            "ticks": 300,
        }
        await http_client.post("/api/league/submit_result", json=payload)

        # Now fetch ranking
        resp = await http_client.get("/api/league/ranking")
        assert resp.status == 200
        data = await resp.json()
        names = {v["name"] for v in data["versions"]}
        assert "alpha-v1" in names
        assert "beta-v1" in names

        # alpha-v1 won → higher ELO → appears first
        assert data["versions"][0]["name"] == "alpha-v1"
        assert data["versions"][0]["elo"] > data["versions"][1]["elo"]


# ── 4. POST /api/league/match ──────────────────────────────────────────────


class TestLeagueMatch:
    """Tests for POST /api/league/match.

    SimulationPool.run_match() depends on SimCore (real engine), so we
    mock the pool to avoid needing a running gRPC server.  We verify that
    the route exists and the handler invokes the pool correctly.
    """

    @pytest.mark.asyncio
    async def test_league_match_endpoint(self, http_client, tmp_path):
        """POST /api/league/match reaches the handler and the route is wired.

        We mock SimulationPool so no real SimCore is needed, and verify
        the response shape.
        """
        fake_match_id = "fake-mid-123"
        fake_result = MagicMock()
        fake_result.match_id = fake_match_id
        fake_result.winner = 1
        fake_result.ticks = 42
        fake_result.tps = 500.0
        fake_result.replay = [{"tick": 0, "entities": {}}]

        with patch("simcore.http_gateway.SimulationPool") as MockPool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.run_match = AsyncMock(return_value=fake_result)
            MockPool.return_value = mock_pool_instance

            payload = {
                "p1_version": "script-v1",
                "p2_version": "script-v2",
                "map_seed": 7,
                "max_ticks": 100,
            }
            resp = await http_client.post("/api/league/match", json=payload)
            assert resp.status == 200
            data = await resp.json()
            assert data["match_id"] == fake_match_id
            assert data["winner"] == 1
            assert data["ticks"] == 42
            assert data["tps"] == 500.0

            # Verify SimulationPool was instantiated and run_match called
            MockPool.assert_called_once()
            mock_pool_instance.run_match.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_league_match_route_exists(self, http_client):
        """The route /api/league/match is registered in the app router."""
        # Simple check: OPTIONS or a minimal POST should not 404.
        # We mock to avoid the real SimulationPool.
        with patch("simcore.http_gateway.SimulationPool") as MockPool, \
             patch("simcore.http_gateway.MatchConfig"):
            mock_pool_instance = MagicMock()
            mock_pool_instance.run_match = AsyncMock(
                return_value=MagicMock(
                    match_id="x", winner=0, ticks=0, tps=0.0, replay=[]
                )
            )
            MockPool.return_value = mock_pool_instance

            resp = await http_client.post(
                "/api/league/match",
                json={"p1_version": "a", "p2_version": "b"},
            )
            # Should NOTbe 404 — route exists
            assert resp.status != 404