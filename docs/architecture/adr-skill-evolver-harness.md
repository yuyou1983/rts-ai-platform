# SkillEvolver 架构决策记录 (ADR)

## 状态: Proposed

## 上下文

当前 `.agents/skills/` 下有 ~20 个 skill，但缺少：
- 标准化元数据 (primary_action, validation_commands, known_failure_modes)
- 执行轨迹审计 (skill 是否被真正读取、primary script 是否被调用)
- 自动进化机制 (对比成功/失败轨迹，生成 skill patch)
- 独立审计 gate (防止 skill 直接修改业务代码)

论文 "Skill Evolution via Contrastive Trace Analysis" 提供了可审计、可复用、可进化的开发技能系统框架。

## 决策

### SkillEvolver 作用域

**允许 (✅)**
- `.agents/skills/*` — skill 元数据与内容修改
- `harness/skills/*` — skill registry, schema, candidates
- `harness/trace/*` — 执行轨迹记录与分析
- `harness/evolve/*` — skill_evolver.py 及其验证脚本
- `harness/memory/procedures/*` — 从 skill evolution 产出的可复用流程
- `agents/prompts/*` — 策略知识库的 prompt 文件
- `agents/runtime/playbooks/*` — runtime agent 消费的配置文件

**禁止 (❌)**
- 直接修改 `simcore/` 规则代码
- 直接修改训练权重 (`*.pt`, `*.pth`, `*.safetensors`)
- 直接修改 `godot/scripts/` runtime 逻辑
- 在 skill 中硬编码 entity ID、seed、文件路径
- 让 `.agents/skills/` 直接参与每 tick LLM 决策

**间接影响 (⚠️)**
- SkillEvolver 可输出建议 patch → 走正常 `harness-executor` → 测试通过后才合入业务代码
- 训练数据可引用 skill evolution 的失败轨迹作为 evidence

### 四层架构约束

Runtime architecture follows AGENTS.md:
L0) Proto (`proto/`)
L1) SimCore (`simcore/`)
L2) Agents (`agents/`)
L3) Frontend/Godot (`godot/`)

SkillEvolver itself is dev-harness infrastructure. It can read runtime code for diagnosis, but promoted skill patches must target `.agents/skills/` or `harness/` unless a separate harness-executor task is opened for business-code changes.

### Silent-Bypass 检测

Skill 中的规则如果满足以下条件之一，标记为 silent-bypass：
1. "必须/永远/不要" 规则，但没有 `validation_commands` 或 `expected_tool_calls` 证明其被遵循
2. `primary_action` 声明了但轨迹中从未出现对应 tool call
3. Skill 引用了不存在的 `primary_script` 路径

## 后果

- 正面：Skill 变为可审计、可复用、可进化的开发资产
- 正面：减少 Hermes/Codex 重复推理相同任务
- 负面：增加 harness 基础设施维护成本
- 负面：需要 held-out validation 防止 skill 过拟合
