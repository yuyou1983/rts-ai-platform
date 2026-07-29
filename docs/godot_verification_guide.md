# 🎮 Godot 全功能验证指南

> 前提：gRPC Server (50051) + HTTP Gateway (8080) 必须已启动

---

## 零、启动后端

```bash
# 终端1: gRPC Server
cd ~/code/rts-ai-platform
python3 -m simcore.grpc_server --port 50051

# 终端2: HTTP Gateway
cd ~/code/rts-ai-platform
python3 -m simcore.http_gateway --grpc-port 50051 --http-port 8080

# 终端3: 启动 Godot
open -a Godot ~/code/rts-ai-platform/godot
# 或命令行:
/Applications/Godot.app/Contents/MacOS/Godot ~/code/rts-ai-platform/godot &
```

验证后端存活:
```bash
curl http://localhost:8080/health        # → {"status":"ok"}
curl http://localhost:8080/api/state      # → 空状态
```

---

## 一、主菜单 (main_menu.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 1 | 打开 Godot 运行 (F5) | 显示主菜单界面 | 基础渲染 |
| 2 | 选择 P1 种族下拉框 | 下拉显示 Terran / Zerg / Protoss | 种族选择UI |
| 3 | 选择 P1=Terran, P2=Zerg | 下拉选中生效 | 种族组合 |
| 4 | 点击「开始游戏」 | 屏幕切换到游戏画面，Godot 输出面板出现 `/start` 请求日志 | start_game |
| 5 | 选 P1=Protoss, P2=Terran 重复 | 同上 | 9种组合全覆盖 |
| 6 | 观察网络日志 | 输出面板有 `POST /api/start` → 200 | HTTP通信 |

---

## 二、游戏画面 — 基础渲染 (game_view.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 7 | 游戏开始后观察地图 | 看到64×64网格地形，高低地用不同颜色 | elevation_grid 渲染 |
| 8 | 观察初始实体 | P1 在左下角看到基地+6 worker | mapgen 种族感知 |
| 9 | Protoss 场景 | 看到 Nexus + 6 Probe | P族基础单位 |
| 10 | Zerg 场景 | 看到 Hatchery + 6 Drone | Z族基础单位 |
| 11 | Terran 场景 | 看到 CommandCenter + 6 SCV | T族基础单位 |

---

## 三、摄像机 (camera_controller.gd)

| # | 操作 | 预期 |
|---|------|------|
| 12 | WASD / 方向键 | 摄像机平滑移动 |
| 13 | 鼠标移到屏幕边缘 | 摄像机向该方向滚动 |
| 14 | 滚轮上下 | 缩放（🔍+/🔍-） |
| 15 | 按住中键拖拽 | 摄像机平移 |
| 16 | 按 F | 摄像机跳回基地 |

---

## 四、选择 (selection_manager.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 17 | 左键点一个单位 | 绿色选中环 + 呼吸脉冲 | 选择VFX |
| 18 | 左键框选多个单位 | 框内全选 | 框选 |
| 19 | Shift+点选 | 追加到已选 | Shift追加 |
| 20 | Ctrl+点击同类单位 | 选中屏幕上所有同类 | Ctrl全选 |
| 21 | 双击单位 | 选中屏幕上所有同类 | 双击全选 |
| 22 | Esc | 取消所有选择 | 取消选择 |
| 23 | 数字键 1-9 设置控制组 | 保存当前选择 | 控制组 |
| 24 | 再按对应数字键 | 快速选中该组 | 控制组召回 |

---

## 五、右键指令

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 25 | 选中单位 → 右键空地 | 单位移动到目标位置 | 移动指令 |
| 26 | 选中单位 → 右键敌方 | 单位攻击目标 | 攻击指令 |
| 27 | 选中 Worker → 右键矿脉 | Worker 前往采矿 | 采集指令 |
| 28 | 选中 Worker → 右键气矿 | Worker 前往采气 | 采集指令 |
| 29 | 选中 Worker → 右键基地 | Worker 送回资源 | 存储指令 |

---

## 六、建造面板 (hud.gd BUILD_CATALOG)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 30 | 选中 Worker → 按 B | 建造面板打开，显示种族对应建筑 | B键/HUD按钮 |
| 31 | P1=Terran → 按 B | 看到 SupplyDepot(100矿)、Barracks(150矿)等 | T族建筑列表 |
| 32 | P1=Zerg → 按 B | 看到 SpawningPool(200矿)、HydraliskDen(100/100)等 | Z族建筑列表 |
| 33 | P1=Protoss → 按 B | 看到 Pylon(100矿)、Gateway(150矿)、Stargate(150/150)等 | P族建筑列表 |
| 34 | 资源不足时点建造 | 按钮灰化/提示资源不足 | 资源检查 |
| 35 | 有资源 → 点击建造 | Worker 走向目标位置，建筑开始建造 | 建造流程 |
| 36 | 建造中的建筑 | 上方显示黄色→橙色进度条 | 建造进度VFX |

---

## 七、训练面板 (hud.gd TRAIN_CATALOG + KEY_T)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 37 | 选中基地 → 按 T | 自动训练种族worker (SCV/Drone/Probe) | KEY_T训练 |
| 38 | 选中 Barracks → 按 T | Terran: Marine, Zerg: Zergling, Protoss: Zealot | 兵营KEY_T |
| 39 | 选中 Factory → 按 T | Terran: Vulture, Zerg: Hydralisk, Protoss: Dragoon | 工厂KEY_T |
| 40 | 选中 Starport → 按 T | Terran: Wraith, Zerg: Mutalisk, Protoss: Scout | 星港KEY_T |
| 41 | HUD 训练按钮 | 选中建筑后显示训练按钮列表，点击触发训练 | HUD训练UI |
| 42 | 资源不足时训练 | 训练按钮灰化 | 资源检查 |

---

## 八、升级面板 (hud.gd UPGRADE_CATALOG)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 43 | Zerg 选中 Hatchery | 显示「升级到 Lair (150/100)」按钮 | Zerg升级UI |
| 44 | Zerg 选中 Lair | 显示「升级到 Hive (200/150)」按钮 | Zerg升级UI |
| 45 | 点击升级按钮 | 扣除资源，建筑显示升级进度条 | 升级执行 |

---

## 九、研究面板 (hud.gd RESEARCH_CATALOG)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 46 | Terran 选中 Academy | 显示「Stimpack 研究 (100/100)」按钮 | T族研究 |
| 47 | Protoss 选中 Forge | 显示「地面武器+1 / 地面装甲+1 / 护盾+1」按钮 | P族研究 |
| 48 | Zerg 选中 EvolutionChamber | 显示「近战攻击+1 / 甲壳+1」按钮 | Z族研究 |
| 49 | 点击研究按钮 | 扣除资源，显示研究进度 | 研究执行 |
| 50 | 研究完成 | 该研究按钮灰化，不可重复研究 | 防重复 |

---

## 十、合体 (hud.gd MERGE_RULES)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 51 | 选中 2 个 Templar | HUD 显示「合体为 Archon」按钮 | 合体UI |
| 52 | 选中 2 个 DarkTemplar | HUD 显示「合体为 Dark Archon」按钮 | 合体UI |
| 53 | 点击合体按钮 | 两个 Templar 消失，在第一单位位置生成 Archon | 合体执行 |
| 54 | 合体后观察 Archon | 大型单位，hp=10, shield=350 | Archon属性 |
| 55 | 选中 1 个 Templar + 1 个其他单位 | 不显示合体按钮 | 同类校验 |

---

## 十一、战斗 VFX (game_view.gd + vfx_manager.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 56 | 攻击指令 → 观察开火瞬间 | 单位白色闪烁 0.1s | 攻击闪烁 |
| 57 | 观察血条 | 选中单位上方绿色→红色渐变HP条 | HP条 |
| 58 | 单位被击杀 | 扩散+渐隐圆环（团队色），持续 0.5s | 死亡爆炸 |
| 59 | 建筑被摧毁 | 更大半径的扩散+渐隐圆环 | 建筑爆炸 |
| 60 | 选中单位后观察 | 绿色环 sin(time) 脉冲呼吸 | 选择呼吸 |
| 61 | 鼠标悬停在单位上 | 白色光环高亮（50ms节流） | 悬停高亮 |
| 62 | 建造中的建筑 | 黄→橙渐变进度条，位于HP条上方 | 建造进度 |

---

## 十二、Pylon 供电圈 (game_view.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 63 | P1=Protoss → 造 Pylon | Pylon 周围出现半透明蓝色填充+蓝色描边圆圈 | 供电圈渲染 |
| 64 | P1=Terran → 造 SupplyDepot | 无供电圈 | T族无Pylon |
| 65 | P1=Zerg → 造建筑 | 无供电圈 | Z族无Pylon |

---

## 十三、隐身/反隐 (construction.py + state.py)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 66 | P2 AI 出 DarkTemplar | P1 视角看不到 DT（无 detector 时） | 隐身 |
| 67 | P1 造 Observer 并移到 DT 附近 | DT 变为可见（半透明） | 反隐 |
| 68 | P1 造 MissileTurret | 附近隐身单位可见 | 建筑detector |
| 69 | Observer 走远 | DT 再次消失 | detector距离 |

---

## 十四、高地优势 (rules.py + mapgen.py)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 70 | 按 F 切换等高线显示 | 地图显示高地/低地区域颜色差异 | elevation渲染 |
| 71 | 高地单位攻击低地单位 | 命中率约 70% | 高→低命中 |
| 72 | 低地单位攻击高地单位 | 命中率约 30% | 低→高命中 |
| 73 | 同高度互攻 | 命中率 100% | 平地对等 |

---

## 十五、护盾回复 (economy.py)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 74 | Protoss 单位受攻击后护盾降低 | 观察蓝条(护盾)减少 | 护盾损伤 |
| 75 | 等待 40 tick 无攻击 | 护盾开始每 2 tick +1 回复 | 护盾自动回复 |

---

## 十六、Zerg Morph (construction.py)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 76 | Zerg P2 AI 自动升级 | Hatchery → Lair (观察 building_type 变化) | 建筑morph |
| 77 | Lair → Hive | 同上 | 二级morph |
| 78 | Zerg AI 出 Mutalisk | 后期变为 Guardian | 单位morph |

---

## 十九、AI 对手 (script_ai.py)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 79 | 观察P2 AI行为 | 自动造 supply→barracks→训练兵 | AI建造流程 |
| 80 | Tick 50 左右 | AI 造第一个 SupplyDepot/SpawningPool/Pylon | AI供给 |
| 81 | Tick 100 左右 | AI 造 Barracks/HatcheryLevel2/Gateway | AI兵营 |
| 82 | Tick 200+ | AI 开始出兵并攻击 | AI进攻 |

---

## 二十、APM 计数器 (game_view.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 83 | 快速操作 (选/令/训) | 右上角 APM 数字实时上升 | APM显示 |
| 84 | 停止操作 60s | APM 逐渐下降到 0 | 滚动窗口 |
| 85 | 观察 APM 数值 | 每秒更新一次 | 更新频率 |

---

## 二十一、结算画面 (victory_screen.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 86 | 摧毁P2所有建筑 | 弹出 VICTORY 结算画面 | 胜利检测 |
| 87 | P2 摧毁P1所有建筑 | 弹出 DEFEAT 结算画面 | 失败检测 |
| 88 | 观察结算数据 | 显示: 时长/KDA/资源采集/APM | 统计展示 |
| 89 | 按 R | 重新开始一局 | Restart |
| 90 | 按 Q | 退出到桌面 | Quit |
| 91 | 观察淡入效果 | 结算画面 0.5s 淡入 | 动画 |

---

## 二十二、回放系统 (recorder.py + replay_player.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 92 | 完成一局后检查 /tmp/rts_replays/ | 有 `replay_*.jsonl` 文件 | 自动录制 |
| 93 | 主菜单点 Watch Replay | 进入回放选择 | 回放入口 |
| 94 | 选择回放开始播放 | 地图重放对局过程 | 回放播放 |
| 95 | 按空格 | 暂停/继续 | 暂停控制 |
| 96 | 按 ← → | 逐帧前进/后退 | 逐帧 |
| 97 | 按 ↑ ↓ | 调速 0.5x/1x/2x/4x/8x | 速度控制 |
| 98 | 回放中尝试操作 | 无效（只能观看） | 操作禁用 |

---

## 二十三、战争迷雾 (fog_renderer.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 99 | 观察未探索区域 | 纯黑 | 三级迷雾-未探索 |
| 100 | 观察已探索但无视野区域 | 灰暗 | 三级迷雾-已探索 |
| 101 | 观察有单位视野区域 | 正常亮度 | 三级迷雾-可见 |
| 102 | 单位移动 | 迷雾动态更新 | 迷雾动态 |

---

## 二十四、小地图 (minimap_rect.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 103 | 观察右下角小地图 | 显示所有可见实体（彩色点） | 小地图渲染 |
| 104 | 点击小地图某位置 | 摄像机跳转 | 小地图导航 |
| 105 | 观察小地图视口框 | 白色矩形表示当前视野 | 视口标识 |

---

## 二十五、音频 (audio_manager.gd)

| # | 操作 | 预期 | 覆盖功能 |
|---|------|------|----------|
| 106 | 选中单位 | 播放选中语音 | 选中SFX |
| 107 | 单位攻击 | 播放攻击音效 | 攻击SFX |
| 108 | 单位死亡 | 播放死亡音效 | 死亡SFX |
| 109 | 建造完成 | 播放建造完成语音 | 建造SFX |

---

## 二十六、端到端全流程

| # | 操作 | 预期 |
|---|------|------|
| 109 | T vs Z: 开局→采矿→建Supply→建Barracks→出Marine→进攻 | 完整对局 |
| 110 | P vs T: 开局→采矿→建Pylon→建Gateway→出Zealot→进攻 | 完整对局 |
| 111 | Z vs P: 开局→采矿→建Pool→出Zergling→升级Lair→出Hydralisk | 完整对局 |
| 112 | 打到一方全灭 | 观察结算画面+回放文件生成 |

---

## 故障排查

| 问题 | 解决 |
|------|------|
| Godot 黑屏/无实体 | 检查 HTTP Gateway 是否 8080 在跑: `curl localhost:8080/health` |
| 选了种族但建筑没变 | 检查 grpc_bridge 日志，确认 `/api/start` 返回 200 |
| AI 不建造 | 检查 `_ai_agent` 是否为 None（历史 race kwarg bug） |
| 建筑无法训练 | 检查 Pylon 供电（P族）或资源是否足够 |
| 合体按钮不出现 | 确认选中 ≥2 个同类 Templar |
| 护盾不回复 | 等待 >40 tick 无攻击后观察 |
| 高地没效果 | 确认 `enable_elevation: true` 在 config 或 mapgen 默认 |
| 6001 端口无法访问 | Platform Dashboard 用浏览器，Godot 游戏走 8080 |

---

## 二十七、SC1 手感专项验收 (Phase 6)

> 基于 `docs/reports/godot-sc1-feel-gap-report.md` 的 10 项评分，每项 1-5 分。低于 3 分的项目必须进入下一轮 backlog。

### 验收前准备

```bash
# 确保 sc1_feel_baseline.json 和 control_feel_config.json 存在
ls godot/resources/feel/sc1_feel_baseline.json godot/resources/feel/control_feel_config.json
# 运行 pytest 基线
python3 -m pytest tests/godot/ -q
```

### A. Terran 验收

| # | 操作 | SC1 参考行为 | 评分 1-5 | 备注 |
|---|------|------------|---------|------|
| A1 | 框选 4 个 SCV | 框选无延迟，选中高亮即时出现 | | |
| A2 | 右键矿区 | 地面出现绿色 ping，SCV 即刻开始移动 | | |
| A3 | Ctrl+1 编队 | 编队闪光反馈清楚 | | |
| A4 | 双击 1 回到编队 | 摄像机跳转至编队中心 | | |
| A5 | 建造 Barracks | 建筑半透明呼吸 ghost，完成后淡入 | | |
| A6 | Marine attack-move | 攻击 ping + muzzle flash 命中反馈 | | |

### B. Zerg 验收

| # | 操作 | SC1 参考行为 | 评分 1-5 | 备注 |
|---|------|------------|---------|------|
| B1 | Drone 采集 | 右键 ping + 即时移动 | | |
| B2 | Zergling move/attack | 移动 ping + 近战命中 acid/melee 效果 | | |
| B3 | Hydralisk 远程攻击 | 弹道 tracer + 命中 spark | | |
| B4 | Hatchery footprint 检查 | 选择圈、血条、sprite 边界对齐 | | |

### C. Protoss 验收

| # | 操作 | SC1 参考行为 | 评分 1-5 | 备注 |
|---|------|------------|---------|------|
| C1 | Probe 采集 | 同 Terran/Zerg worker 手感 | | |
| C2 | Pylon/Nexus/Zealot/Dragoon 比例 | Scale 视图中 worker→infantry→townhall 梯度清晰 | | |
| C3 | shield hit 检查 | 被攻击时蓝色闪烁 + shield_hit VFX | | |

### D. Mixed Combat 验收

| # | 操作 | SC1 参考行为 | 评分 1-5 | 备注 |
|---|------|------------|---------|------|
| D1 | 6v6 | 命中/死亡反馈可辨识，不互相遮挡 | | |
| D2 | 12v12 | 血条和选择圈仍可读 | | |
| D3 | 30v30 | 特效不遮挡核心信息，低优先级特效被淘汰 | | |
| D4 | 地面打空中 | 弹道方向和命中清晰 | | |
| D5 | 建筑被攻击 | 建筑 damaged VFX 明显不同于单位命中 | | |

### E. Fog / Terrain 验收

| # | 操作 | SC1 参考行为 | 评分 1-5 | 备注 |
|---|------|------------|---------|------|
| E1 | 未探索黑区 | 纯黑，单位完全不可见 | | |
| E2 | 探索后 shroud | 深灰暗，可见地形轮廓但无单位 | | |
| E3 | 可见区 | 完全清晰，无残留雾 | | |
| E4 | debug elevation off/on | 默认关闭，按 ⛏ Elev 开启后等高线出现 | | |

### F. 相机手感验收

| # | 操作 | SC1 参考行为 | 评分 1-5 | 备注 |
|---|------|------------|---------|------|
| F1 | 键盘平移速度 | 主观感觉稳定，不随 zoom 突变 | | |
| F2 | 边缘滚动 | 渐进加速，不突然跳速 | | |
| F3 | zoom 预设 | gameplay/inspection/debug 三档，默认 gameplay | | |

### 评分汇总

将每项分数记录到 `docs/reports/godot-sc1-feel-gap-report.md` 对应行。

## 操作手感 P1 自动门禁

先运行行为与契约测试：

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_operation_feel.gd
python3 -m pytest tests/godot/test_operation_feel_contract.py -q
```

期望结果：headless 行为测试全部通过；点选矩阵至少 95%，框选矩阵至少 95%，双分辨率可见世界宽度误差小于 2%。

需要采集真实对局数据时，在 `project.godot` 中临时设置：

```ini
[debug]
feel_metrics_enabled=true
```

运行结束后检查 Godot 用户目录中的 `feel_metrics.jsonl`。验收后恢复为 `false`，避免正式运行持续写盘。人工步骤和评分表见 `docs/reports/godot-operation-feel-qa-2026-07.md`。

```
| 评分项 | 得分 | 备注 |
|--------|------|------|
| camera pan stability | | |
| camera edge scroll | | |
| zoom readability | | |
| click selection accuracy | | |
| box selection accuracy | | |
| right-click acknowledgement | | |
| control group recall | | |
| unit movement readability | | |
| basic combat readability | | |
| building footprint clarity | | |
```
