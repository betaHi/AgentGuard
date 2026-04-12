# AgentGuard 当前状态评审

> 更新时间：2026-04-12
> 范围：当前主线实现、README、examples、analysis、viewer、并行示例语义一致性

---

## 1. 当前结论

AgentGuard 当前已经明显收敛到一个更清晰的产品方向：

- 它不是通用 LLM observability 工具。
- 它不是泛化 reliability suite。
- 它的核心价值正在逐步收敛到 multi-agent orchestration observability。

从仓库当前状态看，这个方向是成立的，而且比早期版本更稳。

当前最强的三部分是：

1. trace 数据模型已经足够像一个产品内核，而不是 demo 数据结构。
2. SDK 接入方式已经覆盖 decorator、context manager、manual、middleware、async、distributed 等主流形态。
3. analysis / viewer / examples 正在逐步围绕 handoff、failure propagation、critical path、parallel execution 形成统一叙事。

但当前仓库仍然没有完全进入“可信诊断工具”阶段，主要原因不是方向错误，而是：

**viewer 与 analysis 的语义一致性、examples 文档收口，以及并行能力的人体工学仍有几个关键缺口。**

---

## 2. 当前最重要的问题

### 2.1 viewer 与 analysis 的 bottleneck 语义还没有完全对齐

这是当前最重要的问题。

当前 analysis 已经比之前更合理：

- 不再机械地把 root coordinator 判成 100% bottleneck
- 瓶颈开始落到真正的工作节点上

这是明显进步。

但新的问题也随之出现：

- analysis 现在可能返回 tool span 作为 bottleneck
- viewer 的 sidebar 仍然主要按 agent 卡片来标记 bottleneck

这会导致一种新的语义错位：

- analysis 结果是对的
- 但 UI 没有把它正确表达出来

这说明 analysis 层已经开始领先 viewer 一步，展示层还需要继续跟上。

### 2.2 原生线程的人体工学仍然不够自然

并行示例已经开始成为仓库的重要卖点，例如 parallel pipeline / parallel coding 这类场景，方向是对的。

当前仓库已经补上了线程上下文继承能力，并且 parallel examples 也已经改成在 coordinator span 下运行，因此示例级别的 execution topology 已经恢复可信。

但这条能力目前仍然是显式能力，而不是对原生 `threading.Thread` 的无感继承：

- recorder 仍然使用 thread-local span stack
- Python 原生线程不会自动继承这个上下文
- 用户需要显式使用 trace-aware 线程包装，才能保住 parent-child 关系

这不再是“核心语义缺失”，但仍然是一个 SDK 人体工学问题。

如果后续要继续强化 parallel orchestration 叙事，这里仍值得继续收口，例如扩展到更通用的线程池 / executor 接口。

### 2.3 examples 文档与真实示例之间仍有残留错位

`docs/examples.md` 已经比更早版本明显进步，但仍存在几类问题：

- 个别 bottleneck 描述和真实 pipeline 节点不一致
- subprocess 示例虽然已经注明是 inline simulation，但仍容易让人误解为端到端分布式示例
- 并行示例虽然现在已经有真实 coordinator root，但 examples 文档和 README 对它们的定位还没有完全稳定下来

这些问题不会破坏项目方向，但会影响仓库的第一印象可信度。

### 2.4 README 叙事仍略领先于当前完全稳定的实现

README 现在的产品表达方向是对的，而且比早期版本强很多。

它已经开始讲：

- orchestration timeline
- failure propagation
- bottleneck
- handoff flow
- parallel pipeline

但当前实现层仍有两条未完全打平的线：

- analysis 输出是否在 viewer 中被完整而一致地表达
- 原生线程接入是否足够自然

所以当前 README 更接近“已经接近产品形态的展示”，而不是“每个点都已经完全稳定落地的能力图”。

这不是严重问题，但需要持续收紧，避免首页叙事再次跑在实现层前面。

---

## 3. 当前最强的部分

### 3.1 产品边界是清晰的

结合 `program.md` 和 `GUARDRAILS.md` 看，当前项目边界是成立的：

- 不做通用 token / cost 平台
- 不让 eval / replay / guard 反客为主
- 优先把 trace depth、handoff、context flow、failure propagation 做深

这是当前仓库最重要的优点。

### 3.2 顶层 trace 状态语义已经比之前可信

之前最严重的问题之一，是“局部失败已被兜住，但整条 trace 仍然被直接判成 failed”。

当前这条逻辑已经明显改善：

- handled / contained failure 不再直接把整体执行判成失败
- 顶层 trace 状态更接近整体 run outcome

这对 CLI、web report 和 examples 的可信度提升很大。

### 3.3 bottleneck 分析已经脱离最粗糙的容器判断

之前 bottleneck 基本等于“最长 coordinator span”。

当前 analysis 已经不再停留在这个阶段，而是开始把 bottleneck 落到真正的工作节点上。这说明 analysis 层正在从“统计信息”变成“诊断信息”。

### 3.4 examples 体系正在变成场景库，而不是单一 demo

当前仓库已经不仅有最早的 research / coding demo，还开始有：

- parallel research
- parallel coding
- support pipeline
- data pipeline
- security pipeline
- content pipeline

这说明项目开始具备“不同 orchestration 场景的可观测性模板库”雏形，这是很有价值的正向变化。

---

## 4. 近期已改善的问题

以下问题在前几轮 review 中是主问题，但按当前状态看已经明显改善：

1. viewer 不再无条件把顺序 agent 渲染成 handoff。
2. 顶层 trace 状态不再简单按“任意 failed span”收口。
3. bottleneck 不再固定误判为 root coordinator 100%。
4. threaded parallel examples 已经恢复成单根 coordinator 拓扑，子线程 agent 会挂到正确父 span 下。

这些修正说明仓库不是停滞状态，而是在沿着正确方向收紧核心语义。

---

## 5. 当前优先级建议

如果只看当前主线，我会把优先级排成这样：

1. 让 viewer 跟上新的 bottleneck 语义，解决 tool bottleneck 与 agent sidebar 表达脱节的问题。
2. 继续收紧 README / examples，使所有对外叙事都与当前真实实现完全一致。
3. 把当前线程上下文继承能力继续抽象成更自然的并行接入方式，而不只停留在显式线程包装。
4. 再考虑进一步扩展 parallel execution、context flow、propagation 的产品表达。

---

## 6. 总评

当前 AgentGuard 已经不再像一个“功能散点集合”，而更像一个正在成型的产品原型。

它现在最强的不是某一个 demo，也不是单个 CLI 命令，而是这三层已经开始互相支撑：

- 统一 trace 数据模型
- 多种低侵入 SDK 接入方式
- 逐步成型的 orchestration diagnostics 语义

当前最大的风险也已经发生了变化：

不再是“方向不清”，
而是“analysis、viewer、examples 能不能始终讲同一个真实的故事”。

现在并行示例的拓扑已经基本站住了。下一步如果 viewer 再继续跟上 analysis 的语义，AgentGuard 就会从一个已经很强的 trace / diagnostics 原型，进一步升级成一个更可信的 multi-agent orchestration observability 工具。

---

## 7. Sprint 1 修复记录 (2026-04-12)

以下问题在 Sprint 1 中已修复：

### §2.1 viewer ↔ analysis bottleneck 语义对齐
- ✅ viewer sidebar 现在支持 tool-span bottleneck 卡片（不再只显示 agent）
- ✅ 新增 7 个 viewer fidelity 测试，验证 viewer 不显示 phantom handoffs
- ⚠️ 仍需深化：tool-level drill-down（点击 agent → 展开 tool 细节）

### §2.2 线程上下文传播
- ✅ TracingExecutor — ThreadPoolExecutor wrapper，自动传播 trace context
- ✅ traced_task() — asyncio.create_task 的 trace-aware 版本
- ✅ TraceThread — threading.Thread 的 trace-aware 版本
- ⚠️ 仍需深化：ProcessPoolExecutor、框架 middleware（LangChain/CrewAI/AutoGen）

### §2.3 examples 文档一致性
- ✅ README audit 完成 — 移除了不存在的 `evolve` CLI 引用，修正了数字
- ✅ getting-started.md 和 quickstart.md 合并

### §2.4 README 叙事
- ✅ README 数字更新：750+ tests, 15K+ LOC, 30+ CLI commands
- ✅ 移除了 evolve CLI 引用

### 新增能力
- Q4 cost-yield analysis（9 个测试）
- Q5 decision tracking + refactor（9 个测试，≤50 行函数）
- Integration roundtrip test（8 个测试）
- Span duration anomaly detection
- Context truncation detection
- Context flow waterfall chart in viewer
- Multi-model pipeline example
- Error recovery: timeout + partial result patterns
- api-reference.md, configuration.md 文档
