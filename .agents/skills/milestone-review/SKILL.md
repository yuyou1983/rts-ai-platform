---
name: milestone-review
description: "里程碑进度评审: 功能完成度、质量指标、风险评估和 Go/No-Go 建议。"
argument-hint: "[milestone-name|current]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write
---

当此 skill 被调用时：

1. 读取里程碑定义
2. 读取 Sprint 报告
3. 检查代码 TODO/FIXME
4. 检查风险登记表
5. 生成评审报告:
   - 功能完成度矩阵
   - 质量门控通过率
   - 风险状况
   - Go/No-Go 建议
