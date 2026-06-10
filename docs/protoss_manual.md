# 🛡️ Protoss 操作手册 — DevKCClaw RTS Platform

> **"En Taro Adun!"** — 神族以科技与护盾取胜，兵精不靠量。

---

## 一、种族特色

| 特性 | 说明 |
|------|------|
| **Plasma Shield** | 所有单位和建筑拥有额外护盾层，脱战后自动回复 |
| **Pylon Power** | 建筑必须在 Pylon 供电范围内才能运作（Nexus/Pylon/Assimilator 除外） |
| **Warp-in** | Gateway 训练单位直接出现在建筑旁（当前版本） |
| **高单兵质量** | 单兵战斗力三族最强，但造价也最高 |

---

## 二、基础操控

### 2.1 通用快捷键

| 按键 | 功能 |
|------|------|
| `WASD` / 方向键 | 移动摄像机 |
| 鼠标边缘 | 摄像机自动滚屏 |
| 滚轮 | 缩放 (0.5x – 2.0x) |
| 中键拖拽 | 平移摄像机 |
| `F` | 摄像机跟随选中单位 |
| `Esc` | 取消选择 / 关闭建造面板 |
| `1`–`9` | 切换控制组 |
| `Ctrl+1-9` | 创建控制组 |
| `Shift+1-9` | 追加到控制组 |
| 双击 `1-9` | 摄像机跳到控制组 |

### 2.2 选择 & 右键指令

| 操作 | 功能 |
|------|------|
| 左键点选 | 选中单位/建筑 |
| 左键框选 | 框选多个单位 |
| `Shift+左键` | 追加选择 |
| `Ctrl+左键` / 双击 | 选中屏幕上所有同类单位 |
| 右键空地 | 移动（Move） |
| 右键敌方 | 攻击（Attack） |
| 右键矿脉 | 采集（Gather） |
| 右键气矿 | 采气（Gather Gas） |
| `A` + 左键 | 攻击移动 |
| `S` | 停止（Stop） |
| `H` | 原地驻守（Hold） |
| `P` + 左键 | 巡逻（Patrol） |
| `G` + 左键 | 强制采集 |

### 2.3 建造 & 训练

| 按键 | 功能 |
|------|------|
| `B` | 开关建造面板（选中 Probe 时） |
| `T` | 快速训练（选中建筑时） — 自动按种族训练对应单位 |
| 右键放置 | 建造面板打开后，右键点击地图放置建筑 |

---

## 三、建筑科技树

### 3.1 全科技树图

```
                    ┌──────────┐
                    │  Nexus   │  400⛏ 0🛢
                    │ (主基地)  │  → 训练 Probe
                    └────┬─────┘
                         │
           ┌─────────────┼─────────────┐
           │             │             │
    ┌──────▼──────┐ ┌────▼─────┐ ┌────▼──────────┐
    │    Pylon    │ │ Assimilator│ │    Forge      │
    │  100⛏ 0🛢  │ │ 100⛏ 0🛢 │ │  150⛏ 0🛢    │
    │ (供电+人口) │ │  (采气)   │ │  (升级武器/护甲)│
    └──────┬──────┘ └──────────┘ └────┬──────────┘
           │                        │
    ┌──────▼──────┐          ┌──────▼──────────┐
    │  Gateway    │          │  Photon Cannon  │
    │  150⛏ 0🛢  │          │  150⛏ 0🛢      │
    │ (兵营)      │          │  (防御塔,需Forge)│
    └──┬───┬───┬─┘          └─────────────────┘
       │   │   │
       │   │   └──────────────────┐
       │   │                  ┌───▼──────────────┐
       │   │                  │  Shield Battery   │
       │   │                  │  100⛏ 0🛢        │
       │   │                  │  (护盾充能站)     │
       │   │                  └──────────────────┘
       │   └──────────────┐
       │              ┌───▼──────────────┐
       │              │ Cybernetics Core │
       │              │  200⛏ 0🛢       │
       │              │ (升级空中武器/护甲)│
       │              └──┬──────┬────────┘
       │                 │      │
       │     ┌───────────▼┐  ┌──▼───────────────┐
       │     │  StarGate  │  │ CitadelOfAdun    │
       │     │ 150⛏ 150🛢 │  │  150⛏ 100🛢     │
       │     │ (星门)     │  │ (速度升级前置)    │
       │     └──┬──┬──┬──┘  └──────┬───────────┘
       │        │  │  │            │
       │        │  │  │    ┌──────▼──────────┐
       │        │  │  │    │ TemplarArchives │
       │        │  │  │    │  150⛏ 200🛢     │
       │        │  │  │    │ (Templar/DT解锁) │
       │        │  │  │    └──────┬──────────┘
       │        │  │  │           │
       │        │  │  │    ┌──────▼───────────────┐
       │        │  │  │    │ ArbiterTribunal      │
       │        │  │  │    │  200⛏ 300🛢         │
       │        │  │  │    │ (Arbiter升级)         │
       │        │  │  │    └──────────────────────┘
       │        │  │  │
       │        │  │  └───┐
       │        │  │  ┌───▼──────────┐
       │        │  │  │  FleetBeacon │
       │        │  │  │  300⛏ 200🛢 │
       │        │  │  │ (Carrier解锁)│
       │        │  │  └──────────────┘
       │        │  │
       │   ┌────▼──▼──────────┐
       │   │ Robotics Facility │
       │   │  200⛏ 200🛢      │
       │   │  (机械工厂)       │
       │   └──┬──────┬────────┘
       │      │      │
       │  ┌───▼────┐ ┌▼──────────────────┐
       │  │Observatory│ │RoboticsSupportBay │
       │  │ 50⛏100🛢│ │  100⛏ 50🛢       │
       │  │(Observer)│ │ (Reaver升级)      │
       │  └──────────┘ └───────────────────┘
       │
       └─────→ (当前简化版: 无前置)
              build 面板直接可用
```

### 3.2 建筑详细数据

| 建筑 | 俗称 | 晶矿 | 气矿 | 建造时间 | 前置 | 训练单位 | 说明 |
|------|------|-----|------|---------|------|---------|------|
| **Nexus** | 主基地 | 300 | 0 | 1200 | — | Probe | 自带供电，不需要Pylon |
| **Pylon** | 供电塔 | 100 | 0 | 400 | — | — | 提供人口+供电范围 |
| **Assimilator** | 气矿 | 100 | 0 | 400 | — | — | 在气泉上建造 |
| **Gateway** | 兵营 | 150 | 0 | 600 | — | Zealot, Dragoon, Templar, DarkTemplar | 当前版本不需Pylon即可训练 |
| **Forge** | 铁匠铺 | 150 | 0 | 600 | — | — | 升级地面武器/护甲 |
| **Photon Cannon** | 光子炮 | 150 | 0 | 400 | Forge | — | 对空对地防御塔 |
| **Cybernetics Core** | 控制核心 | 200 | 0 | 600 | Gateway | — | 升级空中武器/护甲，解锁Dragoon |
| **Shield Battery** | 护盾站 | 100 | 0 | 400 | Gateway | — | 为附近单位充能护盾 |
| **Robotics Facility** | 机械厂 | 200 | 200 | 800 | Cybernetics Core | Shuttle, Reaver, Observer | 重型机械单位 |
| **Stargate** | 星门 | 150 | 150 | 800 | Cybernetics Core | Scout, Carrier, Arbiter, Corsair | 空中单位 |
| **Citadel of Adun** | 圣堂 | 150 | 100 | 600 | Cybernetics Core | — | Zealot速度升级前置 |
| **Robotics Support Bay** | 机械湾 | 100 | 50 | 400 | Robotics Facility | — | Reaver升级 |
| **Fleet Beacon** | 舰队灯塔 | 300 | 200 | 800 | Stargate | — | Carrier解锁/升级 |
| **Templar Archives** | 圣殿 | 150 | 200 | 600 | Citadel of Adun | — | Templar/DT技能解锁 |
| **Observatory** | 观测站 | 50 | 100 | 400 | Robotics Facility | — | Observer升级 |
| **Arbiter Tribunal** | 仲裁庭 | 200 | 300 | 800 | Stargate + Templar Archives | — | Arbiter升级 |

---

## 四、单位数据

### 4.1 全兵种一览

| 单位 | 俗称 | 晶矿 | 气矿 | 人口 | 训练时间 | 训练建筑 | 定位 |
|------|------|-----|------|------|---------|---------|------|
| **Probe** | 农民 | 50 | 0 | 1 | 200 | Nexus | 采集/建造 |
| **Zealot** | 狂徒 | 100 | 0 | 2 | 300 | Gateway | 近战主力 |
| **Dragoon** | 龙骑 | 125 | 50 | 2 | 400 | Gateway | 远程对空 |
| **Templar** | 闪电 | 50 | 150 | 2 | 500 | Gateway | 法术AOE |
| **Dark Templar** | 隐刀 | 125 | 100 | 2 | — | Gateway | 永久隐身近战 |
| **Shuttle** | 运输机 | 200 | 0 | 2 | 600 | Robotics Facility | 空中运输 |
| **Reaver** | 金甲虫 | 200 | 100 | 4 | 700 | Robotics Facility | 攻城AOE |
| **Observer** | 探测器 | 25 | 75 | 1 | 400 | Robotics Facility | 永久隐身侦察 |
| **Scout** | 侦察机 | 300 | 150 | 3 | 800 | Stargate | 空优战斗机 |
| **Carrier** | 航母 | 350 | 250 | 6 | 1400 | Stargate | 重型空战 |
| **Arbiter** | 仲裁者 | 100 | 350 | 4 | 1600 | Stargate | 隐身场+传送 |
| **Corsair** | 海盗船 | 150 | 100 | 2 | 400 | Stargate | 对空干扰 |

> **注**：Archon / Dark Archon 为合体单位，当前版本暂未实现。

### 4.2 单位分类

```
┌───────────┐
│ 地面单位   │
├───────────┤
│ Probe     │ ← 经济核心，造建筑
│ Zealot    │ ← 前排肉盾+DPS
│ Dragoon   │ ← 远程+对空
│ Templar   │ ← 法术爆发
│ Dark Templar│ ← 隐身刺客
│ Reaver    │ ← 攻城重炮
├───────────┤
│ 空中单位   │
├───────────┤
│ Shuttle   │ ← 运输
│ Observer  │ ← 侦察
│ Scout     │ ← 空战
│ Carrier   │ ← 战略核心
│ Arbiter   │ ← 战术支援
│ Corsair   │ ← 对空控场
└───────────┘
```

---

## 五、标准开局流程

### 5.1 简化版开局（当前版本可用）

> 初始资源：200 晶矿 / 0 气矿 / 6 Probe

```
Tick   操作                   说明
───── ─────────────────────── ─────────────────────────
  0   全部 Probe 采矿          左键框选，右键矿脉
  1   Nexus 训练 Probe (T键)   保持农民不断
 20   第 7 个 Probe 出发       晶矿够 100
 30   选一个空闲 Probe         B键 → Pylon → 右键放置
 50   Pylon 建造中             放在基地附近（供电范围覆盖后续建筑）
 60   训练第 8 个 Probe        保持不断
 80   Pylon 完成 ✓             人口上限 +8
100   选空闲 Probe             B键 → Gateway → 右键放置
      同时训练 Probe           人口够就训练
150   Gateway 完成前           造 Assimilator (100矿)
200   Gateway 完成 ✓           可以训练 Zealot!
200   第一批 Zealot 出征       T键 或点选训练面板
250   持续训练 Zealot + Probe  双线运营
```

### 5.2 速攻流程（2-Gate Rush）

```
Tick   操作
───── ───────────────────────
  0   6 Probe 采矿
 30   造 Pylon (100矿)
 50   造 Gateway (150矿) — 晶矿一够立即造
 80   造第二个 Pylon
100   造第二个 Gateway (150矿)
150   双 Gateway 狂出 Zealot
250   4-6 Zealot 出门压制
```

### 5.3 稳健运营（Fast Expand）

```
Tick   操作
───── ───────────────────────
  0   6 Probe 采矿
 30   造 Pylon
 50   造 Gateway
100   造 Assimilator (100矿)
120   造 Cybernetics Core (200矿) — 解锁 Dragoon
150   造第二个 Pylon
200   开分矿 — 新 Nexus (300矿)
250   双矿运营，科技攀升 Stargate/Robotics
```

---

## 六、HUD 建造面板速查

### 6.1 选中 Probe 时 — 建造面板

| 按钮 | 建筑 | 晶矿 | 气矿 | 前置 |
|------|------|-----|------|------|
| `base` | Nexus | 400 | 0 | — |
| `supply_depot` | Pylon | 100 | 0 | — |
| `refinery` | Assimilator | 100 | 0 | — |
| `barracks` | Gateway | 150 | 0 | — |
| `factory` | Robotics Facility | 200 | 100 | Gateway |
| `starport` | Stargate | 200 | 150 | Gateway |

> **建造流程**：`B` 打开面板 → 左键选建筑 → 右键放置地图
> **Pylon 供电**：建筑必须放在 Pylon 蓝色供电圈内才能运作！

### 6.2 选中建筑时 — 训练面板

| 建筑 | 可训练单位 |
|------|-----------|
| Nexus | Probe (50矿) |
| Gateway | Zealot (100矿), Dragoon (125矿50气), Templar (50矿150气), Dark Templar (125矿100气) |
| Robotics Facility | Shuttle (200矿), Reaver (200矿100气) |
| Stargate | Scout (300矿150气), Carrier (350矿250气), Arbiter (100矿350气), Corsair (150矿100气) |

> **训练快捷键**：选中建筑 → `T` 键快速训练（自动选种族对应单位）
> **面板训练**：点击训练面板上的兵种按钮

---

## 七、Pylon 供电机制

```
          ┌─────────────────────────┐
          │    Pylon 供电范围 (8格)    │
          │                         │
          │   ┌──────┐  ┌──────┐   │
          │   │Gate- │  │Cyber-│   │
          │   │way   │  │Core  │   │
          │   └──────┘  └──────┘   │
          │                         │
          │         ⚡ Pylon        │
          │                         │
          └─────────────────────────┘

  ✅ 供电圈内：  Gateway, Forge, Cybernetics Core 等 → 正常运作
  ❌ 供电圈外：  上述建筑 → 离线，无法训练/研究
  🔒 自供电：    Nexus, Pylon, Assimilator → 不需要Pylon也能运作
  ⚠️ 当前简化版：Gateway 也设为自供电，降低上手门槛
```

---

## 八、Protoss vs 各族要点

### vs Terran

| 要点 | 说明 |
|------|------|
| Zealot 冲坦克 | 早期 Zealot 可以冲散未架坦克 |
| Dragoon 打坦克 | 架坦克后 Dragoon 射程优势 |
| Templar 清兵 | Psi Storm 一发清马林+医疗兵 |
| Observer 反隐 | 必须造 Observer 看 Mine / Ghost |
| Carrier 终局 | 大和打不过 Carrier（数量够的话） |

### vs Zerg

| 要点 | 说明 |
|------|------|
| Zealot + Archon | 近战群打 Zergling + Hydra 最优 |
| Corsair 封虫 | Disruption Web 封防空，空投无忧 |
| Reaver 清虫 | Scarab 一发秒一片 Zergling |
| 高地 Dragoon | 利用高地打低地优势 |
| 早期防守 | 1-2 Zealot 堵口 + Photon Cannon |

---

## 九、当前版本已知限制

| 项目 | 状态 | 说明 |
|------|------|------|
| Pylon 供电检查 | ⚠️ 简化 | Gateway 当前自供电，无需 Pylon |
| Templar 技能 | ❌ 未实现 | Psi Storm / Hallucination 暂无 |
| Dark Templar 隐身 | ❌ 未实现 | 永久隐身机制待做 |
| Arbiter 隐身场 | ❌ 未实现 | Recall / Stasis 待做 |
| Reaver Scarab | ❌ 未实现 | 弹药系统待做 |
| Carrier 拦截机 | ❌ 未实现 | Interceptor 机制待做 |
| Corsair Web | ❌ 未实现 | Disruption Web 待做 |
| Shield Battery | ❌ 未实现 | 充能机制待做 |
| 建筑升级 | ❌ 未实现 | 升级研究按钮待做 |
| Archon 合体 | ❌ 未实现 | 2 Templar 合体待做 |
| Scout_ship 显示名 | ⚠️ | manifest 中 ID 为 `Scout_ship`，面板显示 `Scout` |

---

## 十、快速参考卡（可打印）

```
╔══════════════════════════════════════════════════╗
║         🛡️  PROTOSS QUICK REFERENCE  🛡️         ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  建造: B → 选建筑 → 右键放置                       ║
║  训练: 选中建筑 → T (或点面板)                      ║
║                                                  ║
║  ┌──────── 建筑造价 ────────┐                     ║
║  │ Nexus    300⛏           │                     ║
║  │ Pylon    100⛏  ←人口+供电│                     ║
║  │ Gateway  150⛏  ←兵营    │                     ║
║  │ Assimil  100⛏  ←采气    │                     ║
║  │ Robotics 200⛏ 200🛢     │                     ║
║  │ Stargate 150⛏ 150🛢     │                     ║
║  └─────────────────────────┘                     ║
║                                                  ║
║  ┌──────── 核心单位 ────────┐                     ║
║  │ Probe     50⛏           │                     ║
║  │ Zealot   100⛏           │                     ║
║  │ Dragoon  125⛏  50🛢     │                     ║
║  │ Templar   50⛏ 150🛢     │                 ║
║  │ DarkT   125⛏ 100🛢      │                     ║
║  └─────────────────────────┘                     ║
║                                                  ║
║  ⚡ Pylon 供电 = 神族命脉!                         ║
║  ⚡ 护盾脱战自动回 = 拉扯打法!                      ║
╚══════════════════════════════════════════════════╝
```

---

*DevKCClaw RTS Platform v0.4 · Protoss Manual · 2026-06*
