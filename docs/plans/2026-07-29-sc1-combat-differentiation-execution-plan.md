# SC1 战斗差异化分步执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `systematic-debugging`, `test-driven-development`, `godot-specialist`, and `balance-check` while implementing this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 12 个三族代表单位建立一条由 SimCore 权威战斗事件驱动、正式对局与 Test Mode 共用、接近 SC1 规则和表现的完整战斗差异化链路。

**Architecture:** SimCore 负责武器、命中、护盾、溅射、弹射和死亡等战斗事实，通过 protobuf `CombatEvent` 传输；Godot 根据 `weapon_id` 将事实映射为攻击动画、弹道、命中、护盾和死亡表现。正式对局不显示显式克制提示，Test Mode 在相同事件链路外增加诊断面板。

**Tech Stack:** Python 3.11、protobuf/gRPC、SimCore deterministic tick、Godot 4.x typed GDScript、JSON catalogs、pytest、Godot headless tests。

## 执行入口

交给其他模型时，将本文件路径作为唯一任务入口，并要求执行模型遵守以下顺序：

1. 先阅读仓库根目录 `AGENTS.md`、本文件的“已冻结的产品决策”和“执行纪律”。
2. 只领取一个未完成 Task；不得一次实现多个 Gate 之后的内容。
3. 开始 Task 前运行其失败测试，完成后运行该 Task 的回归命令并更新 checkbox、QA 证据和提交。
4. 到达 G0-G7 任一 Gate 时先核对停止条件；未通过不得继续下一阶段。
5. 修改跨层契约时按 `Proto -> SimCore -> Transport -> Godot` 顺序落地，禁止在 Godot 先猜测尚未存在的字段。
6. 不确定 SC1 数值、武器行为或动画时回到 Task 1A 的 DAT/OpenBW 审计，不得凭记忆补值。
7. 每个执行回合的输出必须包含：完成的 checkbox、修改文件、测试命令与结果、未解决风险、下一 Task。

---

## 0. 已冻结的产品决策

以下决策已经由用户确认，执行模型不得自行扩大或改变：

1. 目标优先级是 **SC1 复刻优先**，不是重新设计一套克制系统。
2. 首轮只覆盖 12 个代表单位：
   - Terran：Marine、Firebat、Vulture、Tank。
   - Zerg：Zergling、Hydralisk、Mutalisk、Ultralisk。
   - Protoss：Zealot、Dragoon、Templar（High Templar）、Reaver。
3. 正式对局与 Test Mode 使用同一套武器表现配置和事件消费逻辑。
4. 正式对局只通过攻击节奏、动画、弹道、命中和实际伤害表达克制。
5. 武器类型、护甲类型、倍率和公式只在 Test Mode 诊断层显示。
6. SimCore 不允许引用纹理路径、Godot scene 或 `vfx_profile`。
7. Godot 不允许根据 HP 差猜测权威攻击者、武器类型或伤害倍率。
8. 本轮不扩展第 13 个单位，不重做 AI，不重构整个 `game_view.gd`。

## 1. 当前基线与已知根因

当前项目已经有：

- `simcore/data/unit_stats.json`：43 个单位的基础武器和护甲数据。
- `data/combat.json`：`normal / explosive / concussive` 伤害矩阵。
- `simcore/rules.py`：伤害、护盾、部分溅射和冷却结算。
- `simcore/projectile.py`：未与主战斗武器完整接通的旧 projectile entity 系统。
- `simcore/events.py`：仅保存在 replay snapshot 中的通用事件字典。
- `godot/scripts/combat_visual_controller.gd`：根据状态差推断战斗事件。
- `godot/scripts/vfx_manager.gd`：profile 驱动的基础 VFX。
- `godot/resources/vfx/vfx_catalog.json`：粗粒度种族/武器 profile。
- `godot/resources/sprite_frames_config.json`：12 个目标单位均有正式动画配置。

必须先处理的偏差：

- `CombatVisualController` 读取 `attack_cooldown`，SimCore 实际使用 `cooldown_timer`。
- `CombatVisualController` 读取 `shield`，当前单位状态主要使用 `shields`。
- gRPC `GameStateSnapshot` 没有携带 `events_this_tick`，HTTP/Godot 收不到权威战斗事件。
- `game_view.gd` 和 `CombatVisualController` 都在做 HP delta/VFX，存在重复触发风险。
- `simcore/engine.py`、HTTP gateway 和 Godot `poll_interval` 对应 10 TPS，但 `grpc_client.py`、旧 `py_bridge.py`、`victory_screen.gd` 和 `unit_stats.json._meta` 使用 20；现有 cooldown 和时长显示没有单一时钟真值。
- `tools/mpq/StarDat_extracted/arr/` 当前没有 `weapons.dat`，现有 12 单位伤害、hit count、弹道和 splash 参数缺少本地原始数据证据。
- `tools/mpq/sc1_dat_chain.py` 的硬编码 `UNIT_NAMES` 只服务资源链路，不得直接当作 combat unit ID 真值；combat audit 必须从 `stat_txt.tbl + units.dat` 重新核对。
- Vulture 当前映射 `terran_ballistic`，不能表达榴弹武器。
- Hydralisk 当前映射 `zerg_acid`，不能表达针刺弹道。
- Mutalisk 当前没有 Glave Wurm 三段弹射表现。
- Zealot 当前总伤害被当成单次命中，缺少双刃命中节奏。
- Reaver Scarab、Psionic Storm 虽有规则雏形，但没有权威视觉事件闭环。

## 2. 首轮单位表现矩阵

以下 `weapon_id` 是跨层稳定语义 ID。SimCore 和 Godot 可以分别维护 mechanics/visual catalog，但必须由测试保证 ID 对齐。

| Unit | weapon_id | 规则类型 | 正式对局视觉要求 | Test Mode 诊断 |
|---|---|---|---|---|
| Marine | `terran_c10_rifle` | normal、hitscan | 枪口闪光、短曳光、金属命中 | normal 对三类护甲均 100% |
| Firebat | `terran_flame_thrower` | concussive、近距扇形溅射 | 双股短火焰、地面余焰、轻型目标明显受创 | light/medium/heavy = 100/50/25% |
| Vulture | `terran_fragmentation_grenade` | concussive、projectile | 榴弹发射、抛射轨迹、小爆点 | 对 light 优势、对 heavy 劣势 |
| Tank | `terran_arclite_cannon` | explosive、projectile | 炮口后坐、炮弹、重爆炸；Siege 状态使用更大 profile | light/medium/heavy = 50/75/100% |
| Zergling | `zerg_claws` | normal、melee | 扑咬/爪击、短受击闪 | normal 100% |
| Hydralisk | `zerg_needle_spines` | explosive、projectile | 针刺发射、窄弹道、生物命中 | 对 heavy 优势 |
| Mutalisk | `zerg_glave_wurm` | normal、chain projectile | 首次命中后两次可见弹射，轨迹逐段变弱 | chain 0/1/2 与 1、1/3、1/9 |
| Ultralisk | `zerg_kaiser_blades` | normal、melee | 大范围双刃挥击、强命中震动，不生成弹道 | normal 100% |
| Zealot | `protoss_psi_blades` | normal、dual melee | 同一攻击周期内两次灵能刃命中 | 两个 hit，伤害合计与 stats 一致 |
| Dragoon | `protoss_phase_disruptor` | explosive、projectile | 蓝白能量球、护盾涟漪、机体命中闪 | explosive 倍率和 shield/health 拆分 |
| Templar | `protoss_psionic_storm` | spell、area periodic | 施法动作、持续风暴、逐 tick 命中 | 半径、持续时间、每 tick 实际伤害 |
| Reaver | `protoss_scarab` | explosive、tracking+splash | Scarab 实体移动、爆炸、分层溅射 | ammo、主目标、splash fraction |

## 3. 目标文件结构

### 新增

- `docs/architecture/adr-combat-visual-events.md`
  - 固化战斗事实和表现数据的所有权边界。
- `data/combat/sc1_representative_reference.json`
  - 从本地合法 MPQ 中导出的 12 单位/武器结构化参考值，不包含原始商业二进制资源。
- `data/combat/weapons.json`
  - 12 个语义武器的 mechanics catalog。
- `scripts/audit_sc1_combat_data.py`
  - 使用 PyMS 读取 `units.dat/weapons.dat` 并生成可复核差异报告。
- `simcore/combat_events.py`
  - 事件常量、构造器、校验和确定性 event ID。
- `simcore/combat_resolution.py`
  - melee/hitscan/projectile 共用的权威命中、护盾、护甲、溅射和击杀结算。
- `godot/resources/vfx/weapon_visual_catalog.json`
  - `weapon_id -> animation/projectile/impact/audio` 映射。
- `tests/proto/test_combat_event_proto.py`
  - protobuf schema 和序列化回归。
- `tests/simcore/test_combat_event_emission.py`
  - 攻击、命中、护盾、死亡事件。
- `tests/simcore/test_combat_event_transport.py`
  - engine -> gRPC -> client dict 完整性。
- `tests/simcore/test_sc1_representative_weapons.py`
  - 12 单位 mechanics 和克制矩阵。
- `tests/simcore/test_projectile_combat_integration.py`
  - 发射时不提前扣血、到达时统一结算、事件与状态一致。
- `tests/tools/test_sc1_combat_dat_audit.py`
  - DAT 映射、字段导出、时钟换算和 12 单位覆盖率。
- `tests/godot/test_weapon_visual_catalog.py`
  - mechanics/visual/presentation 三方 ID 对齐。
- `godot/scripts/test_combat_event_pipeline.gd`
  - Godot headless 事件消费测试。
- `godot/scripts/test_sc1_combat_slice.gd`
  - 12 单位 Test Mode fixture 与 VFX 测试。
- `docs/reports/sc1-combat-differentiation-qa.md`
  - 自动和人工验收记录。

### 修改

- `proto/state.proto`
- `tools/mpq/extract_dat.py`
- `simcore/engine.py`
- `simcore/rules.py`
- `simcore/projectile.py`
- `simcore/spells.py`
- `simcore/grpc_server.py`
- `simcore/grpc_client.py`
- `simcore/data/unit_stats.json`
- `godot/scripts/grpc_bridge.gd`
- `godot/scripts/combat_visual_controller.gd`
- `godot/scripts/vfx_manager.gd`
- `godot/scripts/game_view.gd`
- `godot/scripts/test_mode_gallery.gd`
- `godot/scripts/sprite_loader.gd`
- `godot/resources/vfx/vfx_catalog.json`
- `godot/resources/presentation_manifest.json`
- `godot/resources/unit_type_catalog.json`
- `godot/resources/sprite_frames_config.json`
- `docs/godot_verification_guide.md`

### 生成文件

执行 `make proto` 后更新：

- `simcore/proto_out/proto/state_pb2.py`
- `simcore/proto_out/proto/service_pb2.py`
- `simcore/proto_out/proto/service_pb2_grpc.py`

不要手工编辑生成文件。

## 4. 执行纪律

1. 每个 Task 必须按“失败测试 -> 最小实现 -> 通过测试 -> 小提交”执行。
2. 不得使用 `git reset --hard`、`git checkout --` 或删除用户现有修改。
3. 当前工作区可能包含未提交的 Godot 手感改动和 replay 输出。执行前必须隔离分支或 worktree。
4. `harness/output/replays/*.jsonl` 不属于本计划，不得加入提交。
5. 原始 SC1 商业资源不得新增到 Git 跟踪；只提交已有合法资源的配置、测试和校验记录。
6. 每个 Task 完成后更新本文 checkbox 和 QA 报告，不得最后一次性补状态。
7. 任一完整测试失败时先定位根因，不得通过放宽断言或删除测试绕过。
8. `tools/mpq/StarDat_extracted/**/*.dat` 是本地输入，不加入 Git；只提交派生 JSON、审计脚本和报告。

---

### Task 0：建立可恢复基线

**Files:**
- Read: `docs/plans/2026-07-21-godot-operation-feel-iteration-plan.md`
- Read: `docs/reports/godot-operation-feel-qa-2026-07.md`
- Create: `docs/reports/sc1-combat-differentiation-qa.md`

- [ ] **Step 1：检查工作区和基线提交**

Run:

```bash
git status --short
git log -5 --oneline
test -z "$(git status --porcelain --untracked-files=all)"
```

Expected:

- 明确记录所有已有修改。
- 不把 `harness/output/replays/*.jsonl` 归入本任务。
- 最后一条命令必须退出 0；若工作区不干净，先让仓库所有者提交或使用独立 worktree，执行模型不得自行 reset/stash。
- 如果操作手感 P0/P1 尚未形成可恢复提交，先让仓库所有者处理。

- [ ] **Step 2：建立独立执行分支**

Run:

```bash
git switch -c codex/sc1-combat-differentiation
```

Expected: 当前分支为 `codex/sc1-combat-differentiation`。

- [ ] **Step 3：运行基线测试**

Run:

```bash
python3 -m pytest tests/simcore/test_combat.py tests/simcore/test_splash_damage.py tests/godot/test_vfx_profiles.py -q
python3 scripts/verify_presentation_scene.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd
```

Expected: 全部 PASS。若失败，将失败命令和错误原文记录到 QA 报告后停止扩展。

- [ ] **Step 4：写入 QA 基线**

`docs/reports/sc1-combat-differentiation-qa.md` 至少包含：

```markdown
# SC1 Combat Differentiation QA

## Baseline
- Commit:
- Godot version:
- SimCore combat tests:
- VFX profile tests:
- Presentation verification:

## Automated Gates
| Gate | Target | Result | Status |
|---|---:|---:|---|
| CombatEvent transport | 100% fields preserved | pending | PENDING |
| 12-unit weapon mapping | 12/12 | pending | PENDING |
| Counter matrix | exact | pending | PENDING |
| Godot event pipeline | all event types | pending | PENDING |
| 30v30 VFX cap | no overflow | pending | PENDING |

## Manual Gates
| Unit | attack animation | projectile | impact | timing | verdict |
|---|---|---|---|---|---|
```

- [ ] **Step 5：提交基线报告**

```bash
git add docs/reports/sc1-combat-differentiation-qa.md
git commit -m "docs: record SC1 combat differentiation baseline"
```

---

### Task 1：冻结战斗事件 ADR

**Files:**
- Create: `docs/architecture/adr-combat-visual-events.md`

- [ ] **Step 1：写 ADR**

ADR 必须明确：

```text
Decision:
- SimCore owns combat facts.
- Proto transports semantic CombatEvent records.
- Godot owns weapon_id -> visual mapping.
- Test Mode injects the same CombatEvent shape.
- HP-delta inference is migration fallback only.

Consequences:
- Protocol and replay snapshots grow.
- Event order must be deterministic.
- Godot visuals become replayable and testable.
- SimCore remains independent from Godot assets.
```

- [ ] **Step 2：检查架构边界**

Run:

```bash
make lint-arch
rg -n "res://|vfx_profile|Godot" simcore proto
```

Expected:

- `make lint-arch` PASS。
- 新增 SimCore/Proto 代码中不存在 Godot 资源引用。

- [ ] **Step 3：提交 ADR**

```bash
git add docs/architecture/adr-combat-visual-events.md
git commit -m "docs: define authoritative combat visual events"
```

---

### Task 1A：建立 SC1 DAT 战斗真值审计

**Files:**
- Modify: `tools/mpq/extract_dat.py`
- Create: `scripts/audit_sc1_combat_data.py`
- Create: `tests/tools/test_sc1_combat_dat_audit.py`
- Create: `data/combat/sc1_representative_reference.json`
- Create: `docs/reports/sc1-12-unit-combat-source-audit.md`

- [ ] **Step 1：写审计脚本的失败测试**

测试必须先断言以下行为：

```text
12 个 project unit name 都能唯一映射到 SC1 unit id
每个普通攻击单位能解析 ground_weapon/air_weapon id
weapons.dat 字段能导出为 JSON 数字或布尔值
damage_amount * damage_factor = total_base_damage
runtime_cooldown_ticks = max(1, round(sc1_cooldown_frames * sim_tick_rate / 23.81))
High Templar 没有普通武器时不得伪造 weapon DAT id
Psi Storm 必须从 weapons.dat 名称表唯一解析为 weapon id 84，并与 techdata id 19 交叉核对
输出按 project unit name 和 weapon id 稳定排序
```

测试不得复用 `tools/mpq/sc1_dat_chain.py::UNIT_NAMES` 作为断言真值。单位名应从 `rez/stat_txt.tbl` 的 unit string 顺序读取，去掉 race 前缀、控制码和显示标记后，再通过审计脚本内的显式 alias 表匹配；匹配为 0 个或多个都必须失败。

- [ ] **Step 2：确认失败**

```bash
python3 -m pytest tests/tools/test_sc1_combat_dat_audit.py -q
```

Expected: FAIL，原因是审计脚本和 reference JSON 尚不存在。

- [ ] **Step 3：补齐本地提取项**

在 `tools/mpq/extract_dat.py::FILES` 增加：

```python
"arr\\weapons.dat",
"arr\\techdata.dat",
"scripts\\iscript.bin",
```

然后运行：

```bash
python3 tools/mpq/extract_dat.py
test -s tools/mpq/StarDat_extracted/arr/weapons.dat
test -s tools/mpq/StarDat_extracted/arr/techdata.dat
test -s tools/mpq/StarDat_extracted/scripts/iscript.bin
```

Expected: 三个文件均非空。若本地 `/Users/yuyou/code/StarCraft/StarDat.mpq` 不存在或提取失败，将命令、MPQ SHA-256 和错误写入 source audit，标记 `SOURCE_BLOCKED` 并停止 Task 2；不得改用模型记忆填数据。

- [ ] **Step 4：实现结构化审计器**

`scripts/audit_sc1_combat_data.py` 必须：

1. 通过 `tools/mpq/PyMS/PyMS/FileFormats/DAT/UnitsDAT.py` 和 `WeaponsDAT.py` 加载 DAT，不手写列偏移。
2. 从 `stat_txt.tbl` 解析 unit display names，输出最终使用的 `project_name -> sc1_unit_id` 映射。
3. 对普通武器导出：

```text
unit_id
unit_size_code
armor_type
base_armor
ground_weapon_dat_id
air_weapon_dat_id
max_ground_hits
max_air_hits
weapon_dat_id
damage_amount
damage_factor
total_base_damage
damage_bonus
weapon_cooldown_frames
runtime_cooldown_ticks
attack_launch_offset_frames
launch_delay_ticks
weapon_type_code
weapon_type
target_flags
minimum_range
maximum_range
graphics_flingy_id
weapon_behavior
explosion_type
inner_splash_range
medium_splash_range
outer_splash_range
```

4. 从 `simcore.engine.SimCore.tick_rate` 读取当前默认值；当前预期是 `10.0`。JSON 同时保留 `sc1_logic_fps: 23.81` 和换算公式，禁止继续沿用 `unit_stats.json` 中未经证明的 `/3` 公式。
5. 对 Templar 输出 `ordinary_weapon: null`，同时输出独立 `spell_weapon` 对象：`weapon_dat_id: 84`、`techdata_id: 19`、DAT 数值字段及 `behavior_source: "weapons_dat+techdata_dat+iscript+openbw"`。不能把 spell 塞进 High Templar 的普通 ground/air weapon 字段，也不能因其没有普通攻击而丢弃 Psi Storm 的 weapon DAT 记录。
6. `--check` 模式只比较生成结果与已提交 JSON，不写文件；差异时返回非零。
7. 原始 DAT、TBL、BIN 路径和内容不得进入 Git，只允许提交派生数值和 SHA-256。

Run:

```bash
PYTHONPATH=tools/mpq/PyMS python3 scripts/audit_sc1_combat_data.py \
  --dat-root tools/mpq/StarDat_extracted \
  --output data/combat/sc1_representative_reference.json \
  --report docs/reports/sc1-12-unit-combat-source-audit.md
```

- [ ] **Step 5：逐项裁决现有数据偏差**

报告必须给出 12 行主表，列出：

```text
project unit
SC1 unit id
SC1 weapon id/name
current total damage
SC1 total damage
current cooldown ticks
converted cooldown ticks
current hit count
SC1 damage factor
current delivery/splash
SC1 behavior/explosion
current armor type
SC1 unit size
resolution
```

裁决规则固定如下：

- DAT 原始字段优先于 Wiki 和记忆值。
- `damage_factor > 1` 表示一次攻击周期的多 hit；catalog 保存 `damage_per_hit` 和 `hit_count`，单位 stats 的 `attack_*` 保存总基础伤害。
- runtime cooldown 使用审计器换算值，不改全局 engine tick rate。
- `unit_stats.json.armor_type` 必须由 `units.dat` unit size 映射为 `light/medium/heavy`，不得沿用基于视觉体积的分类；例如 Zealot 的视觉体积不能作为 heavy 判据。
- delivery、chain、splash 或 spell 行为无法仅由 DAT 唯一确定时，使用本地 `iscript.bin` 和 OpenBW 代码语义交叉核对；OpenBW 基线固定为 commit `8265ec449b903e0752060a00ed5f930a3656bf00`，报告记录函数名和源码行附近的稳定语义，不得只写仓库首页或凭记忆猜测。
- 本轮只裁决 12 个单位，不顺手重写其余 31 个单位。

- [ ] **Step 6：运行稳定性测试**

```bash
python3 -m pytest tests/tools/test_sc1_combat_dat_audit.py -q
PYTHONPATH=tools/mpq/PyMS python3 scripts/audit_sc1_combat_data.py \
  --dat-root tools/mpq/StarDat_extracted \
  --output data/combat/sc1_representative_reference.json \
  --report docs/reports/sc1-12-unit-combat-source-audit.md \
  --check
```

Expected: PASS；第二次运行无 diff。审计报告不得存在 `UNKNOWN`、重复 unit ID 或未裁决字段。

- [ ] **Step 7：提交派生结果，不提交原始二进制**

```bash
git add tools/mpq/extract_dat.py scripts/audit_sc1_combat_data.py tests/tools/test_sc1_combat_dat_audit.py data/combat/sc1_representative_reference.json docs/reports/sc1-12-unit-combat-source-audit.md
test -z "$(git diff --cached --name-only | rg 'StarDat_extracted|\\.dat$|\\.bin$')"
git commit -m "test: audit representative combat data from SC1 DAT"
```

---

### Task 2：建立语义武器目录

**Files:**
- Read: `data/combat/sc1_representative_reference.json`
- Read: `docs/reports/sc1-12-unit-combat-source-audit.md`
- Create: `data/combat/weapons.json`
- Modify: `simcore/data/unit_stats.json`
- Create: `tests/simcore/test_sc1_representative_weapons.py`

- [ ] **Step 1：写失败测试**

测试必须校验 12 个 canonical unit 对应以下 ID：

```python
EXPECTED_WEAPONS = {
    "Marine": "terran_c10_rifle",
    "Firebat": "terran_flame_thrower",
    "Vulture": "terran_fragmentation_grenade",
    "Tank": "terran_arclite_cannon",
    "Zergling": "zerg_claws",
    "Hydralisk": "zerg_needle_spines",
    "Mutalisk": "zerg_glave_wurm",
    "Ultralisk": "zerg_kaiser_blades",
    "Zealot": "protoss_psi_blades",
    "Dragoon": "protoss_phase_disruptor",
    "Templar": "protoss_psionic_storm",
    "Reaver": "protoss_scarab",
}
```

同时校验：

```python
VALID_DELIVERY = {"melee", "hitscan", "projectile", "chain", "area_periodic", "tracking"}
VALID_DAMAGE_TYPES = {"normal", "explosive", "concussive", "spells"}
```

12 单位的 `armor_type` 也必须与 `sc1_representative_reference.json` 的 unit size 映射一致。

每个武器必须有：

```text
weapon_id
source_weapon_dat_id
damage_per_hit
hit_count
total_base_damage
damage_type
delivery_type
can_target_ground
can_target_air
cooldown_ticks
launch_delay_ticks
projectile_speed_world_per_tick
max_lifetime_ticks
splash_profile
chain_fractions
chain_radius_world
```

`source_weapon_dat_id` 对 Psionic Storm 为 `84`，并额外保存 `source_techdata_id: 19`；`projectile_speed_world_per_tick` 对 melee/hitscan/area 为 `0`。测试同时比较 `sc1_representative_reference.json`，确保 damage、hit count、cooldown 和 target flags 没有被二次手填覆盖。

- [ ] **Step 2：运行并确认失败**

```bash
python3 -m pytest tests/simcore/test_sc1_representative_weapons.py -q
```

Expected: FAIL，原因是 `data/combat/weapons.json` 不存在或 unit stats 缺 `weapon_id_ground`。

- [ ] **Step 3：创建 mechanics catalog**

以下两个条目的行为字段必须为；所有数值字段从 Task 1A reference JSON 逐字段复制：

```json
{
  "zerg_glave_wurm": {
    "delivery_type": "chain",
    "splash_profile": "none",
    "chain_fractions": [1.0, 0.333333, 0.111111]
  },
  "protoss_psi_blades": {
    "delivery_type": "melee",
    "splash_profile": "none",
    "chain_fractions": []
  }
}
```

`hit_count`、damage、cooldown、range、target flags 和 projectile 参数必须来自 Task 1A。Mutalisk 的 chain fraction 以及 delivery/splash 语义必须由 Task 1A 的 OpenBW/iscript 交叉核对结论支持；若结论不同，以审计报告为准并同步修正测试。其余 10 个武器使用同一固定 schema，不增加 Godot 资源字段。

- [ ] **Step 4：为 12 单位增加 weapon ID**

`unit_stats.json` 中：

- 普通单位增加 `weapon_id_ground`。
- Marine、Hydralisk、Mutalisk、Dragoon 同时增加 `weapon_id_air`。
- Templar 增加 `spell_weapon_id: "protoss_psionic_storm"`，保持普通攻击为 `none`。
- 将 12 单位的 `attack_*`、`cooldown_*`、weapon type 和 `armor_type` 更新为 Task 1A 已裁决值；`attack_*` 保持一次完整攻击周期总伤害。
- 将 `_meta.engine_tps` 改为实际 `SimCore.tick_rate`，并将公式写为 `round(sc1_frames * sim_tick_rate / 23.81)`；不得只改数字而保留错误元数据。

- [ ] **Step 5：运行测试**

```bash
python3 -m pytest tests/simcore/test_sc1_representative_weapons.py tests/simcore/test_combat.py -q
```

Expected: PASS，且原有 combat tests 无回归。

- [ ] **Step 6：执行 balance-check**

输出至少包含：

- normal/explosive/concussive 对 light/medium/heavy 的倍率。
- 12 单位基础 DPS。
- Mutalisk 三段总理论伤害。
- Zealot 双 hit 合计伤害。
- Tank/Firebat/Reaver splash 的 inner/mid/outer。

只允许修改 Task 1A 报告已裁决的 12 单位基础伤害和 cooldown。每一项 runtime 变化都写入 QA 报告；其余单位和全局 tick rate 不变。

- [ ] **Step 7：提交**

```bash
git add data/combat/weapons.json simcore/data/unit_stats.json tests/simcore/test_sc1_representative_weapons.py docs/reports/sc1-combat-differentiation-qa.md
git commit -m "feat: define semantic weapons for representative units"
```

---

### Task 3：增加 protobuf CombatEvent

**Files:**
- Modify: `proto/state.proto`
- Create: `tests/proto/test_combat_event_proto.py`
- Regenerate: `simcore/proto_out/proto/*.py`

- [ ] **Step 1：写失败测试**

测试构造并 round-trip 一个事件：

```python
event = state_pb2.CombatEvent(
    event_id="42:3",
    tick=42,
    event_type=state_pb2.IMPACT_RESOLVED,
    attacker_id="marine_1",
    target_id="zergling_1",
    weapon_id="terran_c10_rifle",
    source_x=10.0,
    source_y=12.0,
    target_x=14.0,
    target_y=12.0,
    delivery_type="hitscan",
    weapon_type="normal",
    armor_type="light",
    base_damage=6.0,
    final_damage=6.0,
    damage_multiplier=1.0,
    health_damage=6.0,
    armor_value=0.0,
    shield_armor_value=0.0,
    hit_index=0,
    hit_count=1,
)
snapshot = state_pb2.GameStateSnapshot(combat_events=[event])
decoded = state_pb2.GameStateSnapshot.FromString(snapshot.SerializeToString())
assert decoded.combat_events[0].weapon_id == "terran_c10_rifle"
assert decoded.combat_events[0].hit_count == 1
```

- [ ] **Step 2：确认失败**

```bash
python3 -m pytest tests/proto/test_combat_event_proto.py -q
```

Expected: FAIL，`CombatEvent` 未定义。

- [ ] **Step 3：修改 schema**

在 `state.proto` 增加：

```proto
enum CombatEventType {
  COMBAT_EVENT_UNSPECIFIED = 0;
  ATTACK_STARTED = 1;
  PROJECTILE_SPAWNED = 2;
  IMPACT_RESOLVED = 3;
  UNIT_DESTROYED = 4;
  SPELL_RESOLVED = 5;
}

message CombatEvent {
  string event_id = 1;
  int32 tick = 2;
  CombatEventType event_type = 3;
  string attacker_id = 4;
  string target_id = 5;
  string weapon_id = 6;
  float source_x = 7;
  float source_y = 8;
  float target_x = 9;
  float target_y = 10;
  string delivery_type = 11;
  string weapon_type = 12;
  string armor_type = 13;
  float base_damage = 14;
  float final_damage = 15;
  float damage_multiplier = 16;
  float shield_damage = 17;
  float health_damage = 18;
  string projectile_id = 19;
  int32 chain_index = 20;
  bool is_splash = 21;
  float splash_fraction = 22;
  bool killed = 23;
  bool missed = 24;
  float armor_value = 25;
  float shield_armor_value = 26;
  int32 hit_index = 27;
  int32 hit_count = 28;
}
```

在 `GameStateSnapshot` 使用新 field number：

```proto
repeated CombatEvent combat_events = 11;
```

不得重用现有 1-10。

- [ ] **Step 4：生成并测试**

```bash
make proto
python3 -m pytest tests/proto/test_combat_event_proto.py -q
```

Expected: PASS。

- [ ] **Step 5：提交**

```bash
git add proto/state.proto simcore/proto_out/proto/state_pb2.py simcore/proto_out/proto/service_pb2.py simcore/proto_out/proto/service_pb2_grpc.py tests/proto/test_combat_event_proto.py
git commit -m "feat: add combat event protobuf contract"
```

---

### Task 4：让 SimCore 在结算点产生权威事件

**Files:**
- Create: `simcore/combat_events.py`
- Modify: `simcore/rules.py`
- Modify: `simcore/engine.py`
- Create: `tests/simcore/test_combat_event_emission.py`

- [ ] **Step 1：写事件构造器失败测试**

要求：

```python
event = make_combat_event(
    tick=7,
    sequence=2,
    event_type="impact_resolved",
    attacker=attacker,
    target=target,
    weapon_id="terran_c10_rifle",
    delivery_type="hitscan",
    weapon_type="normal",
    base_damage=6,
    final_damage=6,
    damage_multiplier=1.0,
    shield_damage=0,
    health_damage=6,
    armor_value=0,
    shield_armor_value=0,
    hit_index=0,
    hit_count=1,
)
assert event["event_id"] == "7:2"
assert event["source_x"] == attacker["pos_x"]
assert event["target_x"] == target["pos_x"]
```

- [ ] **Step 2：写战斗事件失败测试**

至少覆盖：

1. Marine 开火产生 `attack_started` 和 `impact_resolved`。
2. 高地 miss 产生 `missed=true` 且无 health damage。
3. Dragoon 命中 Protoss 目标，shield/health 分开。
4. 击杀产生 `unit_destroyed`。
5. 一个 tick 内事件 ID 唯一且顺序稳定。

- [ ] **Step 3：确认失败**

```bash
python3 -m pytest tests/simcore/test_combat_event_emission.py -q
```

Expected: FAIL，缺少事件输出参数或构造器。

- [ ] **Step 4：实现构造器**

`simcore/combat_events.py` 提供：

```python
ATTACK_STARTED = "attack_started"
PROJECTILE_SPAWNED = "projectile_spawned"
IMPACT_RESOLVED = "impact_resolved"
UNIT_DESTROYED = "unit_destroyed"
SPELL_RESOLVED = "spell_resolved"

def make_combat_event(*, tick: int, sequence: int, event_type: str, **fields) -> dict:
    return {"event_id": f"{tick}:{sequence}", "tick": tick, "event_type": event_type, **fields}

def append_combat_event(
    events: list[dict],
    *,
    tick: int,
    event_type: str,
    **fields,
) -> dict:
    event = make_combat_event(
        tick=tick,
        sequence=len(events),
        event_type=event_type,
        **fields,
    )
    validate_combat_event(event)
    events.append(event)
    return event
```

同时提供 `validate_combat_event(event)`，拒绝未知 event type、空 `weapon_id`（death 事件除外）、负 `chain_index`、`hit_count < 1` 或 `hit_index >= hit_count`。所有规则、projectile 和 spell 路径只能通过 `append_combat_event()` 写列表，禁止各模块维护自己的 sequence counter。

- [ ] **Step 5：从真实结算点发出事件**

给 `resolve_combat` 增加可选参数：

```python
combat_events: list[dict] | None = None
```

要求：

- 只有通过 cooldown gate 且进入射程时产生 `attack_started`。
- 命中/未命中判定后产生 `impact_resolved`。
- 使用实际 impact 结算前的 target snapshot 填写 armor、shield 和位置；projectile 不得使用发射时防御值。
- `damage_multiplier` 只表示 weapon type 对 target armor type 的 SC1 size multiplier（如 0.25/0.5/0.75/1.0），不是 `final_damage / base_damage`；shield、armor 和剩余 HP 会让后者失真。
- 每个 splash target 独立产生 impact event。
- 事件列表为空时保持现有调用兼容。
- 同一 tick 的 melee、hitscan、projectile 和 spell 共享一个 append-only 列表；不得在各阶段重新从 sequence 0 开始。

- [ ] **Step 6：Engine 保存本 tick 事件**

`Engine` 增加：

```python
self._combat_events_this_tick: list[dict] = []

@property
def combat_events_this_tick(self) -> list[dict]:
    return [dict(event) for event in self._combat_events_this_tick]
```

每次 `step()` 开始清空，并使用以下完整调用传递事件列表，结束时保存。不要把事件塞入 immutable entity state。

```python
combat_events: list[dict] = []
entities, resources = resolve_combat(
    entities,
    temp_state.resources,
    other_cmds,
    self._tick,
    kill_feed=self.rule_engine.kill_feed,
    tile_map=self._tile_map,
    combat_events=combat_events,
)
```

本行赋值不能紧跟 `resolve_combat()`；必须放在 `process_spells()` 和 `process_projectiles()` 都执行完之后：

```python
self._combat_events_this_tick = [dict(event) for event in combat_events]
```

`step()` 即使发现游戏已 terminal，也要先清空 `_combat_events_this_tick`，防止 `Step` 重复返回上一 tick 的事件。通用 `events_this_tick` 与 `combat_events` 保持两个列表，不互相包装或复用 ID。

- [ ] **Step 7：运行测试**

```bash
python3 -m pytest tests/simcore/test_combat_event_emission.py tests/simcore/test_combat.py tests/simcore/test_splash_damage.py -q
```

Expected: PASS。

- [ ] **Step 8：提交**

```bash
git add simcore/combat_events.py simcore/rules.py simcore/engine.py tests/simcore/test_combat_event_emission.py
git commit -m "feat: emit authoritative combat events"
```

---

### Task 5：打通 gRPC、HTTP 和 replay

**Files:**
- Modify: `simcore/grpc_server.py`
- Modify: `simcore/grpc_client.py`
- Modify: `simcore/http_gateway.py`
- Modify: `simcore/replay.py`
- Modify: `godot/scripts/grpc_bridge.gd`
- Modify: `godot/scripts/py_bridge.py`
- Modify: `godot/scripts/victory_screen.gd`
- Create: `tests/simcore/test_combat_event_transport.py`
- Modify: `tests/integration/test_grpc.py`

- [ ] **Step 1：写失败测试**

测试必须经过真正 protobuf 转换：

```python
proto = SimCoreServicer._snapshot_dict_to_proto({
    "tick": 9,
    "entities": {},
    "combat_events": [{
        "event_id": "9:0",
        "tick": 9,
        "event_type": "impact_resolved",
        "attacker_id": "m1",
        "target_id": "z1",
        "weapon_id": "terran_c10_rifle",
        "source_x": 1.0,
        "source_y": 2.0,
        "target_x": 3.0,
        "target_y": 4.0,
        "delivery_type": "hitscan",
        "weapon_type": "normal",
        "armor_type": "light",
        "base_damage": 6.0,
        "final_damage": 6.0,
        "damage_multiplier": 1.0,
        "shield_damage": 0.0,
        "health_damage": 6.0,
        "projectile_id": "",
        "chain_index": 0,
        "is_splash": False,
        "splash_fraction": 1.0,
        "killed": False,
        "missed": False,
        "armor_value": 0.0,
        "shield_armor_value": 0.0,
        "hit_index": 0,
        "hit_count": 1,
    }],
})
decoded = SimCoreClient._snapshot_to_dict(proto)
assert decoded["combat_events"][0]["weapon_id"] == "terran_c10_rifle"
assert decoded["combat_events"][0]["hit_count"] == 1
```

- [ ] **Step 2：确认失败**

```bash
python3 -m pytest tests/simcore/test_combat_event_transport.py -q
```

Expected: FAIL，转换器丢失 `combat_events`。

- [ ] **Step 3：实现统一转换 helper**

避免在 `_state_to_snapshot` 和 `_snapshot_dict_to_proto` 复制字段映射。新增私有 helper：

```python
_EVENT_TYPE_TO_PROTO = {
    "attack_started": state_pb2.ATTACK_STARTED,
    "projectile_spawned": state_pb2.PROJECTILE_SPAWNED,
    "impact_resolved": state_pb2.IMPACT_RESOLVED,
    "unit_destroyed": state_pb2.UNIT_DESTROYED,
    "spell_resolved": state_pb2.SPELL_RESOLVED,
}

def _append_combat_events(proto_snapshot, events: list[dict]) -> None:
    for event in events:
        event_type = event["event_type"]
        if event_type not in _EVENT_TYPE_TO_PROTO:
            raise ValueError(f"Unknown combat event type: {event_type}")
        proto_snapshot.combat_events.add(
            event_id=event["event_id"],
            tick=int(event["tick"]),
            event_type=_EVENT_TYPE_TO_PROTO[event_type],
            attacker_id=event.get("attacker_id", ""),
            target_id=event.get("target_id", ""),
            weapon_id=event.get("weapon_id", ""),
            source_x=float(event.get("source_x", 0.0)),
            source_y=float(event.get("source_y", 0.0)),
            target_x=float(event.get("target_x", 0.0)),
            target_y=float(event.get("target_y", 0.0)),
            delivery_type=event.get("delivery_type", ""),
            weapon_type=event.get("weapon_type", ""),
            armor_type=event.get("armor_type", ""),
            base_damage=float(event.get("base_damage", 0.0)),
            final_damage=float(event.get("final_damage", 0.0)),
            damage_multiplier=float(event.get("damage_multiplier", 0.0)),
            shield_damage=float(event.get("shield_damage", 0.0)),
            health_damage=float(event.get("health_damage", 0.0)),
            projectile_id=event.get("projectile_id", ""),
            chain_index=int(event.get("chain_index", 0)),
            is_splash=bool(event.get("is_splash", False)),
            splash_fraction=float(event.get("splash_fraction", 1.0)),
            killed=bool(event.get("killed", False)),
            missed=bool(event.get("missed", False)),
            armor_value=float(event.get("armor_value", 0.0)),
            shield_armor_value=float(event.get("shield_armor_value", 0.0)),
            hit_index=int(event.get("hit_index", 0)),
            hit_count=int(event.get("hit_count", 1)),
        )
```

字符串 event type 映射到 protobuf enum；未知类型必须抛出 `ValueError`，不能静默降级。

- [ ] **Step 4：Step/GetState 行为**

- `Step` 返回 `engine.combat_events_this_tick`。
- `GetState` 返回空 combat event 列表，避免重复播放上一 tick。
- `StartGame` 返回空 combat event 列表。
- replay snapshot 保存 combat events；播放时保持原 event ID 和顺序。

- [ ] **Step 5：统一 10 TPS runtime contract**

- `SimCore`、`SimCoreClient.start_game()`、HTTP gateway、`py_bridge.py` 默认均为 `10.0`。
- `GrpcBridge.poll_interval=0.1`，start request 显式发送 `tick_rate=10.0`，不依赖 gateway fallback。
- snapshot config 必须回传本局实际 tick rate。
- `victory_screen.gd` 用 snapshot/config 的 tick rate 计算秒数，fallback 为 10，不再写死 `/20.0`。
- 增加测试扫描上述入口，任何默认值回到 20 都应失败。

- [ ] **Step 6：client dict 字段完整**

`SimCoreClient._snapshot_to_dict()` 输出：

```python
"combat_events": [
    {
        "event_id": e.event_id,
        "tick": e.tick,
        "event_type": state_pb2.CombatEventType.Name(e.event_type).lower(),
        "attacker_id": e.attacker_id,
        "target_id": e.target_id,
        "weapon_id": e.weapon_id,
        "source_x": e.source_x,
        "source_y": e.source_y,
        "target_x": e.target_x,
        "target_y": e.target_y,
        "delivery_type": e.delivery_type,
        "weapon_type": e.weapon_type,
        "armor_type": e.armor_type,
        "base_damage": e.base_damage,
        "final_damage": e.final_damage,
        "damage_multiplier": e.damage_multiplier,
        "shield_damage": e.shield_damage,
        "health_damage": e.health_damage,
        "projectile_id": e.projectile_id,
        "chain_index": e.chain_index,
        "is_splash": e.is_splash,
        "splash_fraction": e.splash_fraction,
        "killed": e.killed,
        "missed": e.missed,
        "armor_value": e.armor_value,
        "shield_armor_value": e.shield_armor_value,
        "hit_index": e.hit_index,
        "hit_count": e.hit_count,
    }
    for e in snapshot.combat_events
]
```

HTTP gateway 已透传 client dict，不在 gateway 重新解释事件。

- [ ] **Step 7：测试**

```bash
python3 -m pytest tests/simcore/test_combat_event_transport.py tests/integration/test_grpc.py -q -x
```

Expected: PASS。

- [ ] **Step 8：提交**

```bash
git add simcore/grpc_server.py simcore/grpc_client.py simcore/http_gateway.py simcore/replay.py godot/scripts/grpc_bridge.gd godot/scripts/py_bridge.py godot/scripts/victory_screen.gd tests/simcore/test_combat_event_transport.py tests/integration/test_grpc.py
git commit -m "feat: transport combat events to frontend and replay"
```

---

### Task 6：Godot 改为事件驱动的单一表现入口

**Files:**
- Modify: `godot/scripts/combat_visual_controller.gd`
- Modify: `godot/scripts/game_view.gd`
- Modify: `godot/scripts/vfx_manager.gd`
- Create: `godot/scripts/test_combat_event_pipeline.gd`
- Create: `tests/godot/test_combat_event_contract.py`

- [ ] **Step 1：写静态失败测试**

断言：

```python
assert 'state.get("combat_events", [])' in game_view_source
assert "process_combat_events" in controller_source
assert 'cur.get("attack_cooldown"' not in controller_source
assert 'cur.get("shield"' not in controller_source
```

- [ ] **Step 2：写 Godot headless 失败测试**

创建 `CombatVisualController` 和 fake VFX sink，输入：

```gdscript
{
    "event_id": "12:0",
    "tick": 12,
    "event_type": "impact_resolved",
    "attacker_id": "m1",
    "target_id": "z1",
    "weapon_id": "terran_c10_rifle",
    "source_x": 2.0,
    "source_y": 3.0,
    "target_x": 5.0,
    "target_y": 3.0,
    "delivery_type": "hitscan",
    "final_damage": 6.0,
}
```

断言 sink 恰好收到一次事件；重复输入同一 `event_id` 不得重播。

- [ ] **Step 3：确认失败**

```bash
python3 -m pytest tests/godot/test_combat_event_contract.py -q
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_combat_event_pipeline.gd
```

Expected: 两个测试至少一个 FAIL。

- [ ] **Step 4：重构 Controller**

公开入口：

```gdscript
func process_combat_events(events: Array) -> void
func current_action_for(entity_id: String) -> String
func clear_seen_events() -> void
```

内部：

- `_seen_event_ids` 防止 HTTP 重试或 replay seek 重复播放。
- `_seen_event_ids` 使用按 tick/event ID 淘汰的有界缓存，上限 4096；新对局和 replay seek 必须清空，长局不能无限增长。
- `attack_started` 设置短期 `attack` action。
- `projectile_spawned` 交给 VFXManager。
- `impact_resolved` 触发 hit/shield/splash。
- `unit_destroyed` 触发 death。
- 未知 event type 只 warning 一次。

- [ ] **Step 5：接入 game_view**

`_parse(state)` 在构建实体缓存后调用：

```gdscript
_combat_visual_controller.process_combat_events(state.get("combat_events", []))
```

`_unit_animation_key()` 优先读取：

```gdscript
var event_action := _combat_visual_controller.current_action_for(str(e.get("id", "")))
```

移除或 feature-flag 关闭 `game_view.gd` 中 `_prev_hp` 触发的 attack/hit VFX，确保一个真实命中只显示一次。

- [ ] **Step 6：测试**

```bash
python3 -m pytest tests/godot/test_combat_event_contract.py tests/godot/test_vfx_profiles.py -q
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_combat_event_pipeline.gd
```

Expected: PASS。

- [ ] **Step 7：提交**

```bash
git add godot/scripts/combat_visual_controller.gd godot/scripts/game_view.gd godot/scripts/vfx_manager.gd godot/scripts/test_combat_event_pipeline.gd tests/godot/test_combat_event_contract.py
git commit -m "feat: drive Godot combat visuals from authoritative events"
```

---

### Task 7：建立 weapon visual catalog

**Files:**
- Create: `godot/resources/vfx/weapon_visual_catalog.json`
- Modify: `godot/resources/vfx/vfx_catalog.json`
- Modify: `godot/resources/presentation_manifest.json`
- Modify: `godot/resources/unit_type_catalog.json`
- Create: `tests/godot/test_weapon_visual_catalog.py`

- [ ] **Step 1：写失败测试**

要求 mechanics catalog 的 12 个 `weapon_id` 全部存在 visual catalog，并包含：

```text
animation_action
launch_effect
projectile_style
impact_effect
shield_impact_effect
death_effect
audio_cue
priority
```

同时校验：

- `launch_effect/impact_effect/death_effect` 引用 `vfx_catalog.effects`。
- `presentation_manifest` 的 12 个单位引用正确 weapon ID。
- Templar 使用 `cast` animation，其他 11 个使用 `attack`。

- [ ] **Step 2：确认失败**

```bash
python3 -m pytest tests/godot/test_weapon_visual_catalog.py -q
```

Expected: FAIL，visual catalog 不存在。

- [ ] **Step 3：创建 12 武器视觉条目**

示例：

```json
{
  "terran_fragmentation_grenade": {
    "animation_action": "attack",
    "launch_effect": "vulture_grenade_launch",
    "projectile_style": "grenade_arc",
    "impact_effect": "small_concussive_burst",
    "shield_impact_effect": "shield_hit",
    "death_effect": "small_death_burst",
    "audio_cue": "VultureAttack",
    "priority": 2
  }
}
```

不得让 Marine、Vulture、Tank 共用同一个完整 profile；可共享底层 effect texture，但时长、轨迹、颜色和尺寸必须可区分。

- [ ] **Step 4：扩展 VFXManager**

新增：

```gdscript
func spawn_weapon_event(event: Dictionary, visual: Dictionary) -> void
```

按 `projectile_style` 分发：

```text
none
hitscan_tracer
flame_cone
grenade_arc
tank_shell
needle_spine
glave_chain
phase_orb
storm_area
scarab_tracking
melee_slash
heavy_melee_arc
```

旧 `vfx_profile` 保持 fallback，但 12 个首轮单位必须优先走 weapon catalog。

- [ ] **Step 5：测试**

```bash
python3 -m pytest tests/godot/test_weapon_visual_catalog.py tests/godot/test_vfx_profiles.py tests/godot/test_unit_type_catalog.py -q
```

Expected: PASS。

- [ ] **Step 6：提交**

```bash
git add godot/resources/vfx/weapon_visual_catalog.json godot/resources/vfx/vfx_catalog.json godot/resources/presentation_manifest.json godot/resources/unit_type_catalog.json godot/scripts/vfx_manager.gd tests/godot/test_weapon_visual_catalog.py
git commit -m "feat: add per-weapon SC1 visual profiles"
```

---

### Task 7A：统一权威 projectile 与 impact 结算

**Files:**
- Create: `simcore/combat_resolution.py`
- Modify: `simcore/rules.py`
- Modify: `simcore/projectile.py`
- Modify: `simcore/spells.py`
- Modify: `simcore/engine.py`
- Modify: `godot/scripts/game_view.gd`
- Create: `tests/simcore/test_projectile_combat_integration.py`
- Modify: `tests/simcore/test_combat_event_emission.py`
- Modify: `tests/simcore/test_sprint3.py`
- Modify: `tests/simcore/test_support_spells.py`
- Modify: `tests/godot/test_combat_event_contract.py`

- [ ] **Step 1：写“发射不扣血、命中才扣血”的失败测试**

至少覆盖：

```python
before_hp = entities[target_id]["health"]
after_launch, _ = resolve_combat(
    entities,
    resources,
    attack_commands,
    tick=10,
    combat_events=events,
)
assert after_launch[target_id]["health"] == before_hp
assert any(e["event_type"] == "projectile_spawned" for e in events)

after_impact = advance_until_projectile_resolves(after_launch, events)
assert after_impact[target_id]["health"] < before_hp
assert len([e for e in events if e["event_type"] == "impact_resolved"]) == 1
```

再覆盖：

1. melee/hitscan 在 scheduled launch tick 产生 impact，不创建 projectile entity。
2. `launch_delay_ticks > 0` 时，`attack_started` 先发生；scheduled launch tick 才产生 hitscan impact 或 `projectile_spawned`。
3. projectile 发射 tick 不扣血，到达 tick 才产生 `impact_resolved` 和可能的 `unit_destroyed`。
4. projectile 命中时使用“命中时目标”的 armor/shield/health，不使用发射时快照扣血。
5. 目标提前死亡或 projectile 超时，产生 `missed=true` 的 impact，伤害为 0。
6. 分别使用 `PYTHONHASHSEED=1` 和 `PYTHONHASHSEED=999` 运行同 seed/commands，命中结果、projectile ID 和 combat event ID 一致。
7. projectile/effect entity 不进入普通单位选择、fog 视野、minimap 和 Godot unit renderer。
8. 20 explosive 命中 30 shield 的 light 单位，只扣 20 shield，不先乘 0.5。
9. 20 explosive 命中 10 shield、0 armor 的 light 单位，扣 10 shield 和 5 health。
10. 20 concussive 命中 10 shield、0 armor 的 heavy 单位，扣 10 shield 和 2.5 health。

- [ ] **Step 2：确认失败**

```bash
python3 -m pytest tests/simcore/test_projectile_combat_integration.py tests/simcore/test_sprint3.py -q
python3 -m pytest tests/godot/test_combat_event_contract.py -q
```

Expected: FAIL；当前 `resolve_combat()` 会立即扣血，旧 `_next_proj_id` 也不是对局内确定性 ID。

- [ ] **Step 3：抽取唯一 damage/impact 入口**

`simcore/combat_resolution.py` 成为以下逻辑的唯一实现：

```python
def resolve_weapon_impact(
    entities: dict[str, dict],
    *,
    attacker_id: str,
    target_id: str,
    weapon: dict,
    tick: int,
    combat_events: list[dict],
    kill_feed: KillFeed,
    projectile_id: str = "",
    chain_index: int = 0,
    splash_fraction: float = 1.0,
    missed: bool = False,
) -> tuple[dict[str, dict], set[str]]:
    ...
```

要求：

- damage matrix、armor、shield-first、health、splash、kill feed 和 death event 只在这个模块处理。
- 结算顺序必须与 OpenBW `weapon_deal_damage()` 一致：先应用 chain/splash divisor，再扣 shield armor 并吸收 shield；只有剩余伤害进入 health，先扣 unit armor，再应用 explosive/concussive 对 unit size 的倍率。
- weapon type 对 unit size 的倍率不能作用于 shield。若 shield 全部吸收，本次 `health_damage=0`；若 shield 被打穿，只对穿透后的部分执行 unit armor 和 size multiplier。
- 每个 hit 单独执行上述流程，因此 Zealot/Firebat 的 armor 至少按 DAT `damage_factor` 对应的 hit 次数分别生效。SC1 最小伤害规则也必须在 shield 分支后执行，不能使用当前 `(base * multiplier) - armor` 的简化公式。
- 每个实际结算的 hit-target 对只产生一个 `impact_resolved`；dual hit 可以产生两个不同 `hit_index` 的 impact。每个死亡目标只产生一个 `unit_destroyed`。
- `final_damage = shield_damage + health_damage`，不得记录被目标剩余生命截断之前的理论伤害。
- `calculate_damage()` 和 `get_armor_type()` 从 `rules.py` 移到该模块；`rules.py` 通过 import 保持既有公共导入兼容。
- `KillFeed` 同时移到该模块，`rules.py` 只 re-export；避免 `combat_resolution.py <-> rules.py` 循环 import。
- splash 目标按 `(distance, entity_id)` 排序，之后才依次结算。

- [ ] **Step 4：把 projectile 改为确定性权威实体**

移除模块全局 `_next_proj_id`。`resolve_combat()` 在发射时生成：

```python
projectile_id = f"projectile:{tick}:{len(combat_events)}"
```

`create_projectile()` 必须显式接收并保存：

```text
id
entity_type = projectile
source_id
owner
target_id
weapon_id
delivery_type
weapon_type
base_damage
damage_per_hit
hit_count
projectile_speed_world_per_tick
max_lifetime_ticks
chain_index
chain_fractions
chain_radius_world
will_hit
pos_x / pos_y
last_target_x / last_target_y
age
```

不得再生成 `entity_type="effect"` 的 hit/fizz marker；视觉只由 CombatEvent 驱动。旧测试需要改成验证事件，而不是查找 effect marker。

- [ ] **Step 5：按 delivery 分流**

`resolve_combat()`：

- cooldown gate 通过时发出 `attack_started`，并在 attacker entity 写入确定性的 `pending_attack`（weapon ID、target ID、launch tick、hit roll）；不得在 windup tick 扣血。
- scheduled launch tick 到达后，`melee`、`hitscan` 调用 `resolve_weapon_impact()`；dual hit 按 reference 的 hit timing 调用两次，共用 attack cycle，事件 ID 不同。
- scheduled launch tick 到达后，`projectile`、`tracking`、`chain` 创建 projectile 并发出 `projectile_spawned`，该 tick 不调用 impact。
- `area_periodic`：只由 `process_spells()` 在实际 tick damage 点调用 impact。
- high-ground hit roll 只计算一次；projectile 保存 `will_hit`，到达时再发 missed/impact。
- 删除 `hash((tick, uid))` 命中随机源；Python 字符串 hash 会随进程变化。新增基于 `map_seed + tick + attacker_id + target_id + attack_serial` 的稳定整数 roll，Engine 和 `RuleEngine.apply()` 都显式传 combat seed。
- `launch_delay_ticks` 由 Task 1A 的 iscript/animation audit 提供；取消命令、目标死亡、stasis 和离开有效状态时如何清理 `pending_attack` 必须有测试。Godot 的 attack animation 从 `attack_started` 开始，枪口/挥击时刻以实际 launch/impact event 为准。

`process_projectiles()` 保持旧两参数调用兼容，同时新增：

```python
combat_events: list[dict] | None = None
kill_feed: KillFeed | None = None
```

到达时调用 `resolve_weapon_impact()`。Mutalisk 下一段必须等上一段到达后才创建，共用 `projectile_id`，递增 `chain_index`；Reaver 使用 tracking，目标移动时更新 last-known position。

- [ ] **Step 6：Engine 全 tick 共用事件列表**

Engine 的调用顺序保持：

```text
resolve_combat
process_spells
process_projectiles
finalize combat_events_this_tick
derive legacy generic events
```

三个阶段收到同一个 `combat_events` list。旧的 pre/post HP 猜测逻辑删除；若 replay/analytics 仍需要 `COMBAT_HIT` 和 `UNIT_DESTROYED`，在 tick 结束时从权威 CombatEvent 单向派生一次，不能再次扫描 HP。

`RuleEngine.apply()` 的非 Engine 调用路径也要传入本地事件列表并执行 projectile；不能保留一条“测试环境立即扣血、正式 Engine 延迟扣血”的分叉。

`process_spells()` 必须在每个 Engine tick 调用，即使 `spell_cmds=[]`；否则现有 storm effect 只在施法 tick 处理一次。持续效果的创建 tick、首个 damage tick 和最后一个 damage tick要由测试锁定，禁止在创建时和 active-effect loop 中同 tick 重复扣血。

为保持既有直接调用兼容，`process_spells()` 增加可选参数而不是修改已有位置参数：

```python
combat_events: list[dict] | None = None
kill_feed: KillFeed | None = None
```

本轮只把 Psionic Storm 的实际伤害迁移到 `resolve_weapon_impact()`；其他法术保持原行为，但仍必须通过现有回归测试。

- [ ] **Step 7：过滤内部实体**

以下消费者必须忽略 `entity_type in {"projectile", "effect"}`：

```text
auto-attack target selection
collision separation
fog source
terminal-state unit count
gRPC normal entity snapshot
Godot unit drawing/selection/minimap
```

projectile 的视觉位置通过 `projectile_spawned` 事件和 Godot tween 表现；本轮不把 projectile entity 暴露成可选单位。

- [ ] **Step 8：运行回归**

```bash
python3 -m pytest tests/simcore/test_projectile_combat_integration.py tests/simcore/test_combat_event_emission.py tests/simcore/test_combat.py tests/simcore/test_splash_damage.py tests/simcore/test_sprint3.py tests/simcore/test_support_spells.py -q
python3 -m pytest tests/godot/test_combat_event_contract.py -q
make lint-arch
```

Expected: 全部 PASS；测试明确证明 projectile flight ticks 内目标 HP 不变。

- [ ] **Step 9：提交**

```bash
git add simcore/combat_resolution.py simcore/rules.py simcore/projectile.py simcore/spells.py simcore/engine.py godot/scripts/game_view.gd tests/simcore/test_projectile_combat_integration.py tests/simcore/test_combat_event_emission.py tests/simcore/test_sprint3.py tests/simcore/test_support_spells.py tests/godot/test_combat_event_contract.py
git commit -m "feat: resolve ranged damage on authoritative projectile impact"
```

---

### Task 8：完成 Terran 四单位闭环

**Files:**
- Modify: `simcore/rules.py`
- Modify: `godot/resources/vfx/weapon_visual_catalog.json`
- Modify: `godot/resources/vfx/vfx_catalog.json`
- Modify: `godot/resources/sprite_frames_config.json`
- Modify: `godot/scripts/test_mode_gallery.gd`
- Modify: `tests/simcore/test_sc1_representative_weapons.py`
- Modify: `godot/scripts/test_sc1_combat_slice.gd`

- [ ] **Step 1：增加四组失败场景**

```text
Marine -> Zergling: hitscan normal, one impact
Firebat -> 3 Zerglings: cone splash fractions visible
Vulture -> Zealot: concussive projectile
Tank -> Dragoon: explosive shell and heavy impact
```

每组断言 attack event、impact event、weapon ID、final damage 和 VFX style。

- [ ] **Step 2：确认失败**

```bash
python3 -m pytest tests/simcore/test_sc1_representative_weapons.py -k terran -q
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sc1_combat_slice.gd -- --race=terran
```

- [ ] **Step 3：实现差异**

- Marine：短 hitscan，不能生成长寿命 projectile。
- Firebat：使用现有 splash 规则，但事件标记每个 splash target/fraction。
- Vulture：从 ballistic profile 分离为 grenade arc。
- Tank：普通模式使用 cannon shell；若实体 `siege_mode=true`，visual catalog 选择 `terran_arclite_siege_cannon` 扩展条目，使用更大爆炸和 splash。

- [ ] **Step 4：验证动画**

四单位的 `sprite_frames_config.json` 必须保留非零 `attack` 帧；Test Mode 逐单位播放两个完整攻击周期，不循环 idle 冒充 attack。

- [ ] **Step 5：运行回归并提交**

```bash
python3 -m pytest tests/simcore/test_sc1_representative_weapons.py tests/simcore/test_splash_damage.py tests/godot/test_weapon_visual_catalog.py -q
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sc1_combat_slice.gd -- --race=terran
git add simcore/rules.py godot/resources/vfx/weapon_visual_catalog.json godot/resources/vfx/vfx_catalog.json godot/resources/sprite_frames_config.json godot/scripts/test_mode_gallery.gd godot/scripts/test_sc1_combat_slice.gd tests/simcore/test_sc1_representative_weapons.py
git commit -m "feat: differentiate Terran representative weapons"
```

---

### Task 9：完成 Zerg 四单位闭环

**Files:**
- Modify: `simcore/rules.py`
- Modify: `simcore/projectile.py`
- Modify: `godot/resources/vfx/weapon_visual_catalog.json`
- Modify: `godot/resources/vfx/vfx_catalog.json`
- Modify: `godot/scripts/test_mode_gallery.gd`
- Modify: `tests/simcore/test_sc1_representative_weapons.py`
- Modify: `godot/scripts/test_sc1_combat_slice.gd`

- [ ] **Step 1：增加四组失败场景**

```text
Zergling -> Marine: melee normal
Hydralisk -> Dragoon: explosive needle projectile
Mutalisk -> three targets: chain_index 0/1/2
Ultralisk -> Zealot: heavy melee arc, no projectile
```

- [ ] **Step 2：增加 Mutalisk 精确断言**

```python
assert [e["chain_index"] for e in impacts] == [0, 1, 2]
assert [round(e["splash_fraction"], 6) for e in impacts] == [1.0, 0.333333, 0.111111]
assert len({e["projectile_id"] for e in impacts}) == 1
assert len({e["target_id"] for e in impacts}) == 3
```

后续目标选择必须确定性：按距离，再按 entity ID 排序；不能依赖 dict 插入顺序。

OpenBW 的 bounce 会选择底层 spatial query 返回的首个合法目标；SimCore 当前没有同构 spatial index。本轮以 `(distance, entity_id)` 作为可重放近似，并在 source audit 的 `known_divergences` 记录，不得声称 target selection 已逐帧等价于 SC1。

- [ ] **Step 3：确认失败**

```bash
python3 -m pytest tests/simcore/test_sc1_representative_weapons.py -k zerg -q
```

- [ ] **Step 4：实现差异**

- Zergling 与 Ultralisk 都是 melee，但效果尺寸、攻击保持时间和优先级不同。
- Hydralisk 使用 spine projectile，不使用 acid blob。
- Mutalisk 产生一条分段轨迹，每一段到达后再显示下一段。
- 事件中保存实际每段伤害；Godot 不自行乘 1/3。

- [ ] **Step 5：运行回归并提交**

```bash
python3 -m pytest tests/simcore/test_sc1_representative_weapons.py tests/simcore/test_combat.py tests/godot/test_weapon_visual_catalog.py -q
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sc1_combat_slice.gd -- --race=zerg
git add simcore/rules.py simcore/projectile.py godot/resources/vfx/weapon_visual_catalog.json godot/resources/vfx/vfx_catalog.json godot/scripts/test_mode_gallery.gd godot/scripts/test_sc1_combat_slice.gd tests/simcore/test_sc1_representative_weapons.py tests/simcore/test_projectile_combat_integration.py
git commit -m "feat: differentiate Zerg representative weapons"
```

---

### Task 10：完成 Protoss 四单位闭环

**Files:**
- Modify: `simcore/rules.py`
- Modify: `simcore/projectile.py`
- Modify: `simcore/spells.py`
- Modify: `godot/resources/vfx/weapon_visual_catalog.json`
- Modify: `godot/resources/vfx/vfx_catalog.json`
- Modify: `godot/scripts/test_mode_gallery.gd`
- Modify: `tests/simcore/test_sc1_representative_weapons.py`
- Modify: `tests/simcore/test_support_spells.py`
- Modify: `godot/scripts/test_sc1_combat_slice.gd`

- [ ] **Step 1：增加四组失败场景**

```text
Zealot -> target: two impact events in one attack cycle
Dragoon -> shielded target: phase orb + shield/health split
Templar -> area: one spell_resolved cast + repeated impact_resolved damage events
Reaver -> clustered targets: ammo decrement + scarab + splash
```

- [ ] **Step 2：增加关键断言**

Zealot：

```python
assert len(impacts) == 2
assert sum(e["health_damage"] + e["shield_damage"] for e in impacts) == expected_total
```

Templar：

```python
assert cast_event["weapon_id"] == "protoss_psionic_storm"
assert cast_event["event_type"] == "spell_resolved"
assert len(cast_events) == 1
assert all(e["event_type"] == "impact_resolved" for e in storm_impacts)
assert all(e["delivery_type"] == "area_periodic" for e in storm_impacts)
```

`tests/simcore/test_support_spells.py` 还必须锁定以下生命周期：

1. 施法 tick 创建一个 storm effect，并且不在创建分支和 active-effect 分支重复扣血。
2. 后续调用 `process_spells(..., commands=[])` 仍推进 storm，并只在 catalog 指定的 damage tick 扣血。
3. 首次、末次 damage tick、总 damage tick 数和总伤害与 Task 1A/Task 2 reference 一致。
4. 每个受影响目标在每个 damage tick 恰好一个 `impact_resolved`，所有事件共用稳定 effect ID。
5. 持续时间结束后删除 effect，下一 tick 不再扣血或发事件。

Reaver：

```python
assert after["reaver"]["scarab_count"] == before_count - 1
assert spawn["delivery_type"] == "tracking"
assert any(e["is_splash"] for e in impacts)
```

- [ ] **Step 3：确认失败**

```bash
python3 -m pytest tests/simcore/test_sc1_representative_weapons.py -k protoss -q
```

- [ ] **Step 4：实现差异**

- Zealot 的两个命中共享 attack cycle，但使用不同 event ID。
- Dragoon projectile 命中先扣 shield；同一次命中可以同时包含 shield 和 health damage。
- Templar cast 使用 `cast` 动画，不伪造普通 attack。
- Storm cast 只发一个 `spell_resolved`；effect entity 每次实际伤害对每个目标发出 `impact_resolved`，同一 storm 使用稳定 effect ID。
- Reaver 不能无 Scarab 开火；Scarab 到达后才发出 impact/splash 事件。

- [ ] **Step 5：运行回归并提交**

```bash
python3 -m pytest tests/simcore/test_sc1_representative_weapons.py tests/simcore/test_sprint3.py tests/simcore/test_splash_damage.py tests/simcore/test_support_spells.py tests/godot/test_weapon_visual_catalog.py -q
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sc1_combat_slice.gd -- --race=protoss
git add simcore/rules.py simcore/projectile.py simcore/spells.py godot/resources/vfx/weapon_visual_catalog.json godot/resources/vfx/vfx_catalog.json godot/scripts/test_mode_gallery.gd godot/scripts/test_sc1_combat_slice.gd tests/simcore/test_sc1_representative_weapons.py tests/simcore/test_projectile_combat_integration.py tests/simcore/test_support_spells.py
git commit -m "feat: differentiate Protoss representative weapons"
```

---

### Task 11：Test Mode 克制诊断层

**Files:**
- Modify: `godot/scripts/test_mode_gallery.gd`
- Modify: `godot/scripts/game_view.gd`
- Create or Modify: `godot/scripts/combat_diagnostics_overlay.gd`
- Modify: `godot/scripts/test_sc1_combat_slice.gd`

- [ ] **Step 1：写失败测试**

Test Mode 选择攻击者和目标后，诊断模型必须输出：

```gdscript
{
    "attacker": "Vulture",
    "target": "Zealot",
    "weapon_id": "terran_fragmentation_grenade",
    "weapon_type": "concussive",
    "armor_type": "light",
    "base_damage": 20.0,
    "damage_multiplier": 1.0,
    "shield_damage": 0.0,
    "health_damage": 19.0,
    "final_damage": 19.0,
}
```

该 fixture 明确把 Zealot shields 设为 0，以显示 20 base - 1 armor 的生命伤害；另一条 shield fixture 必须证明 concussive 倍率不作用于护盾。`final_damage` 使用事件中的真实结果，不能在 Godot 重算并覆盖。

- [ ] **Step 2：确认失败**

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sc1_combat_slice.gd -- --diagnostics
```

- [ ] **Step 3：实现诊断 UI**

仅 Test Mode 显示：

- attacker/target。
- weapon/armor 类型。
- base damage。
- multiplier。
- shield/health damage。
- splash fraction 或 chain index。
- event tick 和 event ID。

正式对局 scene tree 中不得创建可见诊断面板。

- [ ] **Step 4：增加固定 matchup presets**

```text
Marine vs Zergling
Firebat vs Zergling group
Vulture vs Zealot
Tank vs Dragoon
Hydralisk vs Dragoon
Mutalisk vs three Marines
Zealot vs Marine
Dragoon vs Ultralisk
Templar Storm vs Marine group
Reaver vs Zergling group
```

每个 preset 走标准 `process_combat_events()`。

- [ ] **Step 5：测试并提交**

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sc1_combat_slice.gd -- --diagnostics
python3 -m pytest tests/godot/test_weapon_visual_catalog.py tests/godot/test_combat_event_contract.py -q
git add godot/scripts/test_mode_gallery.gd godot/scripts/game_view.gd godot/scripts/combat_diagnostics_overlay.gd godot/scripts/test_sc1_combat_slice.gd
git commit -m "feat: add Test Mode combat diagnostics"
```

---

### Task 12：资源与动画完整性门

**Files:**
- Modify: `tests/godot/test_weapon_visual_catalog.py`
- Modify: `scripts/verify_presentation_scene.py`
- Modify: `docs/reports/sc1-combat-differentiation-qa.md`

- [ ] **Step 1：增加 12 单位资源门**

自动检查：

- `presentation_manifest.unit_visuals` 存在。
- `sprite_frames_config.units` 存在对应项。
- 普通单位有 `attack > 0`。
- Templar 有 `cast > 0`。
- asset 文件存在且 atlas frame 不越界。
- animation 帧不是全透明。
- generated asset 缺失不阻断正式资源，但在 QA 报告标记 Templar 原始提取资源缺口。

- [ ] **Step 2：运行资源校验**

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot/test_weapon_visual_catalog.py tests/godot/test_presentation_manifest.py -q
```

Expected: 12/12 PASS。

- [ ] **Step 3：人工逐帧检查**

每单位检查：

1. 八方向或当前支持方向没有明显错帧。
2. attack/cast 不使用 moving 帧。
3. 开火时刻位于攻击动作有效帧内。
4. projectile 起点不在身体中心或目标身后。
5. impact 位于目标可见边界附近。
6. death 不复用普通 hit 无限循环。

- [ ] **Step 4：提交**

```bash
git add tests/godot/test_weapon_visual_catalog.py scripts/verify_presentation_scene.py docs/reports/sc1-combat-differentiation-qa.md
git commit -m "test: gate representative combat resources"
```

---

### Task 13：端到端、回放与性能验收

**Files:**
- Create: `tests/integration/test_combat_visual_events_e2e.py`
- Modify: `docs/godot_verification_guide.md`
- Modify: `docs/reports/sc1-combat-differentiation-qa.md`

- [ ] **Step 1：增加端到端测试**

启动真实 SimCore，制造 Marine 对 Zergling 攻击，断言：

```text
command accepted
attack_started transported
impact_resolved transported
weapon_id preserved
damage fields preserved
event ID unique
replay stores same event
```

- [ ] **Step 2：确定性测试**

同 seed、同命令序列运行两次：

```python
assert first_run_combat_events == second_run_combat_events
```

事件顺序、target selection、chain target 和 event ID 必须一致。

测试必须通过子进程分别设置 `PYTHONHASHSEED=1` 和 `PYTHONHASHSEED=999`；两次输出的序列化 combat events 必须逐字节相同，避免仅在同一 Python 进程内得到伪确定性结果。

- [ ] **Step 3：30v30 VFX cap**

Test Mode 同时生成 60 个单位并持续 30 秒：

- `_effects <= max_active_effects`
- `_projectiles <= max_projectiles`
- 无 orphan projectile。
- 无重复 event 播放。
- 血条、选择圈和单位主体仍可辨认。

- [ ] **Step 4：全量自动回归**

```bash
make proto
make lint-arch
python3 -m pytest tests/simcore tests/proto tests/godot tests/tools tests/integration -q -x
python3 scripts/verify_presentation_scene.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_combat_event_pipeline.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_sc1_combat_slice.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --editor --quit
git diff --check
```

Expected: 全部 PASS，无 GDScript parse error。

- [ ] **Step 5：人工正式对局验收**

正式对局完成以下场景：

```text
8 Marine vs 12 Zergling
6 Firebat vs 16 Zergling
4 Vulture vs 8 Zealot
3 Tank vs 6 Dragoon
8 Hydralisk vs 6 Dragoon
6 Mutalisk vs 10 Marine
8 Zealot vs 12 Marine
6 Dragoon vs 3 Ultralisk
2 Templar Storm vs Marine group
3 Reaver vs Zergling group
```

每项按 1-5 分评价：

- 单位身份辨识。
- 攻击动作辨识。
- 弹道辨识。
- 命中反馈。
- 克制结果与视觉一致。
- 密集战斗可读性。

所有项目必须 `>= 4/5`；否则 QA 状态为 CONCERNS，不宣称完成。

- [ ] **Step 6：更新文档**

`docs/godot_verification_guide.md` 增加：

- CombatEvent 检查方式。
- 12 单位 Test Mode preset。
- 正式对局 matchup。
- replay 事件一致性。
- 性能上限。

- [ ] **Step 7：最终提交**

```bash
git add tests/integration/test_combat_visual_events_e2e.py docs/godot_verification_guide.md docs/reports/sc1-combat-differentiation-qa.md
git commit -m "test: complete SC1 combat differentiation gate"
```

## 5. 阶段门与停止条件

| Gate | 完成条件 | 失败时处理 |
|---|---|---|
| G0 Baseline | 现有 combat/VFX 测试通过 | 不开始协议修改 |
| G0A Source | DAT 12/12 唯一映射、时钟/数值/size 已裁决 | 不创建 mechanics catalog |
| G1 Contract | Proto round-trip + ADR 通过 | 不修改 Godot |
| G2 Authority | SimCore 事件字段准确、shield 顺序正确、projectile 到达才扣血、确定性 | 不关闭 HP-delta fallback |
| G3 Transport | gRPC/HTTP/replay 无字段丢失 | 不接正式对局 |
| G4 Terran | 4/4 自动 + 人工通过 | 不开始 Zerg |
| G5 Zerg | 4/4，Mutalisk chain 精确 | 不开始 Protoss |
| G6 Protoss | 4/4，Storm/Scarab 精确 | 不开始 30v30 |
| G7 Final | 全量回归 + 人工评分通过 | 保持 QA 为 CONCERNS |

出现以下任一情况必须停止并报告：

1. Proto 改动导致既有 replay 无法读取且没有兼容策略。
2. 同 seed 事件序列不确定。
3. Godot 一个 impact 显示两次。
4. 正式对局和 Test Mode 使用不同 weapon visual catalog。
5. 为追求视觉效果修改基础数值但没有 balance-check。
6. 需要提交新的商业 SC1 原始资源。
7. DAT 审计与 OpenBW 固定 commit 对同一字段给出冲突，且报告没有裁决证据。
8. weapon type multiplier 被应用到 Protoss shield，或 projectile 发射 tick 提前扣血。

## 6. 完成定义

只有同时满足以下条件才可以把计划标记为完成：

- 12/12 单位有独立语义 `weapon_id`。
- 12/12 单位的 unit size、weapon DAT、damage factor 和 cooldown 均能追溯到 source audit。
- 12/12 单位的 attack/cast 动画可播放。
- 12/12 单位正式对局通过权威事件触发表现。
- Test Mode 使用同一事件入口和 visual catalog。
- normal/explosive/concussive 的倍率与实际伤害一致。
- shield-first、health armor、size multiplier 的顺序与固定 OpenBW 基线一致。
- Shield/health damage 可拆分验证。
- Mutalisk 三段弹射、Zealot 双 hit、Storm 周期伤害、Reaver Scarab 都有自动测试。
- replay 保留事件且同 seed 确定。
- 30v30 VFX 数量受控。
- 所有自动测试通过。
- 人工 matchup 评分全部不低于 4/5。
- QA 报告中不存在被写成 PASS 的待人工项目。

## 7. 推荐执行分工

其他模型可按下列顺序串行或受控并行：

| Worker | Tasks | 允许并行条件 |
|---|---|---|
| Protocol/Architecture | 0-1、3 | 必须先完成 |
| SC1 Data Audit | 1A-2 | Task 1A 必须先于 Task 2 |
| SimCore Event/Transport | 4-5 | 依赖 Task 2-3 |
| Godot Event Pipeline | 6-7 | 依赖 Task 5 |
| Combat Integration | 7A | 依赖 Task 5 和 Task 7 |
| Terran Slice | 8 | 依赖 Task 7A |
| Zerg Slice | 9 | 可与 Task 8 开发并行，但合并必须在 Task 8 gate 后 |
| Protoss Slice | 10 | 可与 Task 8 开发并行，但合并必须在 Task 9 gate 后 |
| Test Mode/QA | 11-13 | 依赖三族 slice |

每个 worker 只修改自己 Task 的文件。跨 worker 冲突集中在 `simcore/rules.py`、`godot/scripts/vfx_manager.gd` 和两个 JSON catalog；这些文件必须由一个集成 worker 串行合并。
