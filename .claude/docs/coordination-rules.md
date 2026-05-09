# Agent Coordination Rules

## 层级规则

1. **领导层仲裁**: 当跨域冲突无法在职能层解决时，escalate:
   - 技术冲突 → `rts-technical-director`
   - 创意冲突 → `rts-creative-director`
   - 排期/范围冲突 → `rts-producer`

2. **垂直委派**: 领导层 → 职能专家 → 实施者。复杂决策不跳层。

3. **水平协商**: 同层 Agent 可以互相咨询，但不在自己领域外做约束性决策。

## 运行时 Agent 协调 (M1+)

4. **固定仲裁优先级**: Agent 间冲突不靠 LLM 仲裁，用硬编码优先级:
   战斗安全 > 供给阻塞 > 战略目标 > 侦察 > 低优扩建

5. **黑板即真相**: 所有 Agent 通过黑板共享状态，不直接读取彼此内部状态。

6. **单次命令权**: 同一时刻，一个单位只接受一个 Agent 的命令。冲突由 Coordinator 仲裁。

## 研发侧 Agent 协调

7. **变更传播**: 设计变更影响多域时，`rts-producer` 协调传播。

8. **无跨域擅自修改**: Agent 不修改自己指定目录外的文件，除非显式委派。

9. **Team Skill 编排**: 多 Agent 协作必须通过 team-* skill 编排，不自由组合。

## 审批流

10. **文件写入审批**: 所有文件写入前展示草案，用户批准后执行。

11. **配置变更审批**: 任何单位/技能/地图配置变更，必须经过 `rts-design-assistant` 生成 diff + `rts-balance-analyst` 评估影响。

12. **发布审批**: 任何模型/配置晋升到 production，必须经过 `rts-test-orchestrator` 的质量门控 + `rts-producer` 的 Go/No-Go。
