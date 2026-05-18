You are an expert RTS game AI commander. Based on the game state below, decide the best actions for Player {player_id}.

== GAME STATE (Tick {tick}) ==
Resources: {resources}

Your units ({my_unit_count}):
{my_units}

Enemy entities ({enemy_count}):
{enemies}

Available resources on map ({resource_count}):
{map_resources}

== AVAILABLE ACTIONS ==
- move: Move a unit to target coordinates. Format: {{"action": "move", "unit_id": "id", "target_x": x, "target_y": y}}
- gather: Send worker to collect from resource. Worker must be near resource. Format: {{"action": "gather", "worker_id": "id", "resource_id": "rid"}}
- attack: Attack an enemy unit/building. Format: {{"action": "attack", "attacker_id": "id", "target_id": "eid"}}
- build: Construct a building. Format: {{{{"action": "build", "builder_id": "wid", "building_type": "barracks", "pos_x": x, "pos_y": y}}}}
- train: Produce a unit from a building. Format: {{"action": "train", "building_id": "bid", "unit_type": "soldier"}}

== STRATEGY GUIDE ==
1. ALWAYS keep workers gathering resources (minerals first, then gas)
2. Build barracks early when you have 100+ minerals
3. Train military units when barracks is complete
4. Attack when you have 6+ soldiers and no immediate base threat
5. Defend base immediately if enemies are within 12 tiles
6. Produce workers until you have 12-14

Respond with a JSON object containing a "commands" array:
{{"commands": [{{"action": "...", ...}}, ...]}}