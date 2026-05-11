# M3 里程碑：战斗原型 — 实体在地图上活起来

**目标**: 让单位在 Godot 地图上可视可交互，完成 单兵→战斗→编队 的自底向上验证闭环

**状态**: ✅ **M3 已完成** (2026-05-11)

---

## 完成总结

### 关键指标

| 指标 | M3 目标 | 实际达成 |
|------|---------|---------|
| 测试覆盖 | ≥80 | 129 tests |
| 对战闭环 | ScriptAI 跑完一局 | ✅ 10/10 正常终止 |
| Coordinator 胜率 | ≥50% vs ScriptAI | 60% (50局统计) |
| 确定性重放 | 同seed同结果 | ✅ 463帧0差异 |
| TPS | ≥20 | 541-696 |
| 0崩溃 | 50局0崩溃 | ✅ |
| 命令类型 | move/attack/gather/build/train | ✅ 5种全端到端验证 |

### 修复的 Bug 清单

| # | Bug | 根因 | Sprint |
|---|-----|------|--------|
| 1 | 资源节点一 tick 全消失 | `health<=0` 清理默认 health=0 的资源 | S1 |
| 2 | Auto-attack 攻击中立实体 | `owner != my_owner` 包含 owner=0 | S1 |
| 3 | Gathering 不持续 | 工人采矿需每 tick 收 gather 命令 | S1 |
| 4 | gRPC 缺 resource_type/amount | server 端序列化遗漏 | S4 |
| 5 | gRPC client 缺同字段 | client 端反序列化遗漏 | S4 |
| 6 | Build 命令被 dedup 吞掉 | worker_id 共享 seen_units | S3 |
| 7 | 没 barracks 时不停 train worker | 矿攒不够 100 建兵营 | S4 |
| 8 | gRPC server 不序列化 fog | 遗漏 fog_p1/fog_p2 | S5 |
| 9 | gRPC client 不反序列化 fog | 遗漏 fog_of_war | S5 |
| 10 | proto 编译导入冲突 | `from proto import` 歧义 | S5 |

---

## Sprint 1: SimCore 行为闭环 ✅

**问题**：ScriptAI 跑 100 tick 实体不增不减（矿不回程、兵不出），闭环修不通后面全是空中楼阁

**修复**：
- Worker 满载后自动返回最近己方基地 deposit → carry=0 → idle
- attack 命令 validate + apply（移动进 range → 每tick扣血 → 死亡清理）
- Construction 按真实进度 `BUILD_PROGRESS_PER_TICK=10%` → 100%后 `is_constructing=False`
- Production 按 `PRODUCTION_TICKS` 倒计时 → 归零 spawn 新单位

**验收**：5 局 ScriptAI vs ScriptAI 全部正常终止（358-969 tick）

---

## Sprint 2: 战斗微操 ✅

**交付**：
- Target-following：有 `attack_target_id` 的单位每 tick 更新目标位置；目标死亡/消失时自动 clear → idle
- 战斗优先级评分：低血量×0.6 + 距离×0.3 - 威胁×0.1，优先打残血
- KillFeed KDA 统计类
- ScriptAI 战术升级：集中火力（所有士兵打最弱敌）、受伤工人撤退（health<30% → move to base）、侦察巡逻、集结后出击
- Move 命令清除 attack_target_id

**验收**：13 个新测试全过

---

## Sprint 3: 多 Agent 编排 ✅

**架构**：
```
Coordinator (全局仲裁)
├── EconomyAgent (工人/建造/资源)
├── CombatAgent (士兵/攻击)
└── ScoutAgent (侦察)
```

**实现**：
- `agents/sub_agents.py`：三核子 Agent，同步 `decide(obs)` 接口
- Coordinator：budget 分配（econ_frac=0.6 early, 0.4 mid），命令 dedup + merge
- `agents/economy.py`/`combat.py`：thin AgentBase wrapper 保持兼容
- MsgHub：sync/async 双模 context manager，auto_broadcast on reply

**关键修复**：dedup 用 `build_{id}` 前缀防止 build 和 gather 互相吞掉

**验收**：Coordinator vs ScriptAI 胜率 30%（10局），架构正确策略待调优

---

## Sprint 4: Godot 交互体验 ✅

**交付**：
- 完整命令系统：WASD移动 / 右键上下文（敌→attack，矿→gather，空地→move）/ B+右键→build / T键→train
- 不同单位形状渲染：worker=圆+工具线，soldier=菱形+剑线，building=方形，resource=金/绿块
- 血条（绿→黄→红）
- HUD：选择信息、操作提示、建造模式指示
- 小地图：实体点+摄像机视窗

**验收**：5种命令全部通过 HTTP gateway 端到端验证，资源节点不再消失

---

## Sprint 5: 战争迷雾 + 侦察 ✅

**交付**：
- Per-player 迷雾网格：0=unexplored, 1=explored, 2=visible
- 视野计算：每 tick 2→1 过期，按己方单位/建筑重新照亮。Scout 视野+1，建筑-1
- `get_observations` 按 fog 裁剪：己方始终可见，中立 explored+ 就可见，敌方仅 visible 可见
- Godot 迷雾渲染：unexplored=85%黑，explored=45%黑，visible=透明
- HUD 显示地图探索率百分比
- ScoutAgent 智能侦察：基于 fog 数据选未探索区域为巡逻路径，低血量撤退

**验收**：11 个迷雾专项测试全过，确定性重放验证通过

---

## Sprint 6: 整合 + 质量门禁 ✅

**交付**：
- 129 tests 全部通过，ruff clean
- 50 局 Coordinator vs ScriptAI：60%胜率，0 崩溃，0 平局
- 确定性重放：463 帧 0 差异
- 端到端压力测试：TPS 541-696
- M3 里程碑文档更新

---

## 原始 M3 拆解（归档）

### Sprint 1: SimCore 行为闭环修复
| # | 任务 | 状态 |
|---|------|------|
| 1.1 | Worker 满载后自动返回最近己方基地 | ✅ |
| 1.2 | 实现 attack 命令解析（validate + apply） | ✅ |
| 1.3 | Construction 建造进度 | ✅ |
| 1.4 | Production 生产队列进度 | ✅ |
| 1.5 | 端到端冒烟测试 | ✅ |

### Sprint 2: 战斗微操基础
| # | 任务 | 状态 |
|---|------|------|
| 2.1 | attack-move 命令 | ✅ |
| 2.2 | 显式 attack 命令执行 | ✅ |
| 2.3 | 撤退/stop 命令 | ✅ |
| 2.4 | CombatAgent 实体化 | ✅ |
| 2.5 | 战斗回放可视化 | ⏳ P2延后 |

### Sprint 3: 经济与多 Agent 编排
| # | 任务 | 状态 |
|---|------|------|
| 3.1 | EconomyAgent 实体化 | ✅ |
| 3.2 | MsgHub 真实广播 | ✅ |
| 3.3 | Worker 智能分配 | ✅ |
| 3.4 | 资源预算仲裁 | ✅ |
| 3.5 | 三核冒烟：胜率≥50% | ✅ 60% |

### Sprint 4: Godot 前端体验提升
| # | 任务 | 状态 |
|---|------|------|
| 4.1 | 血条渲染 | ✅ |
| 4.2 | 左键点选 + Shift 追加 | ✅ |
| 4.3 | 框选逻辑 | ✅ |
| 4.4 | 右键 move + A 键 attack-move | ✅ |
| 4.5 | 编队系统 | ⏳ P2延后 |
| 4.6 | 小地图点击跳转 | ⏳ P2延后 |
| 4.7 | 前端自动化验证 v2 | ✅ |

### Sprint 5: Fog-of-War + 侦察
| # | 任务 | 状态 |
|---|------|------|
| 5.1 | SimCore fog-of-war per-player | ✅ |
| 5.2 | get_observations 按 fog 过滤 | ✅ |
| 5.3 | Godot fog 渲染 | ✅ |
| 5.4 | Scout 视野+1、速度+1 | ✅ |
| 5.5 | ScoutAgent 侦察集成 | ✅ |

### Sprint 6: M3 整合 + 质量门禁
| # | 任务 | 状态 |
|---|------|------|
| 6.1 | 全链路整合测试 | ✅ |
| 6.2 | 性能基准 | ✅ |
| 6.3 | 回放系统 Godot 集成 | ⏳ P2延后 |
| 6.4 | CI 扩展 | ⏳ M4 |
| 6.5 | M3 里程碑文档更新 | ✅ |

---

## 关键依赖链

```
Sprint 1 (SimCore 闭环) ──→ Sprint 2 (战斗微操) ──→ Sprint 3 (多 Agent)
                    ──→ Sprint 4 (Godot 体验)
Sprint 2 ──→ Sprint 5 (Fog-of-War)
Sprint 3 + 4 + 5 ──→ Sprint 6 (整合)
```

## P2 延后项（M4 处理）

- 编队系统 (Ctrl+1~9)
- 小地图点击跳转摄像机
- 战斗回放可视化（Godot 回放模式）
- CI/CD 扩展（Godot headless + 冒烟）

## 风险与缓解

| 风险 | 状态 |
|------|------|
| SimCore 闭环修复发现规则不一致 | ✅ 已解决（7个bug修复） |
| Godot Retina 渲染回归 | ✅ FIXED_TOP_LEFT 修复 |
| MsgHub 实现复杂度 | ✅ 先用简单 broadcast |
| Fog-of-War 性能 | ✅ 8x8 chunk 无压力 |