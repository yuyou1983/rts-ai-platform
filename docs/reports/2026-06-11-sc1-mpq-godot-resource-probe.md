# SC1 MPQ 与 Godot 资源对齐探查报告

日期：2026-06-11

## 结论

已完成安全保护、工具验证、P0 资源抽取和本地 Godot 资源生成。

- Git 已先创建分支并做保护提交：`codex-sc1-mpq-resource-sync`。
- 已验证 `/Users/yuyou/code/StarCraft` 下 3 个 MPQ：`StarDat.mpq`、`BrooDat.mpq`、`Patch_rt.mpq`。
- 已使用 StormLib 打开并抽取 MPQ 文件。
- 已实现 headless GRP -> PNG 转换脚本，避免 PyMS GUI/Tk 依赖。
- P0 manifest 的 20 个资源全部抽取成功，全部转换成功。
- 已生成 Godot 本地资源目录：`godot/assets/sc1_generated/p0/`。

注意：`godot/assets/sc1_generated/`、`local_assets/`、`tools/mpq/` 都是 ignored 本地产物，不提交原始或导出的 SC1 商业资源。

## 使用的开源项目

| 项目 | 用途 | 当前结论 |
| --- | --- | --- |
| [StormLib](https://github.com/ladislav-zezula/StormLib) | MPQ 读取和单文件抽取 | 可用，已本地编译并验证 |
| [PyMS](https://github.com/poiuyqwert/PyMS) | SC1 listfile、DAT/TBL 参考、GRP 格式参考 | 可用于路径和格式参考；CLI 入口在当前环境有 Tk/Python 2 兼容问题 |
| [OpenBW](https://github.com/OpenBW/openbw) | 后续对照 SC1/BW 语义、单位/图像映射 | 建议用于 Phase 2 交叉校验 |
| [BWAPI](https://github.com/bwapi/bwapi) | 后续对照单位枚举、尺寸、武器/命令语义 | 建议用于 Phase 2 交叉校验 |

## 已新增仓库文件

| 文件 | 作用 |
| --- | --- |
| `scripts/sc1_grp_to_png.py` | 将本地 GRP 转成 PNG contact sheet，不依赖 PyMS GUI |
| `scripts/sc1_extract_manifest.py` | 按 manifest 从 MPQ 抽取并可选转换 PNG |
| `tools/sc1_assets/p0_resource_manifest.json` | P0 资源路径清单：工人、基础兵、基础建筑、矿物、野气 |

## 本地生成结果

命令：

```bash
python3 scripts/sc1_extract_manifest.py \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --convert \
  --png-out godot/assets/sc1_generated/p0 \
  --report local_assets/sc1_asset_extract_godot_report.json
```

结果：

```text
assets=20 extracted=20 missing=0
converted_failed=0
```

生成文件：

```text
godot/assets/sc1_generated/p0/SCV.png
godot/assets/sc1_generated/p0/Marine.png
godot/assets/sc1_generated/p0/Drone.png
godot/assets/sc1_generated/p0/Zergling.png
godot/assets/sc1_generated/p0/Probe.png
godot/assets/sc1_generated/p0/Zealot.png
godot/assets/sc1_generated/p0/CommandCenter.png
godot/assets/sc1_generated/p0/Barracks.png
godot/assets/sc1_generated/p0/Refinery.png
godot/assets/sc1_generated/p0/Hatchery.png
godot/assets/sc1_generated/p0/SpawningPool.png
godot/assets/sc1_generated/p0/Extractor.png
godot/assets/sc1_generated/p0/Nexus.png
godot/assets/sc1_generated/p0/Gateway.png
godot/assets/sc1_generated/p0/Pylon.png
godot/assets/sc1_generated/p0/Assimilator.png
godot/assets/sc1_generated/p0/MineralFieldType1.png
godot/assets/sc1_generated/p0/MineralFieldType2.png
godot/assets/sc1_generated/p0/MineralFieldType3.png
godot/assets/sc1_generated/p0/VespeneGeyser.png
```

## 关键尺寸对比

| 资源 | SC1 转换结果 | Godot 当前资源 | 判断 |
| --- | ---: | ---: | --- |
| CommandCenter | contact sheet `2176x160`，单帧 `128x160` | Terran 合图 cell `191x266` | 当前建筑 cell 明显大于原始帧，选择圈/边界容易漂移 |
| Barracks | contact sheet `3264x160`，单帧 `192x160` | Terran 合图 cell `191x266` | 宽接近，高度差异明显 |
| Hatchery | contact sheet `3264x160`，单帧 `192x160` | Zerg 合图 cell `486x362` | 当前 Zerg 建筑合图存在巨大 padding/缩放差 |
| Nexus | contact sheet `3264x224`，单帧 `192x224` | Protoss 合图 cell `209x200` | 高度方向不一致，pivot 需要重算 |
| Marine | contact sheet `1088x896`，单帧 `64x64` | `1152x896` | 当前图多出横向 padding 或列布局不一致 |
| SCV | contact sheet `1224x216`，单帧 `72x72` | `389x239` | 当前资源不是标准 GRP contact sheet |
| Probe | contact sheet `544x32`，单帧 `32x32` | `288x64` | 当前资源帧布局与原始 GRP 不一致 |
| MineralFieldType1 | contact sheet `1088x96`，单帧 `64x96` | 无明确 Godot manifest 项 | Godot 缺少资源点视觉入口 |

## 当前问题

1. Godot 建筑资源是按种族合并的大图，再用 `sprite_frames_config.json` / `presentation_manifest.json` 裁切；SC1 原始资源是每个单位/建筑一个 GRP。两者资源粒度不同。

2. 建筑边界不清的直接原因是当前合图 cell 与原始单帧尺寸不一致。例如 Command Center 原始单帧是 `128x160`，当前 Terran 建筑 cell 是 `191x266`，再加上 `BUILDING_ATLAS_PADDING=12` 会进一步放大裁切区域。

3. 当前单位资源也不是统一的原始 GRP contact sheet 格式。比如 SCV 当前 PNG 是 `389x239`，而原始 contact sheet 是 `1224x216`。这会导致 `frame_width/frame_height/directions/animations` 配置无法直接与 SC1 原始帧模型对齐。

4. 资源点缺少明确 Godot 表现入口。矿物和野气已经可以从 MPQ 生成，但当前 manifest 主要覆盖单位和建筑。

5. PyMS 文本名表、DAT、TBL 的索引不能直接按行号推断。`SpawningPool` 的真实 GRP 路径需要通过 DAT/TBL 与视觉预览共同确认，当前 P0 manifest 记录为 `unit\\zerg\\chrysal.grp`。

## 建议接入方案

短期不要直接把 `godot/assets/sc1_generated/p0/*.png` 写死进 `presentation_manifest.json`。原因是这些 PNG 是本地 MPQ 生成物，不应提交；如果 manifest 直接引用，干净 checkout 会缺资源。

推荐做一个可回退的 override 层：

1. 新增 `godot/resources/sc1_generated_manifest.json` 到 ignored 输出目录，记录每个实体的 generated PNG、原始 GRP 帧宽高、帧数、源 MPQ。
2. `SpriteLoader` 启动时先查 optional generated manifest；如果本地存在 generated PNG，则使用原始资源；否则回退到当前提交内置资源。
3. 建筑使用单资源 PNG 后，去掉 race-level 合图裁切路径的 padding 修正，pivot/selection radius 按原始单帧尺寸重新计算。
4. 资源点加入 `presentation_manifest.json` 或新资源视觉 manifest，让矿物/野气不再走临时占位。
5. 用 Playwright/Godot 截图做接入前后对比：建筑轮廓、选择圈、血条、资源点、单位朝向和动画帧。

## 全量资源对比方案

| 阶段 | 输入 | 输出 | 校验 |
| --- | --- | --- | --- |
| A. MPQ 目录盘点 | `Patch_rt.mpq`、`BrooDat.mpq`、`StarDat.mpq`、PyMS listfile | `source_inventory.json` | 所有 `.grp/.pcx/.wav/.tbl/.dat/.lo*` 是否可抽取 |
| B. 语义映射 | `images.dat`、`images.tbl`、`units.dat`、`Sprites.txt`、`Images.txt` | `sc1_semantic_map.json` | entity id -> image id -> GRP path 不靠猜测 |
| C. 转换产物 | GRP/PCX/palette | `converted_inventory.json` + PNG | 帧数、单帧尺寸、透明像素 bbox、contact sheet 尺寸 |
| D. Godot 清单 | `presentation_manifest.json`、`sprite_frames_config.json`、Godot PNG | `godot_inventory.json` | asset 是否存在、尺寸是否匹配、atlas_rect 是否越界 |
| E. 差异报告 | A-D | `resource_alignment_report.md` | `MATCH / LOCAL_OVERRIDE / MISSING / SIZE_MISMATCH / FRAME_LAYOUT_MISMATCH` |
| F. 视觉 QA | Godot 运行截图 + generated contact sheet | 对比图 | 选择圈、边界、血条、朝向、动画、资源点 |

## 下一步执行顺序

1. 完成 optional generated manifest，并让 `SpriteLoader` 支持本地 override + fallback。
2. 先接入 P0：工人、基础兵、基地、基础生产建筑、矿物、野气。
3. 重算建筑 pivot、render_scale、selection_radius，删除当前针对合图 padding 的经验修正。
4. 加资源点视觉和采集点 marker，对齐 SimCore 资源实体。
5. 扩展 manifest 到当前 Godot 已列出的全部单位/建筑。
6. 引入 OpenBW/BWAPI 作为语义交叉校验源，减少文件名和文本名表误判。
7. 最后再决定是否保留当前提交内置资源，或只作为无 MPQ 时的 fallback。

## 后续实现：本地 Generated Override

已完成第 1 步的最小闭环：

- `scripts/sc1_extract_manifest.py` 在 `--convert` 成功时会额外生成 `godot/assets/sc1_generated/generated_manifest.json`。
- `generated_manifest.json` 记录每个 P0 资源的 `asset`、`source_mpq`、`mpq_path`、`frame_count`、`frame_width`、`frame_height`、`atlas_rect`。
- runtime policy 当前为 `building_and_resource_overrides_only`：
  - `building` 和 `resource` 默认 `runtime_enabled=true`。
  - `unit` 默认 `runtime_enabled=false`，避免在未完成 iscript/动画帧序映射前直接替换单位动画。
- `SpriteLoader` 会尝试读取 `res://assets/sc1_generated/generated_manifest.json`。
- 如果 generated manifest 存在且建筑条目 `runtime_enabled=true`，`SpriteLoader.get_building_atlas()` 会直接使用 generated PNG 的原始单帧 `atlas_rect`，不再套用提交内建筑合图的 padding。
- 如果 generated manifest 缺失、条目禁用、PNG 不存在或加载失败，则自动回退到当前 `presentation_manifest.json` / `sprite_frames_config.json` 路径。
- 对未导入 Godot 的本地 PNG，`SpriteLoader` 已增加 `Image.load()` + `ImageTexture.create_from_image()` fallback，因此 ignored 目录中的 generated PNG 不需要提交 `.import` 文件。

验证命令：

```bash
python3 scripts/sc1_extract_manifest.py \
  --starcraft-dir /Users/yuyou/code/StarCraft \
  --convert \
  --png-out godot/assets/sc1_generated/p0 \
  --report local_assets/sc1_asset_extract_godot_report.json

pytest tests/godot/test_sc1_generated_manifest.py tests/godot/test_presentation_manifest.py -q

/Applications/Godot.app/Contents/MacOS/Godot \
  --headless --path godot --script scripts/test_sprite_loader_generated.gd
```

验证结果：

```text
assets=20 extracted=20 missing=0
converted_failed=0
pytest: 16 passed
SpriteLoader generated manifest test: 2 passed, 0 failed
```

备注：`Godot --headless --path godot --check-only` 在当前环境中未自然退出，已终止该单独校验进程；本轮以专门的 SpriteLoader headless 脚本作为 Godot 行为验证。
