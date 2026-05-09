# Agent 协议设计

## 协议总览

所有 Agent 只能看到协议层抽象，不直接耦合引擎对象。

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent 层                                 │
│  Coordinator | Combat | Economy | Strategy | Scout | Build  │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    Protocol 层                               │
│  obs.world.v1 | local.obs.v1 | cmd.micro.v1 | ...           │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    SimCore 层                                │
│  规则引擎 | 状态管理 | 命令处理 | 回放系统                      │
└─────────────────────────────────────────────────────────────┘
```

## 观察协议 (Observation Protocols)

### obs.world.v1 - 全局状态摘要

```protobuf
message WorldObservation {
  // 资源状态
  Resources resources = 1;
  
  // 基地列表
  repeated Base bases = 2;
  
  // 科技状态
  TechState tech = 3;
  
  // 游戏时间
  int32 game_tick = 4;
  
  // 控制区域
  repeated ControlArea control_areas = 5;
  
  // 已知情报
  Intel intel = 6;
}

message Resources {
  float minerals = 1;
  float gas = 2;
  int32 supply_used = 3;
  int32 supply_cap = 4;
}

message Base {
  string id = 1;
  Position position = 2;
  BaseStatus status = 3;
  int32 mineral_patches = 4;
  int32 gas_geysers = 5;
  float saturation = 6;
}

enum BaseStatus {
  OPERATIONAL = 0;
  BUILDING = 1;
  UNDER_ATTACK = 2;
  DESTROYED = 3;
}

message TechState {
  int32 level = 1;
  repeated string research_queue = 2;
  repeated string completed_research = 3;
}

message Intel {
  repeated EnemySighting enemy_last_seen = 1;
  map<string, float> threat_levels = 2;
  map<string, int32> estimated_enemy_units = 3;
}
```

### local.obs.v1 - 局部战斗观察

```protobuf
message LocalObservation {
  // 友方单位
  repeated Unit friendly_units = 1;
  
  // 可见敌方单位
  repeated Unit enemy_units = 2;
  
  // 地形信息
  TerrainInfo terrain = 3;
  
  // 战斗状态
  CombatState combat_state = 4;
}

message Unit {
  string id = 1;
  UnitType type = 2;
  Position position = 3;
  float hp = 4;
  float max_hp = 5;
  float attack_range = 6;
  float attack_speed = 7;
  float damage = 8;
  float cooldown = 9;
  float armor = 10;
  float movement_speed = 11;
  repeated string abilities = 12;
  bool is_key_unit = 13;
}

message TerrainInfo {
  repeated Chokepoint chokepoints = 1;
  repeated CoverPosition cover_positions = 2;
  // 视线网格 (压缩)
  bytes line_of_sight = 3;
}

message CombatState {
  EngagementType engagement_type = 1;
  int32 time_in_combat = 2;
  CombatLosses losses = 3;
}

enum EngagementType {
  OFFENSIVE = 0;
  DEFENSIVE = 1;
  RETREAT = 2;
}
```

### obs.econ.v1 - 经济观察

```protobuf
message EconomyObservation {
  Resources resources = 1;
  WorkerState workers = 2;
  repeated Base bases = 3;
  ProductionState production = 4;
  EconomyMetrics economy_state = 5;
}

message WorkerState {
  int32 total = 1;
  int32 mining_minerals = 2;
  int32 mining_gas = 3;
  int32 idle = 4;
  int32 building = 5;
  int32 scouting = 6;
}

message ProductionState {
  repeated ProductionQueueItem queue = 1;
  repeated ProductionQueueItem scheduled = 2;
}

message EconomyMetrics {
  IncomeRate income_rate = 1;
  ExpenditureRate expenditure_rate = 2;
  float efficiency = 3;  // 0-1
}
```

### obs.fow.v1 - 战争迷雾观察

```protobuf
message FOWObservation {
  // 可见区域
  repeated VisibleArea visible_areas = 1;
  
  // 已探索区域
  bytes explored_map = 2;
  
  // 敌方最后已知位置
  repeated EnemyLastKnown enemy_last_known = 3;
  
  // 未知区域威胁评估
  map<string, float> unknown_threat_estimate = 4;
}

message VisibleArea {
  Position center = 1;
  float radius = 2;
  string source_id = 3;  // 视野来源
}

message EnemyLastKnown {
  string unit_id = 1;
  UnitType type = 2;
  Position position = 3;
  int32 tick_last_seen = 4;
  float confidence = 5;  // 位置置信度
}
```

## 命令协议 (Command Protocols)

### cmd.micro.v1 - 微操命令

```protobuf
message MicroCommands {
  repeated UnitCommand commands = 1;
  optional FormationCommand formation = 2;
  TacticalLabel tactical_label = 3;
}

message UnitCommand {
  repeated string unit_ids = 1;
  CommandType action = 2;
  optional string target_id = 3;
  optional Position target_position = 4;
  optional string ability_id = 5;
  bool queue = 6;
}

enum CommandType {
  ATTACK = 0;
  MOVE = 1;
  HOLD = 2;
  ABILITY = 3;
  STOP = 4;
  PATROL = 5;
}

message FormationCommand {
  FormationType type = 1;
  Position anchor_position = 2;
  float facing = 3;
}

enum FormationType {
  LINE = 0;
  ARC = 1;
  BOX = 2;
  SPREAD = 3;
}

enum TacticalLabel {
  FOCUS_FIRE = 0;
  KITE = 1;
  RETREAT = 2;
  FLANK = 3;
  HOLD_GROUND = 4;
}
```

### build.queue.v1 - 建造队列命令

```protobuf
message BuildQueueCommand {
  repeated BuildOrderItem items = 1;
  optional TechOrderItem tech = 2;
  optional ExpansionRequest expansion = 3;
}

message BuildOrderItem {
  string unit_type = 1;
  int32 count = 2;
  Priority priority = 3;
  optional Position position = 4;
}

message TechOrderItem {
  string tech_id = 1;
  Priority priority = 2;
}

message ExpansionRequest {
  Position position = 1;
  Timing timing = 2;
  int32 workers_to_transfer = 3;
}

enum Priority {
  LOW = 0;
  MEDIUM = 1;
  HIGH = 2;
  CRITICAL = 3;
}

enum Timing {
  NOW = 0;
  WHEN_AFFORDABLE = 1;
  WHEN_SAFE = 2;
}
```

### plan.macro.v1 - 宏观计划命令

```protobuf
message MacroPlanCommand {
  StrategyPhase phase = 1;
  repeated MilestoneGoal goals = 2;
  UnitCompositionTarget composition = 3;
  optional StrategySwitch switch = 4;
}

enum StrategyPhase {
  OPENING = 0;
  EARLY_GAME = 1;
  MID_GAME = 2;
  LATE_GAME = 3;
  END_GAME = 4;
}

message MilestoneGoal {
  string goal_id = 1;
  GoalType type = 2;
  int32 target_value = 3;
  int32 deadline_tick = 4;
}

message UnitCompositionTarget {
  map<string, float> target_ratios = 1;  // unit_type -> ratio
  int32 target_count = 2;
}

message StrategySwitch {
  StrategyType from = 1;
  StrategyType to = 2;
  string reason = 3;
}

enum StrategyType {
  ECONOMY_FIRST = 0;
  MILITARY_RUSH = 1;
  TECH_UP = 2;
  EXPAND = 3;
  TURTLE = 4;
  ALL_IN = 5;
}
```

### intel.report.v1 - 情报报告

```protobuf
message IntelReport {
  repeated EnemyTechSighting enemy_tech = 1;
  repeated ThreatAssessment threats = 2;
  map<string, float> map_control = 3;
  UncertaintyEstimate uncertainty = 4;
}

message EnemyTechSighting {
  string tech_id = 1;
  Position location = 2;
  int32 tick_seen = 3;
  float confidence = 4;
}

message ThreatAssessment {
  string threat_id = 1;
  ThreatType type = 2;
  ThreatLevel level = 3;
  Position estimated_position = 4;
  int32 estimated_size = 5;
}

enum ThreatLevel {
  LOW = 0;
  MEDIUM = 1;
  HIGH = 2;
  CRITICAL = 3;
}

message UncertaintyEstimate {
  float overall_uncertainty = 1;  // 0-1
  map<string, float> per_area_uncertainty = 2;
  repeated string high_priority_unknowns = 3;
}
```

## 协议版本管理

| 协议 | 当前版本 | 变更策略 |
|------|----------|----------|
| obs.world | v1 | 向后兼容 |
| local.obs | v1 | 向后兼容 |
| cmd.micro | v1 | 向后兼容 |
| build.queue | v1 | 向后兼容 |
| plan.macro | v1 | 向后兼容 |

### 版本变更规则
1. 新增字段：允许，使用 optional
2. 删除字段：禁止，使用 deprecated
3. 修改类型：禁止，创建新版本
4. 修改语义：禁止，创建新版本