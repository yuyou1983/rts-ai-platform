---
name: sprint-plan
description: "生成新 Sprint 计划或更新现有计划。基于里程碑、已完成工作和可用容量。"
argument-hint: "[new|update|status]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit
---

当此 skill 被调用时：

1. 读取当前里程碑定义
2. 读取上一个 Sprint 的速度和 carryover
3. 扫描设计文档中标记为 ready 的功能
4. 生成 Sprint 计划:
   - Sprint Goal (一句话)
   - Must Have / Should Have / Could Have
   - 容量: 总天数 - 20% buffer
   - 任务分配: 谁 + 做什么 + 预估
5. 写入 `production/sprints/sprint-[N].md`
