# AgentGuard 当前状态评审

> 更新时间：2026-04-16
> 适用范围：当前 MVP 收口阶段，用于同步“已经做到哪了、下一步做什么、哪些文档可作为现状基线”。

> 2026-04-19 补充：当前正式主线已经明确为 **Claude Agent SDK-first runtime + AgentGuard diagnostics-first product**。
>
> 执行约束已经明确：
> - Claude SDK 统一通过 `pip install claude-agent-sdk` 接入
> - 能用 SDK 的地方优先用 SDK，不平行重造 Claude runtime
> - 仓库必须主动精简，不能继续扩大当前宽表面

---

## 1. 当前判断

AgentGuard 当前已经从“trace viewer + 一组相关工具”进一步收口成：

**面向多 Agent 编排系统的诊断工具。**

更具体地说，它现在的产品核心已经不是“生成一份报告”，而是：

1. 用统一 trace 数据面捕获多 Agent 执行拓扑。
2. 围绕 handoff、failure propagation、context flow、decision impact 做诊断。
3. 通过 CLI 和 HTML viewer 把这些诊断交付给用户。

当前它已经具备 MVP 雏形，但还没有完全进入“外部用户一上手就会觉得成熟”的状态。

---

## 2. 当前已经完成到哪

### 2.1 核心内核

- 统一 trace 数据模型已经稳定，`ExecutionTrace` / `Span` 足以支撑当前主线功能。
- SDK 接入面已经覆盖 decorator、context manager、manual、middleware、async、distributed。
- `agentguard.configure(...)` 已经成为面向产品的统一入口，默认落盘路径和线程行为可配置。

### 2.2 编排诊断语义

当前五个核心问题已经有实质覆盖：

1. 哪个节点是 bottleneck：已支持 critical path + own-work 语义。
2. 哪个 handoff 丢了信息：已支持 inferred / explicit handoff loss 分析，并新增 semantic retention 评分、critical context 显式标注与启发式识别，用来区分“正常摘要压缩”和“关键语义明显损失”；最近又补上了保守的 downstream impact 归因，在 handoff 本身已可疑时继续看 receiver subtree 是否出现 failure 或明显质量退化。
3. 哪个 failure 开始向下游传播：已支持 causal chain / containment 分析。
4. 哪条路径 cost 高但 yield 差：已支持 cost-yield 分析，并开始优先使用 output / metadata 中的显式质量信号（如 quality、score、confidence、verdict），同时能吸收 evaluation / replay / comparison 结果结构，而不再只靠 output size 近似判断 yield；最近又补上了 critical path / handoff chain 级别的路径聚合，开始直接给出 worst path，而不只停留在单个 agent。
5. 哪个 orchestration decision 导致降级：已支持 decision impact、suggestion、counterfactual，并且 counterfactual 已进入主分析路径，开始基于代表性替代路径而不是单次“幸运运行”给出更保守的判断。

### 2.3 产品路径

- 并行示例已经切到更自然的标准线程路径。
- Evolution 已经不再只是 README 能力词，而是有 CLI、viewer、example、knowledge base 的产品路径。
- HTML prototype 已可由当前代码真实生成，不再依赖手写静态 mock。

### 2.4 测试与示例

- 已有大量单测、集成测试和 subprocess 级 CLI 测试。
- 已补 realistic examples：parallel pipeline、parallel coding、multi-hop RAG、evolution loop、MVP HTML prototype。

---

## 3. 当前主要问题

### 3.1 Q2 / Q4 的“诊断可信度”仍然是 MVP 第一优先级

当前最需要继续收口的，不是再多做几个面板，而是让用户相信这些诊断结论值得采纳。

其中：

- Q2 虽然已经从 keys lost 提升到 semantic retention + downstream impact，但还可以继续加强“哪些信息是关键语义”的识别与归因力度
- Q4 已经从单纯 output / size / success 启发式进一步推进到“显式质量信号优先 + evaluation/replay 结果吸收 + 路径级聚合”，但离“真正的任务结果质量”仍有距离

也就是说，**当前最重要的问题不是“看起来够不够像产品”，而是“结论够不够可信”。**

### 3.2 文档刚做完一轮收口，但仍需要把 current state 变成持续维护对象

当前仓库需要一个持续更新的状态基线，而不是多份并行的方向草稿。

本文件应继续承担这个角色：

- 同步当前产品边界
- 同步已完成能力和主要风险
- 同步下一阶段的收口重点

### 3.3 并行 / distributed 路径仍有后续深化空间

当前已支持：

- TraceThread / auto thread context
- TracingExecutor / traced_task
- TracingProcessExecutor
- distributed merge
- LangChain integration + generic middleware wrapping

但还缺少更“默认即好用”的产品闭环：

- process pool / framework integration 还没有进入主 README 叙事中心
- 缺少更贴近真实产品接入的 end-to-end 示例
- 还没有把不同并行 / 分布式接入路径总结成一套用户容易选型的推荐路径

### 3.4 Viewer 与 README 仍需继续对齐，但优先级低于能力收口

当前 README 的视觉承诺和产品表达方向是对的，但 viewer 视觉本体还需要继续打磨，避免再次形成“截图领先实现”的感觉。

### 3.5 当前最大的结构性问题已经从“功能缺口”转向“runtime 主线还在收口”

现在更大的问题不是还缺一个分析面板，而是：

- AgentGuard 当前仍然把自研 instrumentation 作为主接入路径
- Claude Agent SDK 已经开始稳定暴露 subagent hooks、session helpers、trace context propagation 等真实 runtime 能力
- 如果不调整主线，后续每一轮都还会在“重复实现运行时”上消耗掉诊断产品的精力

因此下一阶段应该继续收口到：

- **Claude Agent SDK-first, AgentGuard analysis-first**

### 3.6 当前仓库的另一个结构性问题是“代码与 API 面过宽”

除了 runtime 主线不对，当前仓库还有一个已经无法回避的问题：

- 顶层模块数量过多
- `agentguard/__init__.py` 暴露面过大
- CLI 命令面过宽
- README 和示例要同时解释多套接入风格，认知负担过高

这意味着不能只是在现有宽表面上再叠一层 Claude integration。

仓库必须继续收窄成：

- 小而稳定的 public API
- 小而清晰的主线目录结构
- 小而清楚的接入叙事

---

## 4. 当前阶段目标

当前阶段不是继续横向堆能力，而是把 MVP 真正收口成“可信产品原型”。

### Goal 1：把 Q2 / Q4 收口成用户可信的诊断能力

目标：

- Q2 不只告诉用户“哪些键丢了”，而是更稳定地区分摘要、过滤、截断、关键语义损失，并开始回答这些损失是否真的在下游造成失败或质量退化
- Q4 不只告诉用户“花了多少 token”，而是更合理地衡量产出质量与成本是否匹配，并开始指出哪条执行路径最浪费
- 让 `analyze` 输出更接近“可直接拿来决策”的产品诊断

### Goal 2：把 current state 作为持续维护文档固定下来

目标：

- 任何人打开仓库，都能快速知道当前做到哪一步
- 不需要翻聊天记录才能理解当前主线

### Goal 3：把例子分层并补齐接入选型闭环

目标：

- 最小接入例子：看 SDK 易接入性
- MVP prototype 例子：看产品页面结果
- RAG / parallel / distributed 例子：看诊断能力边界与接入路径差异

### Goal 4：Viewer 继续产品化，但放在能力之后

目标：

- 时间轴更清楚
- sidebar / diagnostics 更一致
- 页面更接近 README 截图的品质

### Goal 5：保持产品边界不漂移

目标：

- 不退回通用 observability 平台叙事
- 不让 reliability 外圈能力继续抢主线

### Goal 6：完成 Claude Agent SDK-first 主运行时收口

目标：

- 保留现有 trace / analysis 资产
- 把 Claude runtime 事件源变成新的主接入路径
- 把自研 SDK 降级为 fallback / compatibility path

### Goal 7：在当前主线下完成仓库精简

目标：

- 缩小顶层模块数量
- 缩小 `agentguard/__init__.py` 导出面
- 缩小主 CLI 命令面
- 把不再属于主线的代码移入 `legacy/` 或移除

---

## 5. 当前任务拆解

下面这份 task list 更适合作为“接下来每一步该做什么”的执行清单。

### Phase A：文档与状态基线

- ✅ 清理过时静态 prototype 文档
- ✅ 修正 getting-started / tutorial / configuration / API reference 的明显 drift
- ✅ 修复 examples 文档结构问题并补上 MVP prototype 例子
- ✅ 把 current state 文档更新成可持续维护版本

### Phase B：Viewer 产品化

- ✅ 修复 viewer 模板输出失效导致的 CSS / JS 全局退化问题
- ⏳ 重做 viewer 的视觉层级和版式细节
- ⏳ 继续对齐 README 截图与当前真实输出

### Phase C：能力准确性收口

- ✅ Q5 counterfactual 进入主分析路径，并改为基于代表性替代路径做更保守判断
- ✅ Q2 新增 semantic retention 评分，开始区分摘要压缩与真实语义损失
- ✅ Q2 支持 critical context 显式标注与启发式识别，关键字段丢失会被单独放大和解释
- ✅ Q2 已开始为可疑 handoff 补充 downstream impact 信号，把 receiver subtree 的 failure / 质量退化折回 handoff 诊断
- ✅ Q2 已开始按 risk 排序高风险 handoff，并把这层优先级直接暴露到 CLI / viewer，而不只停留在 JSON 字段
- ⏳ 继续提升 Q2 对“关键语义丢失”的识别力度
- ✅ Q4 默认 cost-yield 已开始优先吸收显式质量信号，低质量大输出不会再天然被判高 yield
- ✅ Q4 已开始吸收 evaluation / replay / comparison 结果结构，把规则失败与 regression verdict 纳入默认 yield 判断
- ✅ Q4 已开始按 critical path / handoff chain 聚合路径级 cost-yield，并在 CLI 中直接暴露 worst path
- ⏳ 继续提升 Q4 对“任务结果质量”的真实性判断

### Phase D：产品示例闭环

- ✅ Multi-hop RAG example
- ✅ Evolution loop example
- ✅ MVP HTML prototype example
- ⏳ 增加更强的 parallel / distributed prototype 对照页

### Phase E：并行 / 分布式体验深化

- ✅ auto thread context
- ✅ TracingExecutor / traced_task
- ✅ TracingProcessExecutor
- ✅ distributed merge hardening
- ✅ LangChain callback integration
- ✅ generic middleware wrapping / patching
- ⏳ 补 process pool / framework middleware 的产品叙事、选型建议与更真实的示例闭环

### Phase F：Claude Agent SDK-first 主运行时

- ✅ 明确 Claude runtime 为主接入路径
- ✅ 明确 SDK 接入策略：使用 `pip install claude-agent-sdk`，不拉 SDK 源码仓库
- ✅ 已有 Claude session / subagent transcript importer
- ✅ 已有 Claude hooks / runtime message -> span bridge 第一版
- ✅ 已开始接入 context usage / richer result metadata
- ⏳ 再做 W3C trace context / OTel bridge

### Phase G：仓库瘦身

- ⏳ 把 analysis/flow/scoring/timeline/tree 等主分析资产迁入新的 `diagnostics/` 结构
- ⏳ 把 runtime/importer 路径迁入新的 `runtime/` 结构
- ⏳ 把旧 SDK、长尾命令和非主线模块统一收进 `legacy/`
- ⏳ 重写 README / architecture / API reference，停止继续解释旧的宽表面结构

---

## 6. 当前推荐阅读顺序

如果要快速理解仓库当前状态，建议按下面顺序看：

1. [README.md](../README.md)
2. [docs/getting-started.md](./getting-started.md)
3. [docs/current-state-review-zh.md](./current-state-review-zh.md)
4. [docs/examples.md](./examples.md)
5. [docs/architecture.md](./architecture.md)

如果要理解当前 SDK 边界和正式产品方向，优先看：

1. [docs/architecture.md](./architecture.md)
2. [docs/api-reference.md](./api-reference.md)

---

## 7. 当前结论

当前 AgentGuard 已经具备下面这些特征：

- 核心方向清楚
- MVP 语义已经成型
- SDK 接入已经足够低侵入
- 诊断层已经不只是“看 trace”，而是开始回答编排问题

但距离“成熟产品感”仍然差最后一段：

- Q2 / Q4 的诊断可信度继续收口
- 文档持续收口
- 示例分层与对外展示一致性
- viewer 视觉质量

因此，当前最合适的判断不是“还只是 demo”，也不是“已经完全 ready”，而是：

**已经进入可信 MVP 阶段，接下来重点是完成产品化收口。**
