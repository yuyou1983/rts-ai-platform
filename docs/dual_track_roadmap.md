# RTS-AI Platform — 双轨路线图

> **核心决策**: 项目拆分为两条独立演进轨道，共享 SimCore 引擎层，各自迭代不互相阻塞。

---

## 架构总览

```
                    ┌─────────────────────┐
                    │   SimCore 引擎 (L1)  │  ← 共享层：状态机、战斗、建造、迷雾
                    │   7,700 LOC         │
                    └──────┬───────┬───────┘
                           │       │
              ┌────────────▼───┐ ┌─▼────────────┐
              │  Track A       │ │  Track B      │
              │  平台可视化    │ │  SC1 复刻     │
              │  (Agent Ops)   │ │  (Game Dev)   │
              └────────────────┘ └───────────────┘
```

---

## Track A: 平台可视化 — Agent Ops Dashboard

### 定位
给 AI 研究者 / 开发者用的白屏工具，**看得见 Agent 在干什么**，用于训练调优和实验管理。

### 目标用户
- RL 研究员调参
- Agent 开发者 debug 决策
- 训练集群管理员

### 功能规划

#### Phase A1: 核心仪表盘 (4 周)

| # | 功能 | 优先级 | 验收标准 |
|---|------|--------|----------|
| A1.1 | 对局列表页 | P0 | 列出所有对局，按时间/结果排序，可筛选 |
| A1.2 | 实时观战 | P0 | WebSocket 推送 tick 数据，前端渲染 |
| A1.3 | Agent 命令流 | P0 | 时间线展示每个 Agent 发出的命令序列 |
| A1.4 | KDA / 资源曲线 | P0 | 实时折线图（mineral/gas/supply/kills） |
| A1.5 | 胜率统计 | P1 | 按Agent版本/种族/难度分组统计 |
| A1.6 | 对局回放 | P1 | 从 replay JSON 重放，可暂停/快进/逐帧 |

#### Phase A2: 训练管理 (6 周)

| # | 功能 | 优先级 | 验收标准 |
|---|------|--------|----------|
| A2.1 | 训练任务提交 | P0 | Web 表单提交 GRPO 训练配置 |
| A2.2 | 训练状态监控 | P0 | 实时显示 episode/reward/loss |
| A2.3 | League 版本池 | P1 | 展示所有 Agent 版本 + ELO 排名 |
| A2.4 | Promotion Gate 可视化 | P1 | 新旧版本对战胜率对比图 |
| A2.5 | Rollout Worker 监控 | P1 | 并发路数/吞吐/失败率 |
| A2.6 | 训练曲线对比 | P2 | 多个 run 的 reward 曲线叠加对比 |

#### Phase A3: Agent Debug 深度工具 (4 周)

| # | 功能 | 优先级 | 验收标准 |
|---|------|--------|----------|
| A3.1 | 决策热力图 | P1 | 地图上标注 Agent 关注区域 |
| A3.2 | 命令归因 | P2 | 每条命令关联到哪个子 Agent + 推理链 |
| A3.3 | 状态快照 Diff | P2 | 两个 tick 之间的实体变化 diff 视图 |
| A3.4 | A/B 对战 | P1 | 两版本 Agent 同配置对战，一键启动 |

### 技术栈

```
前端: React + TypeScript + Recharts/D3 + WebSocket
后端: FastAPI + SQLite/Postgres + Redis (队列)
部署: Docker Compose (单机) / K8s (集群)
```

### 目录结构

```
platform/
├── dashboard/            # React 前端
│   ├── src/
│   │   ├── pages/        # MatchesPage, MatchDetailPage, TrainPage, LeaguePage
│   │   ├── components/   # CommandTimeline, ResourceChart, HeatMap, ReplayPlayer
│   │   ├── stores/       # matchStore, trainStore, leagueStore
│   │   └── api/          # ws.ts, rest.ts
│   └── package.json
├── server/               # Python 后端
│   ├── api/              # matches, training, league, replay
│   ├── models/           # Match, Agent, TrainRun, LeagueEntry
│   ├── services/         # replay_parser, stat_aggregator, train_scheduler
│   └── main.py           # FastAPI app
├── workers/              # Rollout Worker, Train Worker
└── docker-compose.yml
```

### 依赖 SimCore 的接口

```python
# SimCore 只需暴露这些 — Track A 不改 SimCore 代码
from simcore.engine import SimCore
from simcore.state import GameState

engine = SimCore()
engine.initialize(config=game_config)
state = engine.step(commands)       # → dict (entities, resources, fog, tick, is_terminal)
gs = GameState(**state)
obs = gs.get_observations()         # → [{tick, entities, resources, fog}, ...]
```

---

## Track B: SC1 复刻 — 游戏可玩性

### 定位
让玩家能真的"打一局星际"，**手感对、内容全、能玩爽**。

### 目标用户
- RTS 玩家
- SC1 怀旧党
- AI 观战者（看 Agent 打得像不像人）

### 功能规划

#### Phase B1: 三族可玩闭环 (6 周) ← 当前优先

| # | 功能 | 优先级 | 状态 | 验收标准 |
|---|------|--------|------|----------|
| B1.1 | 三族建筑完整映射 | P0 | 🟡 60% | T/Z/P 所有建筑在 manifest 中有 atlas + HUD 按钮 |
| B1.2 | 三族单位完整映射 | P0 | 🟡 55% | T/Z/P 所有单位有精灵 + 属性 + 训练入口 |
| B1.3 | 资源节点完整映射 | P0 | 🟡 50% | 矿脉/气泉/Vespene 精灵 + 交互 |
| B1.4 | HUD 种族感知 | P0 | ✅ 90% | BUILD_CATALOG/TRAIN_CATALOG 按 race 过滤 |
| B1.5 | Pylon 供电机制 | P0 | 🟡 70% | 供电圈可视化 + 建筑离线效果 |
| B1.6 | 供给人口显示 | P0 | ✅ | HUD 显示 X/Y supply |
| B1.7 | AI 对手可建造 | P0 | ✅ 刚修 | AI 通过 gateway 正常训练/建造 |
| B1.8 | 按T训练种族感知 | P0 | ✅ 刚修 | P→Zealot, Z→Zergling, T→Marine |

#### Phase B2: 战斗手感 (6 周)

| # | 功能 | 优先级 | 验收标准 |
|---|------|--------|----------|
| B2.1 | 攻击动画 + 弹道 | P0 | 单位攻击有视觉反馈 |
| B2.2 | 死亡动画 + 遗体 | P0 | 单位死亡有爆炸/倒地效果 |
| B2.3 | 采集动画 | P1 | Worker 采矿/运矿有视觉反馈 |
| B2.4 | 建造动画 | P1 | 建筑建造时有进度条 + 施工效果 |
| B2.5 | 选择环 + 悬停高亮 | P0 | 点选/框选有清晰视觉反馈 |
| B2.6 | 血条对齐 | P0 | 血条在头顶，不遮挡操作 |
| B2.7 | 小地图实体点对齐 | P1 | 小地图上单位/建筑颜色+大小正确 |

#### Phase B3: SC1 核心机制 (8 周)

| # | 功能 | 优先级 | 验收标准 |
|---|------|--------|----------|
| B3.1 | 高地优势 | P0 | 低地打高地 70% 命中率 |
| B3.2 | 迷雾等级渲染 | P0 | unexplored/explored/visible 三级效果 |
| B3.3 | Creep 蔓延 | P1 | Zerg 建筑周围 creep 纹理扩展 |
| B3.4 | 护盾回复 | P0 | Protoss 护盾脱战自动回 |
| B3.5 | Templar Psi Storm | P1 | AOE 技能 + 视觉效果 |
| B3.6 | Dark Templar 隐身 | P1 | 永久隐身 + Observer 反隐 |
| B3.7 | Siege Tank 架炮 | P2 | 攻击模式切换 + 射程变化 |
| B3.8 | Carrier 拦截机 | P2 | 航母放飞 Interceptor |
| B3.9 | Arbitar Recall | P2 | 传送技能 |
| B3.10 | Comsat Scan | P1 | 扫描反隐 |

#### Phase B4: 完整对局体验 (4 周)

| # | 功能 | 优先级 | 验收标准 |
|---|------|--------|----------|
| B4.1 | 1v1 匹配流程 | P0 | 主菜单 → 选族 → 匹配 → 游戏中 → 结算 |
| B4.2 | 结算画面 | P0 | 显示 APM / KDA / 资源曲线 / 建造时间线 |
| B4.3 | APM 计数器 | P1 | 实时显示，结算展示统计 |
| B4.4 | 保存/加载回放 | P1 | replay JSON 文件可导出导入 |
| B4.5 | 热键自定义 | P2 | 设置面板可改键位 |
| B4.6 | 难度选择 | P1 | Easy/Medium/Hard AI 行为差异 |

### Godot 目录结构 (Track B 专属)

```
godot/
├── assets/
│   ├── sprites/
│   │   ├── buildings/
│   │   │   ├── TerranBuilding.png    # atlas: 6 列
│   │   │   ├── ZergBuilding.png     # atlas: 9 列
│   │   │   └── ProtossBuilding.png   # atlas: 4 列
│   │   ├── units/
│   │   │   ├── TerranUnit.png
│   │   │   ├── ZergUnit.png
│   │   │   └── ProtossUnit.png
│   │   └── effects/
│   │       ├── explosions.png
│   │       ├── projectiles.png
│   │       └── spells.png
│   └── audio/
│       ├── bgm/
│       └── sfx/
├── resources/
│   ├── presentation_manifest.json   # 视觉映射 (共享)
│   ├── unit_data.json               # 单位属性
│   ├── building_data.json           # 建筑属性
│   └── tech_tree.json               # 科技树数据
├── scenes/
│   ├── main_menu.tscn
│   ├── game_view.tscn
│   └── victory_screen.tscn
├── scripts/
│   ├── game_view.gd                 # 主渲染循环
│   ├── hud.gd                       # HUD (种族感知)
│   ├── grpc_bridge.gd               # HTTP/gRPC 通信
│   ├── sprite_loader.gd             # manifest atlas 加载
│   ├── vfx_manager.gd               # 特效管理
│   ├── fog_renderer.gd              # 迷雾
│   ├── camera_controller.gd         # 摄像机
│   ├── selection_manager.gd         # 选择
│   └── ...
└── project.godot
```

---

## 双轨协作关系

```
    Track A (平台)                    Track B (游戏)
    ─────────────                    ──────────────
    观战页面 ←── ws://localhost:8080 ──→ 游戏实时 tick
    回放页面 ←── replay JSON ──────────→ 录制器导出
    统计面板 ←── 对局结果 ──────────────→ 结算画面
    训练任务 ──→ engine.initialize() ←── 共享 SimCore
    League   ──→ engine.step()       ←── 共享 SimCore
    
    ⚠️ 不共享:
    - 前端代码 (React vs Godot)
    - 构建系统 (npm vs Godot editor)
    - 发布节奏 (A 可独立发版, B 可独立发版)
```

### SimCore 接口契约

Track A 和 Track B 通过 SimCore 的以下接口协作，**互不侵入**：

```python
# 1. 初始化
engine.initialize(map_seed, config) → GameState

# 2. 步进
engine.step(commands: list[dict]) → GameState

# 3. 观测
GameState.get_observations() → list[PlayerObs]

# 4. 回放
engine.initialize_from_snapshot(snapshot) → GameState
```

---

## 执行优先级建议

```
Week 1-2:  B1 闭环 — 三族可玩（当前阻塞项已修，补齐缺失映射）
Week 3-4:  B2 战斗手感 — 攻击/死亡/选择反馈
Week 5-6:  A1 仪表盘 — 基础观战+命令流+资源曲线
Week 7-8:  B3 核心机制 — 高地/护盾/Psi Storm
Week 9-10: A2 训练管理 — 任务提交+监控+League
Week 11-12:B4 完整体验 — 匹配流程+结算+回放
Week 13-14:A3 Debug工具 — 热力图+归因+Diff
```

> **原则**: TrackB 先跑通可玩闭环，Track A 并行建设。不要让可视化阻塞游戏开发，也不要让游戏开发阻塞可视化。

---

*RTS-AI Platform v0.5 · Dual-Track Roadmap · 2026-06*
