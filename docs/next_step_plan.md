# RTS-AI 下一步计划 (2026-06-04 更新)

## 当前进度总结

### ✅ 已完成
- **Track B Phase B1**: 三族可玩闭环 80%+ (建筑/单位映射、HUD种族感知、AI建造训练、T键种族映射)
- **Track B Phase B3**: 高地优势 ✅、护盾回复 ✅、隐身/反隐 ✅
- **Track B Phase B4**: 结算画面 ✅、APM ✅、录制/回放 ✅
- **VFX**: 攻击闪烁/死亡爆炸/选择呼吸/悬停高亮/建造进度条 ✅
- **Pylon供电圈** ✅、Zerg Morph ✅、Archon合体 ✅、研究/升级 ✅
- **SimCore**: 227 tests passing ✅
- **Track A 脚手架**: Dashboard (6001) + API (8000) + Redis 启动正常
- **MemoryLake**: 519K tokens 已同步，auto 模式
- **Bug修复本轮**: gas worker循环采集 ✅、AbilityManager拦截KEY_B ✅、show_build_panel缺rebuild ✅

### ⚠️ 需要验证/修复
- **B键建造面板**: 代码已修复，需 Godot 中实际验证
- **54个 uncommitted files**: 需要 commit
- **manifest 精灵覆盖度**: 建筑 atlas 缺失 (BUILD_CATALOG 有43条但很多没精灵)
- **B3.3 Creep 蔓延**: 未实现
- **B3.5 Psi Storm / B3.7 Siege Tank / B3.8 Carrier / B3.9 Arbiter / B3.10 Comsat**: 未实现
- **B2.1-2.4 战斗动画**: 弹道/死亡动画/采集动画/建造动画都只有占位
- **B4.1 1v1匹配流程**: 主菜单→选族→游戏→结算全链路未闭环
- **Track A 数据接入**: 当前用 mock_data，未接入 SimCore 真实对局

---

## 下一步计划（按优先级排序）

### 🔴 P0: 本轮立刻做

| # | 任务 | 预计 | 说明 |
|---|------|------|------|
| 1 | **Commit 54个 uncommitted files** | 5min | git add + commit，当前太多未提交变更 |
| 2 | **Godot 验证 B键建造面板** | 15min | 本轮已修3个bug，需要实际 F5 验证 |

### 🟡 P1: 本周完成 (1-2天)

| # | 任务 | 预计 | 说明 |
|---|------|------|------|
| 3 | **Track A 接入 SimCore 真实数据** | 4h | 替换 mock_data → 调用 HTTP Gateway API；对局列表从 /api/state 拉取；WebSocket 从 ws://8080 推送 tick |
| 4 | **1v1 匹配全链路闭环** | 3h | 主菜单选族 → /api/start → 游戏中 → 检测胜负 → 结算画面 → (可选)回到主菜单 |
| 5 | **manifest 精灵补齐 (核心建筑)** | 2h | 至少补齐每族5个核心建筑 (T: CC/Supply/Barracks/Factory/Starport, Z: Hatch/Pool/HyDen/Spire/Extractor, P: Nexus/Pylon/Gateway/Robo/Stargate) |

### 🟢 P2: 2周内推进

| # | 任务 | 领域 | 说明 |
|---|------|------|------|
| 6 | **战斗手感升级** | B2 | 弹道飞行物(Vulture炮弹/Marine子弹)、死亡动画帧序列、Worker采矿搬运动画、建筑建造施工效果 |
| 7 | **关键单位技能** | B3 | Psi Storm (Templar AOE) → Siege Mode (Tank) → Carrier Interceptor → Comsat Scan |
| 8 | **Track A Phase A1 核心功能** | A1 | 对局列表页(真实数据) + 实时观战(WebSocket渲染) + KDA/资源曲线(Recharts) |

### ⚪ P3: 1月内推进

| # | 任务 | 领域 | 说明 |
|---|------|------|------|
| 9 | **Creep 蔓延** | B3.3 | Zerg建筑周围creep纹理扩展 |
| 10 | **Track A Phase A2 训练管理** | A2 | 训练任务提交/监控 + League版本池 + Promotion Gate可视化 |
| 11 | **AI 策略多样性** | 核心AI | 当前ScriptAI只走一条路线，需要多策略(rush/eco/turtle)、难度差异 |
| 12 | **热键自定义 + 难度选择** | B4 | 设置面板可改键位 + AI Easy/Medium/Hard 行为差异 |

---

## 建议执行顺序

```
今天: #1 Commit → #2 验证B键
明天: #4 全链路闭环 → #3 Track A 数据接入
本周: #5 精灵补齐 → #6 战斗手感
下周: #7 关键技能 → #8 Track A 核心仪表盘
```

### 关键里程碑
- **M3 (本周)**: 全链路可玩 — 从主菜单到结算画面完整闭环 + Track A 看到真实对局
- **M4 (2周)**: 战斗手感可感知 — 弹道/死亡动画/技能特效到位
- **M5 (1月)**: AI 可训练 — Track A 训练管理闭环 + 多策略AI对手
