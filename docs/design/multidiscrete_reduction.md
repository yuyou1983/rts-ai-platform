# MultiDiscrete 降维方案设计

## 1. 现有编解码实现分析

### 1.1 当前 Action Space

```
Discrete(98304) = 6 cmd × 64 units × 256 targets
```

- `n_cmd = len(COMMAND_TYPES) = 6`  → [move, gather, attack, build, train, noop]
- `n_units = MAX_ENTITIES = 64`
- `n_targets = 16 × 16 = 256` (粗粒度网格, 每个 cell = MAP_SIZE/16 = 4 世界单位)

### 1.2 编码公式（gym_env.py docstring）

```
action = cmd_type × (64 × 256) + unit_idx × 256 + target_idx
       = cmd_type × 16384 + unit_idx × 256 + target_idx
```

注意：当前代码中 **没有 `_encode_action` 方法**，只有 `_decode_action`。  
编码逻辑隐含在 `action_space.sample()` 产生 0..98303 整数后交给 `_decode_action`。

### 1.3 解码实现 (`_decode_action`，L225-297)

```python
def _decode_action(self, action: int) -> list[dict]:
    n_targets = 16 * 16       # = 256
    n_units = MAX_ENTITIES     # = 64
    n_cmd = len(COMMAND_TYPES) # = 6

    ct_idx    = action // (n_units * n_targets)          # [0..5]
    remainder = action % (n_units * n_targets)
    unit_idx  = remainder // n_targets                    # [0..63]
    target_idx = remainder % n_targets                    # [0..255]

    ct_idx = min(ct_idx, n_cmd - 1)   # 越界保护

    cmd_type = COMMAND_TYPES[ct_idx]  # str
```

**关键后续处理：**

| 步骤 | 描述 |
|------|------|
| entity lookup | `entity_ids = list(state.entities.keys())`, `eid = entity_ids[unit_idx]` |
| owner check | 非 P1 (single_player) → fallback `noop` |
| target decode | `tx = (target_idx % 16) * (MAP_SIZE/16)`, `ty = (target_idx // 16) * (MAP_SIZE/16)` |

### 1.4 六种命令的参数需求

| 命令 | 参数需求 | target_xy 使用情况 | 备注 |
|------|---------|--------------------|------|
| **move** | `unit_id`, `target_x`, `target_y` | ✅ 使用 tx, ty | 唯一真正需要 target 坐标的命令 |
| **gather** | `worker_id`, `resource_id` (自动选最近) | ❌ 忽略 tx, ty | target_idx 实际无用 |
| **attack** | `attacker_id`, `target_id` (自动选最近敌) | ❌ 忽略 tx, ty | target_idx 实际无用 |
| **build** | `builder_id`, `building_type`="barracks"(固定), `pos_x`, `pos_y` | ✅ 使用 tx, ty | 需要 target 坐标 |
| **train** | `building_id`, `unit_type`="soldier"(固定) | ❌ 忽略 tx, ty | target_idx 实际无用 |
| **noop** | 无 | ❌ 忽略 | unit_idx, target_idx 都无用 |

**发现：6 种命令中仅 2 种 (move, build) 实际使用 target 坐标，4 种完全浪费 target 维度。**

### 1.5 step() 流程

```
action(int) → _decode_action() → commands: list[dict]
                                      ↓
                    inject P2 AI commands → all_commands
                                      ↓
                    engine.step(all_commands) → new GameState
                                      ↓
                    _state_to_obs() + _compute_reward() → obs, reward, ...
```

---

## 2. MultiDiscrete 降维方案

### 2.1 设计原则

1. **语义透明**：每个维度有明确含义，便于 action mask
2. **sb3 兼容**：`spaces.MultiDiscrete` 原生支持，无需额外 wrapper
3. **降维目标**：从 98304 → 6×64×16×16 = 98304 同维，但结构化表达  
   进一步优化：利用命令参数冗余，减少无效组合

### 2.2 方案 A：结构化 MultiDiscrete（推荐）

```python
# nvec = [cmd_type, unit_idx, target_grid_x, target_grid_y]
action_space = spaces.MultiDiscrete(nvec=[6, 64, 16, 16])
```

**维度语义：**

| 维度 | nvec | 范围 | 含义 |
|------|------|------|------|
| dim0 | 6 | 0..5 | 命令类型：move/gather/attack/build/train/noop |
| dim1 | 64 | 0..63 | 实体索引（映射到 state.entities keys） |
| dim2 | 16 | 0..15 | 目标格子 X（粗粒度，每格 4 世界单位） |
| dim3 | 16 | 0..15 | 目标格子 Y（粗粒度，每格 4 世界单位） |

**总组合数：6 × 64 × 16 × 16 = 98,304（与原始 Discrete 相同）**

但结构化表达带来巨大优势：
- action mask 可按维度独立计算
- 每个维度独立探索，加速收敛
- 可对特定命令做条件 mask（如 noop 时 unit_idx 无需 mask）

### 2.3 编解码转换逻辑

```python
# ─── Encode: MultiDiscrete → Command Dict ─────────────────
def _decode_action_md(self, action: np.ndarray) -> list[dict]:
    """
    Args:
        action: shape (4,), dtype int64, values [cmd, unit, gx, gy]
    Returns:
        list of command dicts (same format as _decode_action)
    """
    ct_idx, unit_idx, gx, gy = int(action[0]), int(action[1]), int(action[2]), int(action[3])

    ct_idx = min(ct_idx, len(COMMAND_TYPES) - 1)
    cmd_type = COMMAND_TYPES[ct_idx]

    if self._engine.state is None:
        return []

    entity_ids = list(self._engine.state.entities.keys())
    if unit_idx >= len(entity_ids):
        return [{"action": "noop", "issuer": 1}]

    eid = entity_ids[unit_idx]
    entity = self._engine.state.entities[eid]
    owner = entity.get("owner", 0)

    if not self._two_player and owner != 1:
        return [{"action": "noop", "issuer": 1}]

    tx = gx * (MAP_SIZE / 16)   # gx ∈ [0..15] → tx ∈ [0..60]
    ty = gy * (MAP_SIZE / 16)   # gy ∈ [0..15] → ty ∈ [0..60]

    # 命令构建 — 与现有 _decode_action 逻辑完全一致
    cmd: dict[str, Any] = {"action": cmd_type, "issuer": owner}

    if cmd_type == "move":
        cmd["unit_id"] = eid
        cmd["target_x"] = tx
        cmd["target_y"] = ty
    elif cmd_type == "gather":
        cmd["worker_id"] = eid
        # 自动选最近 resource（同原逻辑）
        best_rid, best_dist = "", float("inf")
        for rid, r in self._engine.state.entities.items():
            if r.get("entity_type") == "resource" and r.get("resource_amount", 0) > 0:
                d = math.hypot(entity["pos_x"] - r["pos_x"], entity["pos_y"] - r["pos_y"])
                if d < best_dist:
                    best_dist, best_rid = d, rid
        cmd["resource_id"] = best_rid
    elif cmd_type == "attack":
        cmd["attacker_id"] = eid
        best_tid, best_dist = "", float("inf")
        for tid, t in self._engine.state.entities.items():
            if t.get("owner") not in (0, owner) and t.get("health", 0) > 0:
                d = math.hypot(entity["pos_x"] - t["pos_x"], entity["pos_y"] - t["pos_y"])
                if d < best_dist:
                    best_dist, best_tid = d, tid
        cmd["target_id"] = best_tid
    elif cmd_type == "build":
        cmd["builder_id"] = eid
        cmd["building_type"] = "barracks"
        cmd["pos_x"] = tx
        cmd["pos_y"] = ty
    elif cmd_type == "train":
        cmd["building_id"] = eid
        cmd["unit_type"] = "soldier"
    elif cmd_type == "noop":
        pass

    return [cmd]

# ─── Backward-compatible: Discrete → MultiDiscrete ─────────
@staticmethod
def discrete_to_md(action: int) -> np.ndarray:
    """Convert old Discrete(98304) index to MultiDiscrete [6,64,16,16]."""
    ct_idx = action // (64 * 256)
    remainder = action % (64 * 256)
    unit_idx = remainder // 256
    target_idx = remainder % 256
    gx = target_idx % 16
    gy = target_idx // 16
    return np.array([ct_idx, unit_idx, gx, gy], dtype=np.int64)

@staticmethod
def md_to_discrete(action: np.ndarray) -> int:
    """Convert MultiDiscrete [6,64,16,16] to old Discrete(98304) index."""
    ct_idx, unit_idx, gx, gy = int(action[0]), int(action[1]), int(action[2]), int(action[3])
    target_idx = gy * 16 + gx
    return ct_idx * (64 * 256) + unit_idx * 256 + target_idx
```

### 2.4 Action Mask 适配

MultiDiscrete 下 action mask 变为 **per-dimension boolean mask**：

```python
# ActionMaskRTS 适配 — 从 (98304,) bool → 4-tuple of per-dim masks
def _compute_mask_md(self, obs) -> dict[str, np.ndarray]:
    """
    Returns:
        {
            "cmd_mask":   np.ndarray shape (6,),  dtype bool
            "unit_mask":  np.ndarray shape (64,), dtype bool
            "grid_mask":  np.ndarray shape (16, 16), dtype bool  # or (256,) flattened
        }
    """
    # 1. unit_mask: alive P1 entities
    unit_indices = self._alive_p1_indices(obs)
    unit_mask = np.zeros(64, dtype=np.bool_)
    unit_mask[unit_indices] = True

    # 2. cmd_mask: 所有 cmd 对有效 unit 均可用（简化）
    cmd_mask = np.ones(6, dtype=np.bool_)

    # 3. grid_mask: 所有 target 格子均可用（简化）
    grid_mask = np.ones((16, 16), dtype=np.bool_)

    # 高级：可按 cmd_type 条件 mask
    # e.g. gather/attack/train/noop 不需要 target → 可设 grid_mask 为 True
    # move/build 需要 target → 可根据地图障碍物 mask 特定格子

    return {"cmd_mask": cmd_mask, "unit_mask": unit_mask, "grid_mask": grid_mask}
```

**sb3 兼容说明：**

- `sb3` PPO/DQN 原生支持 `MultiDiscrete` action space
- `sb3-contrib` MaskablePPO 不直接支持 MultiDiscrete mask，需要自定义  
  但标准 PPO + MultiDiscrete 可直接训练，Categorical policy 会为每个维度输出独立分布
- 推荐：**先走标准 sb3 PPO + MultiDiscrete（无需 mask）**，后续按需加 mask

---

## 3. 进一步降维方案（可选）

### 3.1 方案 B：条件编码 MultiDiscrete

利用"4/6 命令无需 target"的事实：

```python
# 当 cmd_type ∈ {gather, attack, train, noop} 时，action 仅需 [cmd, unit]
# 当 cmd_type ∈ {move, build} 时，action 需要 [cmd, unit, gx, gy]
# → 无法用单一 MultiDiscrete 表达，需要条件分支
# → 可用 spaces.Dict + 分支处理，但 sb3 不原生支持 Dict action
```

**结论：方案 B 复杂度高、sb3 兼容差，不推荐。**

### 3.2 方案 C：缩减 unit 维度

实际对局中 P1 通常只有 10-20 个单位，64 维度浪费：

```python
# 动态裁剪：仅对 alive P1 entities 编号 0..N-1
# → 需要动态 action space → sb3 不支持
# → 固定裁剪：nvec=[6, 32, 16, 16] = 49152，减半
```

**可行但有风险：超过 32 个单位时 index 越界需 fallback。暂不采用。**

### 3.3 方案 D：更粗粒度 target 网格

```python
# 8×8 网格 → nvec=[6, 64, 8, 8] = 6×64×64 = 24576
# 每格 8 世界单位，精度下降但空间减少 4×
```

**精度损失评估：** MAP_SIZE=64, 8×8 每格 8 单位，move 定位精度 ±4 → 可能影响微操。  
**推荐：** 可作为后续 ablation 选项。

---

## 4. 推荐实施计划

### Step 1：添加 MultiDiscrete 环境变体

```python
# simcore/gym_env.py

class RTSSimCoreEnvMD(RTSSimCoreEnv):
    """MultiDiscrete action space variant for sb3 compatibility."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_space = spaces.MultiDiscrete(nvec=[6, 64, 16, 16])

    def step(self, action: np.ndarray):
        commands = self._decode_action_md(action)  # new method
        # ... rest identical to parent
```

### Step 2：注册新环境

```python
gym.register(
    id="rts-ai-md-v0",
    entry_point="simcore.gym_env:RTSSimCoreEnvMD",
    max_episode_steps=10000,
)
```

### Step 3：适配 ActionMaskRTS

```python
class ActionMaskRTSMultiDiscrete(gym.Wrapper):
    """Per-dimension action mask for MultiDiscrete."""

    def _compute_mask(self, obs) -> dict[str, np.ndarray]:
        # 返回 per-dim bool mask
        ...
```

### Step 4：sb3 训练脚本

```python
from stable_baselines3 import PPO

env = gym.make("rts-ai-md-v0")
env = FlattenRTSObs(env)
model = PPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=1_000_000)
```

---

## 5. API 签名总结

```python
# ─── 核心 API ─────────────────────────────────────────────

class RTSSimCoreEnvMD(gym.Env):
    """
    MultiDiscrete action space: nvec=[6, 64, 16, 16]
    
    action[0] ∈ {0..5}  → cmd_type: move/gather/attack/build/train/noop
    action[1] ∈ {0..63} → unit_idx: index into sorted entity_ids list
    action[2] ∈ {0..15} → target_grid_x: coarse X coordinate
    action[3] ∈ {0..15} → target_grid_y: coarse Y coordinate
    
    Total combinations: 6 × 64 × 16 × 16 = 98,304 (same as Discrete)
    """
    
    action_space: spaces.MultiDiscrete  # nvec=[6, 64, 16, 16]
    observation_space: spaces.Dict     # same as parent
    
    def step(self, action: np.ndarray) -> tuple[
        dict[str, np.ndarray],  # obs
        float,                   # reward
        bool,                    # terminated
        bool,                    # truncated
        dict[str, Any],          # info
    ]:
        ...

    @staticmethod
    def discrete_to_md(action: int) -> np.ndarray:
        """Discrete(98304) → MultiDiscrete [6,64,16,16]"""
        ...

    @staticmethod
    def md_to_discrete(action: np.ndarray) -> int:
        """MultiDiscrete [6,64,16,16] → Discrete(98304)"""
        ...
```

---

## 6. 关键发现与结论

1. **当前 `_encode_action` 不存在**，只有 `_decode_action`；编码隐含在 `Discrete.sample()`
2. **target 维度 75% 浪费**：6 命令中仅 move/build 用 target，gather/attack 自动选最近，train/noop 完全不用
3. **MultiDiscrete nvec=[6,64,16,16]** 是最安全的第一步：同组合数、语义清晰、sb3 原生支持
4. **action mask 从 98304-dim bool → 4 个 per-dim bool 数组**，大幅降低 mask 计算开销
5. **后续可按需降维**：8×8 grid → 24576 组合，32 units → 49152 组合
