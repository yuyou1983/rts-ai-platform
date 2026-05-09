---
name: architecture-decision
description: "记录架构决策 (ADR): 上下文、决策、后果。使用此 skill 进行四层架构、协议、技术选型相关决策的正式化。"
argument-hint: "[decision-title]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write
---

当此 skill 被调用时：

1. **理解决策上下文**: 读取相关架构文档和先前决策
2. **生成 ADR 文档**:

```markdown
# ADR-[N]: [决策标题]

## 状态
[提议 | 已接受 | 已废弃 | 已替代]

## 上下文
[促成此决策的背景和约束]

## 决策
[做出的选择及理由]

## 后果
[正面的和负面的影响]

## 选项考虑
| 选项 | 优势 | 劣势 | 结论 |
|------|------|------|------|

## 验证标准
[如何判断此决策是否正确]
```

3. **写入** `docs/architecture/decisions/adr-[N]-[slug].md`
4. **更新** 架构文档中的相关引用
