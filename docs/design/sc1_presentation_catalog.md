# SC1 表现映射目录

> 机器可读版: `godot/resources/presentation_manifest.json`
> Godot 校验脚本: `godot/scripts/verify_manifest.gd`
> Python 校验脚本: `scripts/verify_presentation_scene.py`
> 更新时间: 2026-05-30

---

## 1. 抽象类型 → SC 单位映射

| 抽象类型 | Terran (P1) | Zerg (P2) | Protoss (P3) |
|---------|------------|----------|-------------|
| worker | SCV | Drone | Probe |
| soldier | Marine | Zergling | Zealot |
| scout | Ghost | Hydralisk | Dragoon |

## 2. 抽象类型 → SC 建筑映射

| 抽象类型 | Terran (P1) | Zerg (P2) | Protoss (P3) |
|---------|------------|----------|-------------|
| base | CommandCenter | Hatchery | Nexus |
| barracks | Barracks | SpawningPool | Gateway |
| factory | Factory | — | — |
| refinery | Refinery | Extractor | Assimilator |
| starport | Starport | — | — |
| lair | — | Lair | — |
| hive | — | Hive | — |
| pylon | — | — | Pylon |

## 3. 建筑视觉参数

### Terran 建筑

| 建筑 | atlas_rect [x,y,w,h] | pivot | render_scale | selection_radius | health_bar_offset |
|------|---------------------|-------|-------------|-----------------|-------------------|
| CommandCenter | [205,190,145,95] | [0.5,0.72] | 0.04 | 4.1 | [0,-0.28] |
| Barracks | [573,197,191,69] | [0.5,0.72] | 0.0319 | 3.2 | [0,-0.28] |
| Factory | [409,466,164,47] | [0.5,0.72] | 0.0426 | 3.5 | [0,-0.28] |
| Refinery | [382,189,191,77] | [0.5,0.72] | 0.026 | 2.8 | [0,-0.28] |
| Starport | [573,446,191,86] | [0.5,0.72] | 0.0256 | 3.5 | [0,-0.28] |
| SupplyDepot | [191,0,191,266] | [0.5,0.72] | 0.0156 | 3.0 | [0,-0.28] |
| **Fallback** | [1,1,128,109] | [0.5,0.72] | 0.015 | — | [0,-0.28] |

> atlas_rect 来源：game_view.gd `_get_building_region()` 精确裁剪值，
> 迁移到 manifest 后 Godot 直读，不再走硬编码覆盖。

### Zerg 建筑

| 建筑 | atlas_rect [x,y,w,h] | pivot | render_scale | selection_radius | health_bar_offset |
|------|---------------------|-------|-------------|-----------------|-------------------|
| Hatchery | [30,301,121,128] | [0.5,0.72] | 0.033 | 4.1 | [0,-0.28] |
| SpawningPool | [1478,688,83,85] | [0.5,0.72] | 0.048 | 2.8 | [0,-0.28] |
| Lair | [10,627,210,132] | [0.5,0.72] | 0.019 | 4.1 | [0,-0.28] |
| Hive | [11,1184,141,124] | [0.5,0.72] | 0.028 | 4.1 | [0,-0.28] |
| Extractor | [972,362,486,362] | [0.5,0.72] | 0.0107 | 2.5 | [0,-0.28] |
| **Fallback** | [1475,670,89,100] | [0.5,0.72] | 0.045 | — | [0,-0.28] |

### Protoss 建筑

| 建筑 | atlas_rect [x,y,w,h] | pivot | render_scale | selection_radius | health_bar_offset |
|------|---------------------|-------|-------------|-----------------|-------------------|
| Nexus | [0,0,209,200] | [0.5,0.72] | 0.0156 | 4.1 | [0,-0.28] |
| Gateway | [627,0,209,200] | [0.5,0.72] | 0.0156 | 3.2 | [0,-0.28] |
| Assimilator | [418,0,209,200] | [0.5,0.72] | 0.0156 | 2.8 | [0,-0.28] |
| Pylon | [209,0,209,200] | [0.5,0.72] | 0.0156 | 2.0 | [0,-0.28] |
| **Fallback** | [1,1,128,128] | [0.5,0.72] | 0.015 | — | [0,-0.28] |

## 4. 单位视觉参数

### 核心单位（三族 worker/combat/scout）

| 单位 | Race | render_scale | selection_radius | health_bar_offset |
|------|------|-------------|-----------------|-------------------|
| SCV | Terran | 0.0208 | 0.688 | [0,-0.28] |
| Marine | Terran | 0.0072 | 0.688 | [0,-0.28] |
| Ghost | Terran | 0.0208 | 0.672 | [0,-0.28] |
| Drone | Zerg | 0.0107 | 0.688 | [0,-0.28] |
| Zergling | Zerg | 0.0087 | 0.531 | [0,-0.28] |
| Hydralisk | Zerg | 0.0121 | 0.781 | [0,-0.28] |
| Probe | Protoss | 0.0234 | 0.5 | [0,-0.28] |
| Zealot | Protoss | 0.0109 | 0.688 | [0,-0.28] |
| Dragoon | Protoss | 0.0121 | 0.781 | [0,-0.28] |

### 全量单位（43个）

> 详见 `presentation_manifest.json` → `unit_visuals`

## 5. 全局渲染参数

### 选择圈

| 参数 | 值 |
|------|------|
| 颜色 | RGBA(0.2, 1.0, 0.2, 0.88) |
| 线宽 | 0.055 |
| 弧段数 | 24 |

### 血条

| 参数 | 值 |
|------|------|
| 偏移 | [0, -0.28] (相对 sprite 顶部) |
| 宽度系数 | radius × 1.45 |
| 宽度范围 | [0.55, 2.8] |
| 高度 | 0.15 |
| 颜色阈值 | GREEN > 60%, YELLOW > 30%, RED ≤ 30% |

### 缩放变换

| 类型 | 乘数 | 最小 | 最大 |
|------|------|------|------|
| 建筑 render_scale | ×1 (直读 manifest) | — | — |
| 建筑 selection_radius | ×0.34 | 0.95 | 1.65 |
| 单位 render_scale | ×1 (直读 manifest) | — | — |
| 单位 selection_radius | ×0.78 | 0.38 | 0.72 |

> ⚠️ selection_radius 变换逻辑目前仍在 `_visual_radius()` 中。
> 迁移后改为 manifest 直读最终值，删除 clamp。

## 6. Fallback 规则

1. **单位**：按 race 查 fallback → 同种族最简单单位 sprite
   - Terran → Marine (render_scale 0.0072)
   - Zerg → Zergling (render_scale 0.0087)
   - Protoss → Zealot (render_scale 0.0109)
2. **建筑**：按 race 查 fallback → 通用建筑 atlas rect
   - Terran → [1,1,128,109] at scale 0.015
   - Zerg → [1475,670,89,100] at scale 0.045
   - Protoss → [1,1,128,128] at scale 0.015

## 7. VFX 映射

| VFX 类别 | 覆盖单位 | 配置位置 |
|---------|---------|---------|
| attack | 所有 attack_capable 单位 | `spell_visuals` → `attack_profile` |
| build | worker 类 | `spell_visuals` → `build_profile` |
| gather | worker 类 | `spell_visuals` → `gather_profile` |
| death | 所有 combat 单位 | `spell_visuals` → `death_profile` |
| idle | — | — |

## 8. 资源类视觉

| 资源类型 | 视觉 | 来源 |
|---------|------|------|
| mineral | 蓝色水晶 | `sprite_frames_config` → mineral |
| gas | 绿色气泵 | `sprite_frames_config` → vespene |
| creep | 紫色地面 | 程序生成 |
| fog | 灰色半透明 | 程序渲染 (`_draw_fog_of_war`) |

## 9. Godot 校验

在 Godot 编辑器中运行校验脚本：

```
# 从编辑器脚本编辑器中按 Ctrl+Shift+X 执行：
var v = load("res://scripts/verify_manifest.gd").new()
v.run()
```

或在项目加载时自动执行（`game_view.gd` `_ready()` 中调用 `VerifyManifest.run()`）。

校验项：
- manifest JSON 合法且所有 required key 存在
- atlas_rect 不超出 PNG 实际尺寸
- abstract_* 映射全部 resolve 到已知 visual
- fallback 资源文件存在
- render_scale / selection_radius > 0
- 无 `|| true` 类吞失败命令
