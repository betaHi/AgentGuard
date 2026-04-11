# AgentGuard 示例 UI 面板评审

> 日期：2026-04-11
> 目的：对当前示例 Web 面板做一次中文评审，重点从信息架构、视觉表达、产品定位匹配度与后续演进方向进行整理。

---

## 1. 先说结论

当前示例面板已经从“合格的本地 trace viewer”继续往前走了一步，开始具备**多 Agent 编排诊断面板**的雏形。

相比上一轮评审，它已经新增了：

- 更贴近编排层的顶部指标
- 每个 trace 的诊断摘要
- 更明显的 handoff 与 failure propagation 表达
- 简化版的时间条表达

这说明产品方向是在收敛的，UI 也确实开始向“多 Agent 编排层可观测性”靠拢。

但当前最大的剩余问题已经从“界面表达太弱”变成了：

**Web 面板里的诊断语义正在和分析层分叉。**

也就是说，问题不再主要是“看起来不像”，而是“显示出来的诊断结论是否和系统内部统一分析逻辑一致”。

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

如果以后希望让这个项目真正稳定地承担“多 Agent 编排层可观测性”的核心展示面，这个面板下一步最应该解决的是：

- 统一诊断来源
- 明确时间与关键路径语义
- 避免 UI 自己再发明一套和分析层不同的规则

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

---

## 10. 2026-04-12 增量评审

在 rebased `main` 上重新查看后，当前 UI 已经相较上一篇评审明显升级：

- 页面标题与 README 叙事已经统一到 `Multi-Agent Orchestration` 方向。
- 顶部指标不再只有通用 trace 指标，而是开始加入 `Agents` 和 `Slowest Agent`。
- trace 展开区新增了诊断标签，如 handoffs、fallback、failure propagation、slowest、first fail。
- span 右侧新增了简化版的相对时间条，时间信息比之前更容易扫读。
- 截图展示力比早期版本更强，至少已经能看出“这不是普通 trace list”。

这部分说明方向是对的，UI 升级也不是表面修饰，而是确实在往编排层诊断靠近。

### 10.1 当前最主要的问题

当前最值得警惕的问题，不是 UI 风格，而是**诊断语义重复实现**。

仓库已经有正式分析层：

- [agentguard/analysis.py](../agentguard/analysis.py)

它定义了：

- failure propagation 分析
- root cause / handled / unhandled
- handoff 分析
- critical path
- parallel groups

但 Web 面板当前没有直接消费这套分析结果，而是在：

- [agentguard/web/viewer.py](../agentguard/web/viewer.py)

里重新用启发式规则计算：

- `has_fallback`
- `has_propagation`
- `handoff_count`
- `first_fail`
- 局部 handoff 文本

这会带来三个直接风险。

#### 1. CLI 与 Web 的诊断语义可能分叉

CLI 的分析能力和 Web 面板看到的结论，未来可能不是同一套逻辑。

#### 2. Trace schema 的实验字段没有真正被利用

当前 trace schema 已经定义了实验字段：

- `handoff_from`
- `handoff_to`
- `context_size_bytes`
- `caused_by`
- `failure_handled`

如果以后 SDK 开始稳定写这些字段，而 Web 仍然沿用自己的一套简化推断逻辑，展示结果会越来越不准确。

#### 3. 维护成本会变高

分析规则一旦需要升级，未来很容易出现：

- 分析层修了一次
- CLI 跟了一次
- Web 还要再修一次

这种重复实现对长期演进是不利的。

### 10.2 当前具体问题

#### 10.2.1 `first fail` 取的是列表顺序，不是真正的首个失败点

当前 Web 里 `first_fail` 是按 `spans` 原始顺序取到的第一个失败项，而不是按时间排序后的首个失败点。

这意味着在以下场景下它可能误导用户：

- distributed merge 后 spans 顺序变化
- 手工构造 trace
- 外部导入 trace

如果界面要表达“第一个失败点”，就应该以时间为依据，而不是依赖列表顺序。

#### 10.2.2 handoff 表达仍然是推断性的，不是真正的 handoff 事件

当前 UI 中的 handoff 更多是：

- 同父节点下相邻 agent 的关系提示

它仍然不等同于真正的 handoff span，也没有带上上下文转移信息。

这对于当前截图演示是够用的，但对于未来产品语义来说还不够硬。

#### 10.2.3 Web 回归测试没有覆盖这些新增诊断能力

现有 `tests/test_web.py` 仍然主要验证：

- HTML 能生成
- 页面里出现了基本字符串

但没有验证：

- handoff 标签是否正确
- failure propagation 标签是否正确
- slowest agent 是否正确
- first fail 是否正确
- Web 是否与分析层结果一致

这意味着这次 UI 升级最有价值的新能力，还没有被自动化保护住。

### 10.3 这一版 UI 的重新评分

基于当前 rebased `main`，我会把评分调整为：

#### 工程可用性

`8 / 10`

已经比上一版更像真正可用的本地诊断面板。

#### 信息清晰度

`7.5 / 10`

顶部摘要和诊断标签明显提高了可读性。

#### 与项目定位的匹配度

`7 / 10`

方向已经明显向“编排层 observability”靠拢，但分析语义还未统一。

#### 传播展示力

`6.5 / 10`

截图的辨识度比之前强，但还没有强到“一眼就只能是这个产品”。

### 10.4 下一步最应该做什么

如果只做一件事，最建议的是：

**让 Web 面板直接消费分析层结果，而不是在 `viewer.py` 里再次实现一套诊断逻辑。**

最自然的顺序是：

1. 先让 `viewer.py` 调用 `analyze_failures()` 和 `analyze_flow()`。
2. 再让 UI 用统一分析结果展示 handoff、root cause、propagation、critical path。
3. 最后补上对应的 Web 回归测试。

这样改完之后，Web 才会真正从“看起来更像诊断面板”变成“和系统核心语义一致的诊断面板”。