---
name: scope-check
description: "评估功能请求是否超出当前里程碑范围。防止范围蔓延。"
argument-hint: "[feature-description]"
user-invocable: true
allowed-tools: Read, Glob, Grep
---

当此 skill 被调用时：

1. 读取当前里程碑范围定义
2. 评估功能请求:
   - 属于哪个里程碑？
   - 与核心闭环的关系？
   - 如果纳入，影响什么？
3. 给出结论: IN / DEFERRED / SPLIT
4. 如果 DEFERRED，建议替代方案
