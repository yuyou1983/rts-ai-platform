# 四层架构设计

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      Pipeline (工具链)                       │
│  地图/单位/技能/关卡/美术/构建/部署/数据回流                    │
├─────────────────────────────────────────────────────────────┤
│                      Harness (训练验证)                      │
│  BuildRunner | MatchScheduler | SimulationPool              │
│  ReplayParser | MetricsAggregator | ExperimentRegistry      │
│  PromotionGate                                              │
├─────────────────────────────────────────────────────────────┤
│                     AgentHub (Agent运行)                     │
│  M0: BaselineAgent (单体脚本)                                │
│  M1: Coordinator → Economy + Combat                         │
│  M2: Coordinator → Strategy + Economy + Combat + Scout + Build│
├─────────────────────────────────────────────────────────────┤
│                      SimCore (仿真内核)                       │
│  规则引擎 | 状态管理 | 命令处理 | 回放系统 | 协议层             │
└─────────────────────────────────────────────────────────────┘
```

## 关键架构决策

### ADR-1: 运行时 Agent 渐进式拆分

**决策**: M0 用单体 BaselineAgent，M1 拆三核心，M2 全六 Agent。

**理由**: 过早拆分 Agent 会让 SimCore 的 AgentHub 接口陷入先有鸡还是先有蛋的困境。M0 只需要证明"采集-生产-进攻-防守"循环可闭环，单体脚本 AI 足够。只有当训练需要多策略独立进化时才拆分。

**后果**: AgentHub 接口需要版本化 (v0/v1/v2)，确保 M0 的单体接口不被 M1 的多 Agent 接口破坏。

### ADR-2: 协议隔离 (Protocol Barrier)

**决策**: 所有 Agent 只能通过 obs/cmd 协议层抽象访问 SimCore，不直接耦合 State 对象。

**理由**: RTS 的 Agent 类型差异极大 (RL 策略网络 vs 行为树 vs LLM 低频规划)，如果让任何一种 Agent 直接访问引擎对象，协议就会被逐步侵蚀。

**后果**: 协议版本管理成为核心工程约束。新增字段用 optional，删除字段用 deprecated，修改类型必须创建新版本。

### ADR-3: LLM 不进高频环

**决策**: LLM 只用于离线规划、策划辅助、回放解释、测试编排；线上决策用蒸馏后的小模型或策略网络。

**理由**: RTS 动作空间大、层级多、局部交战高频。5-10Hz 的实时控制主环放入 LLM 会导致：延迟超标 (p95 > 80ms)、成本失控、策略漂移。SC2LE 已明确 RTS 的时间尺度和动作空间不友好 LLM。

**后果**: 需要模型蒸馏管线 (LLM → 小分类器/意图模型)，这是 M2 的关键基础设施。

## 第一层: SimCore (可训练仿真内核)

### 核心职责
- 游戏规则执行
- 状态管理和快照
- 命令解析和执行
- 回放录制和重现
- 协议抽象层

### 设计原则
1. **仿真内核与表现层解耦**: 2D 与 3D 共用同一套规则、状态、命令与回放协议
2. **确定性**: 相同 seed 可复现相同对局
3. **协议优先**: 所有 Agent 只看到协议层抽象，不耦合引擎对象

### 核心模块

```
SimCore/
├── Rules/           # 规则引擎
│   ├── Combat/      # 战斗规则
│   ├── Economy/     # 经济规则
│   ├── Tech/        # 科技规则
│   └── Movement/    # 移动规则
├── State/           # 状态管理
│   ├── Snapshot/    # 快照系统
│   ├── Delta/       # 增量更新
│   └── Validation/  # 状态校验
├── Command/         # 命令处理
│   ├── Parser/      # 命令解析
│   ├── Executor/    # 命令执行
│   └── Validator/   # 命令校验
├── Replay/          # 回放系统
│   ├── Recorder/    # 回放录制
│   ├── Player/      # 回放播放
│   └── Validator/   # 回放校验
└── Protocol/        # 协议层
    ├── obs/         # 观察协议
    └── cmd/         # 命令协议
```

## 第二层: AgentHub (Agent运行层)

### 渐进式架构

```
M0: BaselineAgent
    ├── 状态机: OPENING → ECONOMY → MILITARY → END_GAME
    ├── 规则优先级: 战斗安全 > 供给阻塞 > 经济 > 军事 > 进攻
    └── 通过 obs.world.v1 + cmd.micro.v1 交互

M1: 三核心
    ├── Coordinator (仲裁 + 黑板)
    ├── Economy (obs.econ.v1 → intent.econ.v1)
    └── Combat (local.obs.v1 → cmd.micro.v1)

M2: 全 Agent + League
    ├── + Strategy, Scout, Build
    ├── League 训练
    └── OOD 泛化评测
```

### 仲裁机制
```
仲裁优先级:
1. 战斗/生存安全 (最高)
2. 供给与生产阻塞解除
3. 战略阶段目标
4. 侦察与不确定性降低
5. 低优先级扩建/补科技 (最低)
```

### 黑板系统 (M1+)
```
Blackboard:
├── global_state: 全局状态摘要
├── active_tasks: 活跃任务列表
├── resource_budget: 资源预算分配
├── intel: 情报汇总
└── decisions: 决策历史
```

## 第三层: Harness (训练验证层)

### 核心子系统

```
Harness/
├── BuildRunner/         # 构建运行器
├── MatchScheduler/      # 对局调度器
├── SimulationPool/      # 仿真池
├── ReplayParser/        # 回放解析器
├── MetricsAggregator/   # 指标聚合器
├── ExperimentRegistry/  # 实验注册表
└── PromotionGate/       # 晋升门控
```

### A/B 测试流程
```
1. Shadow → 与固定基线对打
2. Staging → 扩大对手池和地图池
3. Canary → 替换单一 Agent
4. Promote → 晋升到生产环境
```

### 质量门控
| 门控类别 | 验收标准 |
|----------|----------|
| 规则一致性 | 回放重放一致率 >= 99.5% |
| 构建稳定性 | nightly build 成功率 >= 92% |
| AI 合法性 | 非法动作率 <= 0.1% |
| 推理性能 | p95 决策延迟 <= 80ms |
| 泛化能力 | OOD 性能下降 <= 10pp |

## 第四层: Pipeline (工具链层)

### 自动化等级
| 等级 | 含义 |
|------|------|
| L0 | 完全手工 |
| L1 | 手工编辑 + 自动校验 |
| L2 | 一键导出/一键构建 |
| L3 | 自动测试 + 自动回归 |
| L4 | 闭环推荐/自动修复 |

### 核心模块
| 模块 | 核心功能 | M0 | M1 | M2 |
|------|----------|----|----|-----|
| 地图模块 | 地图编译、公平性评分 | L2 | L3 | L4 |
| 单位模块 | 单位配置、强弱曲线 | L2 | L3 | L3 |
| 技能模块 | 技能图编译、依赖检查 | - | L2 | L3 |
| 构建模块 | CI/CD、自动测试 | L3 | L3 | L4 |
| 部署模块 | 灰度发布、回滚 | - | L2 | L4 |
| 数据模块 | ETL、特征提取 | L2 | L3 | L4 |

## 数据流

```
        Pipeline                    Harness                   AgentHub                  SimCore
           │                           │                          │                         │
           │  代码/配置/模型提交         │                          │                         │
           ├──────────────────────────►│                          │                         │
           │                           │                          │                         │
           │                           │  构建 + Smoke 测试        │                         │
           │                           ├─────────────────────────►│                         │
           │                           │                          │                         │
           │                           │                          │  obs/cmd 协议交互        │
           │                           │                          ├────────────────────────►│
           │                           │                          │◄────────────────────────┤
           │                           │                          │                         │
           │                           │  回放 + 指标              │                         │
           │                           │◄─────────────────────────┤                         │
           │                           │                          │                         │
           │  数据回流 + 反馈           │                          │                         │
           │◄──────────────────────────┤                          │                         │
           │                           │                          │                         │
```

## AgentHub 接口版本矩阵

| 版本 | Agent 数量 | 架构 | 观察协议 | 命令协议 |
|------|-----------|------|----------|----------|
| v0 (M0) | 1 | 单体 Baseline | obs.world.v1 | cmd.micro.v1 |
| v1 (M1) | 3 | Coordinator + Economy + Combat | + obs.econ.v1, local.obs.v1 | + intent.econ.v1 |
| v2 (M2) | 6 | 全 Agent | + obs.fow.v1, obs.build.v1 | + plan.macro.v1, build.queue.v1, intel.report.v1 |
