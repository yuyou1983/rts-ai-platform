# 项目目录结构

```
rts-ai-platform/
├── .claude/                    # Claude Code 配置
│   ├── agents/                 # Agent 定义 (开发侧)
│   │   ├── rts-test-orchestrator.md
│   │   ├── rts-balance.md
│   │   ├── rts-design-assistant.md
│   │   └── rts-replay-analyzer.md
│   ├── docs/                   # 配置文档
│   │   ├── directory-structure.md
│   │   ├── coordination-rules.md
│   │   ├── coding-standards.md
│   │   └── context-management.md
│   ├── hooks/                  # 钩子脚本
│   ├── rules/                  # 规则文件
│   ├── skills/                 # 技能定义
│   └── settings.json           # 设置文件
│
├── .agents/                    # Agent 运行时配置
│   └── skills/                 # 运行时技能
│       ├── agents/
│       ├── arbitration/
│       ├── balance-check/
│       ├── code-review/
│       ├── gate-check/
│       ├── harness-run/
│       ├── replay-analyze/
│       └── test-matrix/
│
├── agents/                     # Agent 配置 (详细)
│   ├── runtime/                # 运行时 Agent
│   │   ├── rts-coordinator/
│   │   │   ├── IDENTITY.md
│   │   │   ├── AGENTS.md
│   │   │   ├── SOUL.md
│   │   │   └── TOOLS.md
│   │   ├── rts-combat/
│   │   ├── rts-economy/
│   │   ├── rts-strategy/
│   │   ├── rts-scout/
│   │   └── rts-build/
│   └── dev/                    # 研发侧 Agent
│       ├── rts-test-orchestrator/
│       ├── rts-balance/
│       ├── rts-design-assistant/
│       └── rts-replay-analyzer/
│
├── docs/                       # 项目文档
│   ├── architecture/           # 架构设计
│   │   ├── four-layers.md
│   │   ├── agent-protocols.md
│   │   ├── arbitration-rules.md
│   │   └── blackboard-system.md
│   ├── protocols/              # 协议文档
│   │   ├── obs-protocol.md
│   │   └── cmd-protocol.md
│   └── milestones/             # 里程碑
│       ├── m0-startup.md
│       ├── m1-expansion.md
│       └── m2-productization.md
│
├── protocols/                  # 协议定义
│   ├── obs/                    # 观察协议
│   │   ├── world-v1.proto
│   │   ├── local-v1.proto
│   │   ├── econ-v1.proto
│   │   └── fow-v1.proto
│   └── cmd/                    # 命令协议
│       ├── micro-v1.proto
│       ├── macro-v1.proto
│       └── build-v1.proto
│
├── production/                 # 生产管理
│   ├── sprints/                # 冲刺计划
│   ├── gate-checks/            # 门控检查
│   ├── releases/               # 发布记录
│   └── stage.txt              # 当前阶段
│
├── scripts/                    # 工具脚本
│   ├── arbitration_engine.py
│   ├── balance_analyzer.py
│   ├── harness_scheduler.py
│   └── replay_parser.py
│
├── CLAUDE.md                   # 项目主配置
└── README.md                   # 项目说明
```

## 目录用途说明

### `.claude/` - Claude Code 配置
Claude Code 的配置目录，包含 agent 定义、技能、钩子和设置。

### `.agents/` - Agent 运行时配置
Agent 运行时使用的技能和配置，与 OpenClaw 兼容。

### `agents/` - Agent 详细配置
每个 Agent 的详细配置，包括 IDENTITY、AGENTS、SOUL、TOOLS 等文件。

### `docs/` - 项目文档
架构设计、协议文档、里程碑计划等。

### `protocols/` - 协议定义
Protobuf 定义的观察和命令协议。

### `production/` - 生产管理
冲刺计划、门控检查、发布记录等生产管理文件。

### `scripts/` - 工具脚本
仲裁引擎、平衡分析、Harness 调度、回放解析等工具脚本。