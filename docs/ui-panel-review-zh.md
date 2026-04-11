# AgentGuard 示例 UI 面板评审

> 日期：2026-04-11
> 目的：对当前示例 Web 面板做一次中文评审，重点从信息架构、视觉表达、产品定位匹配度与后续演进方向进行整理。

---

## 1. 先说结论

当前示例面板已经是一个**合格的本地 trace viewer**，但还不是一个足够有辨识度的**多 Agent 编排层可观测性面板**。

也就是说，它已经能承担：

- 本地查看 traces
- 快速了解执行树
- 作为 README 截图展示基础能力

但它还没有充分体现出 AgentGuard 最应该强调的差异化价值：

- 编排层 timeline
- handoff 语义
- failure propagation
- context flow
- orchestration diagnostics

如果以后希望让这个项目更贴近“多 Agent 编排层可观测性”的定位，这个面板需要从“trace list + tree viewer”继续往“编排分析面板”升级。

---

## 2. 当前面板概况

相关实现文件：

- [agentguard/web/viewer.py](../agentguard/web/viewer.py)

相关截图：

- [docs/screenshots/web-report-hero.png](./screenshots/web-report-hero.png)
- [docs/screenshots/web-report-full.png](./screenshots/web-report-full.png)

当前界面大致由三部分组成：

1. 页面顶部标题区
2. 总览统计卡片区
3. Trace 卡片列表与展开树形详情区

从实现上看，它采用单文件 HTML + 内嵌 CSS/JS 的方式生成，属于典型的 local-first 报告页面，符合项目当前“无复杂前端依赖”的基调。

---

## 3. 现在做得好的地方

### 3.1 信息结构清楚

当前界面的层次比较顺：

- 先看总体统计
- 再看 trace 列表
- 再点开具体 trace 看执行树

这条阅读路径符合用户排查问题的基本顺序，成本低，认知负担也不大。

### 3.2 作为本地调试视图已经足够实用

对于一个本地 HTML 报告来说，它已经满足了“打开就能看”的基本诉求：

- 不需要服务端
- 不需要前端构建
- 不需要数据库
- 可以直接截图

这点很适合开源第一版和本地调试场景。

### 3.3 树形执行关系表达直接有效

展开后的层级结构能较快说明：

- 哪个 agent 是父节点
- 哪些 tool 属于哪个 agent
- 每个节点的状态和耗时

这和当前 trace 的数据模型是统一的，也说明 `trace -> UI` 的映射成本很低。

### 3.4 视觉语言比较克制

目前的视觉风格偏工程工具：

- 暗色背景
- 低饱和边框
- 简洁统计卡片
- 小型状态 badge

这使得页面不会显得花哨，适合调试和内部使用。

---

## 4. 主要问题

### 4.1 它更像 trace viewer，不像 orchestration panel

这是当前最核心的问题。

页面的主视觉对象仍然是：

- 一组 trace 卡片
- 一个展开的执行树

这意味着它强调的是“某次执行里有哪些 span”，而不是“多个 Agent 是如何协作完成这次任务的”。

换句话说，它更多在展示**执行记录**，还没有开始展示**编排关系**。

### 4.2 时间信息没有真正被可视化

虽然页面右侧有 duration 数字，但这不是强 timeline。

现在用户仍然很难一眼看出：

- 哪些步骤是串行的
- 哪些步骤是并行的
- 哪个 agent 是关键路径上的瓶颈
- 总耗时主要消耗在哪一段

对于“可观测性面板”来说，这一点尤其重要。

### 4.3 编排层语义太弱

当前 UI 展示的是：

- 名称
- 状态
- 耗时
- 层级

但没有明确表达：

- handoff
- fallback
- failure propagation
- context loss
- 重试或降级路径

而这些恰恰是 AgentGuard 如果想做出差异化，最应该被看见的内容。

### 4.4 总览指标偏通用，不够贴近编排诊断

顶部卡片现在展示：

- Traces
- Total Spans
- Passed
- Failed
- Avg Duration

这套指标没有错，但它更像“通用 trace dashboard”，而不是“多 Agent 编排分析面板”。

更贴近项目方向的指标应该逐步包括：

- agent 数量
- 最慢 agent
- 关键路径长度
- failed handoff 数
- failure source agent
- fallback / retry 次数
- longest chain

### 4.5 传播力一般

从截图传播效果看，这个界面是整洁的，但记忆点还不够强。

它能让人知道“这是一个暗色工程面板”，但还不容易让人一眼感知：

**这是一个专门解决多 Agent 编排层问题的工具。**

如果将来希望它承担更多开源传播作用，视觉重点需要更明确地落在“协作关系”和“诊断价值”上。

---

## 5. 与项目方向的匹配度

如果把项目定位为：

**面向多 Agent 协作系统的编排层可观测性**

那么当前面板的匹配度可以概括为：

- 与“本地 trace 可视化”高度匹配
- 与“多 Agent 编排层诊断”中等匹配
- 与“handoff / propagation / context flow”低匹配

也就是说，当前面板更接近第一阶段能力：

**把执行过程看清楚**

但离第二阶段能力还有距离：

**帮助定位编排问题**

---

## 6. 评分

如果从几个维度给一个相对直接的评分，我会这样看：

### 6.1 工程可用性

`7.5 / 10`

它已经是一个可工作的本地 HTML 报告，结构清楚，足够轻量，也便于接入当前项目。

### 6.2 信息清晰度

`7 / 10`

用户能较快理解页面在展示什么，但仍然需要靠阅读数字和层级关系来推理执行过程。

### 6.3 与项目定位的匹配度

`6 / 10`

它还没有充分体现“多 Agent 编排层 observability”的差异化，只是基本完成了 trace 可视化。

### 6.4 传播展示力

`5.5 / 10`

截图足以说明“有个面板”，但还不足以成为让人一眼记住项目定位的核心展示物。

---

## 7. 最值得优先改的方向

### 7.1 从“树”升级为“树 + 时间轴”混合视图

这是最值得优先推进的一步。

用户需要的不只是层级结构，还需要明确看到：

- 谁先执行
- 谁后执行
- 谁并行
- 谁阻塞了整体流程

建议在每个 trace 中引入更明显的 timeline 表达，而不是只在右侧显示 duration 数字。

### 7.2 给每个 trace 增加编排摘要

每张 trace 卡片展开前，就应该给用户一眼可读的诊断摘要，例如：

- 最慢 agent
- 首个失败点
- 是否发生 fallback
- 是否存在 failure propagation
- 关键路径耗时

这样 UI 才会从“日志列表”往“诊断面板”升级。

### 7.3 把 handoff 变成一等公民

当前 UI 里的关系主要靠树缩进表达。

如果项目后续重点是 orchestration observability，那么 handoff 不应该隐含在父子层级里，而应该能被显式展示：

- 从哪个 agent 交给哪个 agent
- handoff 时带了什么上下文
- handoff 后是否成功

### 7.4 强化失败传播表达

失败不能只是一个红色 badge。

更重要的是：

- 失败源头是谁
- 哪些节点只是被上游拖垮
- 哪些节点做了 graceful degradation
- 哪些路径因为失败被跳过或重试

只要这部分表达出来，界面的“工程价值感”会明显提升。

### 7.5 调整总览指标

建议逐步把顶部总览从通用指标改成更贴近 orchestration 的指标组合，例如：

- Traces
- Agents
- Failed Handoffs
- Critical Path Avg
- Slowest Agent
- Retry / Fallback Count

这样总览层就会更贴近项目真实定位。

---

## 8. 一个更合适的演进顺序

为了避免一次性重做过多内容，建议按下面顺序演进：

### Stage 1：增强当前面板的信息密度

目标：不改整体结构，只增强可读性。

建议事项：

1. 增加 trace 摘要信息。
2. 强化失败源头与最慢节点标记。
3. 补充更贴近 orchestration 的顶部指标。

### Stage 2：引入时间轴表达

目标：让面板真正具备 timeline 意义。

建议事项：

1. 在展开区域中用横向条带表示 span 时间分布。
2. 支持视觉区分并行和串行步骤。
3. 明确突出 critical path。

### Stage 3：引入编排诊断语义

目标：从“显示执行过程”升级为“帮助定位问题”。

建议事项：

1. 展示 handoff。
2. 展示 failure propagation。
3. 展示 fallback / retry / degrade 等路径。
4. 尝试加入 context flow 的摘要或异常提示。

---

## 9. 总结

当前示例 UI 面板已经完成了它最基础的任务：

**让 AgentGuard 有一个能工作的、本地优先的、多 Agent trace 可视化入口。**

这是一个合格的起点。

但如果项目接下来希望真正站稳“多 Agent 编排层可观测性”这个定位，那么这个面板还需要继续往下走两步：

1. 从 trace viewer 升级为 orchestration viewer。
2. 从 orchestration viewer 升级为 orchestration diagnostics panel。

只有这样，它才会从“看起来有个 dashboard”变成“真正体现项目方向和工程价值的核心展示面”。