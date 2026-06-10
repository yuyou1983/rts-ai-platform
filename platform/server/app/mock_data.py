"""Mock data for Track A platform API."""

MOCK_MATCHES = [
    {
        "id": "1",
        "players": ["Agent-Alpha", "Agent-Beta"],
        "status": "completed",
        "winner": 1,
        "ticks": 1200,
    },
    {
        "id": "2",
        "players": ["Agent-Gamma", "Agent-Delta"],
        "status": "running",
        "winner": 0,
        "ticks": 450,
    },
    {
        "id": "3",
        "players": ["Agent-Epsilon", "Agent-Zeta"],
        "status": "completed",
        "winner": 2,
        "ticks": 890,
    },
]

MOCK_TICK = {
    "tick": 0,
    "entities": {
        "units": [
            {"id": "u1", "owner": 1, "type": "worker", "x": 10, "y": 20, "hp": 100},
            {"id": "u2", "owner": 2, "type": "worker", "x": 90, "y": 80, "hp": 100},
        ],
        "buildings": [
            {"id": "b1", "owner": 1, "type": "command_center", "x": 5, "y": 5, "hp": 500},
            {"id": "b2", "owner": 2, "type": "command_center", "x": 95, "y": 95, "hp": 500},
        ],
    },
    "resources": {
        "1": {"gold": 500, "wood": 300},
        "2": {"gold": 480, "wood": 310},
    },
    "is_terminal": False,
    "winner": 0,
}
