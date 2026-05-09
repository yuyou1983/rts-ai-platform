---
name: estimate
description: "估算任务工作量: 最佳/最可能/最差三值估算。"
argument-hint: "[task-description]"
user-invocable: true
allowed-tools: Read, Glob, Grep
---

当此 skill 被调用时：

1. 理解任务范围
2. 扫描相关代码/文档
3. 给出三值估算:
   - Optimistic: [X] 天
   - Most Likely: [Y] 天
   - Pessimistic: [Z] 天
   - Expected (PERT): (O + 4M + P) / 6
4. 列出估算假设和风险
