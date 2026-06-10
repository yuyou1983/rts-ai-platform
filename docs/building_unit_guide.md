# 🏗️ 建筑操作与兵种生产指南

## 通用操作

| 操作 | 按键 | 说明 |
|------|------|------|
| 打开建造菜单 | **B** | 需要选中 Worker |
| 选择建筑后放置 | **右键** | B→点建筑→右键放 |
| 快速训练 | **T** | 选中建筑后按T训练当前建筑默认兵种 |
| 训练面板 | 选中建筑自动弹出 | 点击面板中的按钮 |
| 取消建造面板 | **B** / **Esc** | 再按一次B或Esc关闭 |
| 集结点 | **右键** | 选中建筑后右键空地设集结点 |

---

## 🟦 Terran (人族) — 种族ID: 1

### 建筑列表 (按B → 选择)

| 建筑名 | 抽象键 | 矿 | 气 | 前置 |
|--------|--------|----|----|------|
| Command Center | base | 400 | 0 | — |
| Supply Depot | supply_depot | 100 | 0 | — |
| Refinery | refinery | 100 | 0 | — |
| Barracks | barracks | 150 | 0 | — |
| Factory | factory | 200 | 100 | Barracks |
| Starport | starport | 200 | 150 | Factory |
| Missile Turret | defense_turret | 75 | 0 | — |
| Bunker | bunker | 100 | 0 | — |
| Academy | tech_infantry | 150 | 0 | — |
| Engineering Bay | tech_armor | 125 | 0 | — |
| Armory | armory | 100 | 50 | Factory |
| Science Facility | science | 100 | 150 | Armory |

### 训练兵种 (选中建筑自动弹出面板)

| 建筑 | 兵种 | 矿 | 气 | 备注 |
|------|------|----|----|------|
| **Command Center** | SCV | 50 | 0 | 工人，T键快速训练 |
| **Barracks** | Marine | 50 | 0 | 基础步兵，T键 |
| | Firebat | 50 | 25 | 火兵 |
| | Ghost | 25 | 75 | 特种兵 |
| | Medic | 50 | 25 | 医疗兵 |
| **Factory** | Vulture | 75 | 0 | 雷车 |
| | Siege Tank | 150 | 100 | 坦克 |
| | Goliath | 100 | 50 | 机甲 |
| **Starport** | Wraith | 150 | 100 | 隐形战机 |
| | Dropship | 100 | 100 | 运输机 |
| | Vessel | 100 | 225 | 科学船 |
| | Valkyrie | 250 | 125 | 对空舰 |
| | BattleCruiser | 400 | 300 | 大和舰 |

### 研究 (选中对应建筑自动弹出)

| 建筑 | 研究 | 矿 | 气 |
|------|------|----|----|
| Academy | Stim Pack | 100 | 100 |
| Engineering Bay | U-238 Shells | 150 | 150 |

---

## 🟪 Zerg (虫族) — 种族ID: 2

### 建筑列表 (按B → 选择)

| 建筑名 | 抽象键 | 矿 | 气 | 前置 |
|--------|--------|----|----|------|
| Hatchery | base | 400 | 0 | — |
| Extractor | refinery | 100 | 0 | — |
| Spawning Pool | barracks | 150 | 0 | — |
| Hydralisk Den | factory | 200 | 100 | Spawning Pool |
| Spire | starport | 200 | 150 | Hydralisk Den |
| Creep Colony | defense | 75 | 0 | — |
| Spore Colony | defense_air | 75 | 0 | Creep Colony |
| Sunken Colony | defense_ground | 50 | 50 | Creep Colony |
| Evolution Chamber | tech_basic | 75 | 0 | — |
| Lair (升级) | morph_base | 150 | 100 | 选中Hatchery升级 |
| Hive (升级) | morph_base2 | 200 | 150 | 选中Lair升级 |
| Queen Nest | queen_nest | 100 | 100 | Lair |
| Defiler Mound | defiler_mound | 100 | 100 | Lair |
| Nydus Canal | nydus | 150 | 100 | Lair |
| Ultralisk Cavern | ultra_cavern | 200 | 200 | Lair |

### 训练兵种

| 建筑 | 兵种 | 矿 | 气 | 备注 |
|------|------|----|----|------|
| **Hatchery** | Drone | 50 | 0 | 工人，T键快速训练 |
| | Overlord | 100 | 0 | 房宿（人口） |
| **Spawning Pool** | Zergling | 50 | 0 | 狗，T键 |
| | Hydralisk | 75 | 25 | 刺蛇 |
| **Hydralisk Den** | Ultralisk | 200 | 200 | 大牛 |
| **Spire** | Mutalisk | 100 | 100 | 飞龙 |
| | Queen | 100 | 100 | 皇后 |
| | Defiler | 50 | 150 | 蝎子 |
| | Scourge | 25 | 75 | 自爆蚊 |

### 单位 Morph (自动)

| 源单位 | 目标 | 条件 |
|--------|------|------|
| Mutalisk | Guardian | 后期AI自动变形 |
| Mutalisk | Devourer | 后期AI自动变形 |
| Hydralisk | Lurker | 后期AI自动变形 |

### 建筑 Morph (选中建筑自动弹出升级按钮)

| 源建筑 | 目标 | 矿 | 气 |
|--------|------|-----|-----|
| Hatchery | Lair | 150 | 100 |
| Lair | Hive | 200 | 150 |

### 研究

| 建筑 | 研究 | 矿 | 气 |
|------|------|----|----|
| Evolution Chamber | Melee Attacks +1 | 100 | 100 |
| Evolution Chamber | Carapace +1 | 150 | 150 |

---

## 🟨 Protoss (神族) — 种族ID: 3

### 建筑列表 (按B → 选择)

| 建筑名 | 抽象键 | 矿 | 气 | 前置 |
|--------|--------|----|----|------|
| Nexus | base | 400 | 0 | — |
| Pylon | supply_depot | 100 | 0 | — |
| Assimilator | refinery | 100 | 0 | — |
| Gateway | barracks | 150 | 0 | — |
| Robotics Facility | factory | 200 | 100 | Gateway |
| Stargate | starport | 200 | 150 | Robotics |
| Photon Cannon | defense | 150 | 0 | Forge |
| Shield Battery | shield_station | 100 | 0 | Gateway |
| Forge | tech_basic | 100 | 0 | — |
| Cybernetics Core | tech_cyber | 200 | 0 | Gateway |
| Citadel of Adun | tech_infantry | 150 | 100 | Cybernetics Core |
| Templar Archives | tech_templar | 150 | 200 | Citadel of Adun |
| Robotics Support Bay | tech_robotics | 100 | 50 | Robotics |
| Fleet Beacon | tech_fleet | 300 | 200 | Stargate |
| Observatory | tech_observatory | 50 | 100 | Robotics |
| Arbiter Tribunal | tech_arbiter | 200 | 300 | Stargate |

### 训练兵种

| 建筑 | 兵种 | 矿 | 气 | 备注 |
|------|------|----|----|------|
| **Nexus** | Probe | 50 | 0 | 工人，T键快速训练 |
| **Gateway** | Zealot | 100 | 0 | 狂徒，T键 |
| | Dragoon | 125 | 50 | 龙骑 |
| | Templar | 50 | 150 | 闪电侠 |
| | Dark Templar | 125 | 100 | 暗黑 |
| **Robotics** | Reaver | 200 | 100 | 金甲虫 |
| | Shuttle | 200 | 0 | 运输机 |
| | Observer | 25 | 75 | 侦察眼（隐身+反隐） |
| **Stargate** | Scout | 250 | 150 | 侦察机 |
| | Carrier | 350 | 250 | 航母 |
| | Arbiter | 350 | 300 | 仲裁者 |
| | Corsair | 150 | 100 | 海盗船 |

### 合体 (选中 ≥2 同类 Templar 自动弹出按钮)

| 源单位 | 需要 | 目标 | 费用 |
|--------|------|------|------|
| Templar | 2个 | Archon | 0矿 0气 |
| Dark Templar | 2个 | Dark Archon | 0矿 0气 |

### 研究

| 建筑 | 研究 | 矿 | 气 |
|------|------|----|----|
| Forge | Ground Weapons +1 | 100 | 100 |
| Forge | Ground Armor +1 | 100 | 100 |
| Forge | Plasma Shields +1 | 100 | 100 |

---

## ⚡ 操作速查

### 开局标准流程
```
1. 选中基地 → T → 训练工人
2. 选中工人 → 右键矿脉 → 自动采矿（循环）
3. 选中工人 → B → Supply Depot → 右键放置
4. 选中工人 → B → Barracks → 右键放置
5. 选中兵营 → 面板点 Marine/Zergling/Zealot
6. 选中工人 → 右键气矿 → 自动采气（需先造 Refinery）
```

###快捷键总览
| 键 | 功能 | 条件 |
|----|------|------|
| B | 建造面板 开/关 | 选中Worker |
| T | 快速训练 | 选中基地/兵营 |
| A | 攻击移动 | 选中战斗单位 |
| S | 停止 | 选中单位 |
| H | 原地驻守 | 选中单位 |
| P | 巡逻 | 选中单位 |
| G | 采集 | 选中Worker → 右键资源 |
| Esc | 取消选择/关闭面板 | — |
| 1-9 | 控制组 | Ctrl+数字=编队 |
| F | 摄像机回基地 | — |
