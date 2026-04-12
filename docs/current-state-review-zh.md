# AgentGuard 当前状态评审

> 评审时间：2026-04-12
> 范围：rebase 后当前主线实现、README、examples、web viewer、analysis 语义对齐情况

---

## 1. 结论

这次 rebase 后，仓库的整体方向比之前更清晰，已经明显收敛到“多 Agent 编排层可观测性”这条主线。

主要积极变化有三点：

- README、截图、示例集都开始围绕 orchestration、handoff、failure propagation、critical path 叙事。
- `agentguard/analysis.py` 已经具备比早期版本更完整的失败传播、流转和瓶颈分析能力。
- `examples/coding_pipeline.py` 已经成为一个比较像真实工程闭环的旗舰示例，比早期 research demo 更能代表项目价值。

但当前主线仍然有一个明显问题：

**项目叙事已经升级，但部分实现和文档还没有完全跟上。**

也就是说，现在最大的风险不再是方向漂移，而是：

- UI 展示的语义不完全真实
- examples 文档承诺强于真实示例
- README 中个别能力表述仍然略超前于当前落地程度

如果这些地方继续放着不收紧，仓库会开始出现“看起来很强，但跑起来不是同一个故事”的信任损耗。

---

## 2. 当前最重要的问题

### 2.1 viewer 中 handoff 语义仍然不严谨

`agentguard/web/viewer.py` 已经接入分析层输出，这是正确方向。

但当前 handoff 渲染仍有一个关键问题：顺序相邻的 agent 仍会被直接画成 handoff，即使分析层没有明确识别出真实 handoff。

这会带来一个很现实的风险：

- 用户看到的是“Agent A 把上下文交给了 Agent B”
- 但底层 trace 实际上可能只记录了两个顺序执行的 agent

对一般 trace viewer 来说，这只是一个展示问题；对 AgentGuard 这种主打 orchestration diagnostics 的产品来说，这是核心语义问题。

### 2.2 examples 文档与真实示例之间还有不一致

`docs/examples.md` 的整体结构已经比之前好很多，但仍有两类问题：

第一类是**能力描述超前**：

- basic research 示例仍然写成了并行执行，但真实实现是串行。
- subprocess 示例仍然描述为完整跨进程关联与 merge 示例，但真实示例仍主要是父进程内模拟。

第二类是**事故叙事比代码更稳定**：

- coding pipeline 文档里对 fallback、未处理 notifier 失败、resilience 的描述更像固定剧本。
- 实现里这些结果带有条件分支或随机性，未必每次都稳定复现同一个诊断结论。

这不会影响方向判断，但会影响外部用户第一次运行时对项目可信度的感受。

### 2.3 README 已经接近正确，但仍要避免“展示图领先实现太多”

README 当前已经明显优于早期版本，定位基本正确：

- 不再试图和通用 LLM observability 平台重叠
- 把 trace、handoff、failure propagation 放到了核心位置
- 用 coding pipeline 作为主示例，比 generic research 示例更强

但要注意一个边界：

README 现在展示的是更成熟的 orchestration diagnostics 形态，而真实 `viewer.py` 还没有完全到那一步。

这没有错，但应该控制差距，避免首页展示成为“产品愿景图”，而不是“当前仓库能力图”。

---

## 3. 当前最强的部分

### 3.1 产品边界终于更稳了

结合 `program.md` 和 `GUARDRAILS.md` 看，当前项目边界是清晰的：

- 不做通用 LLM token/cost 观测
- 不把 eval/replay/guard 提前抬成主产品
- 坚持把 handoff、failure propagation、context flow 做深

这是项目当前最重要的正向信号。

### 3.2 coding pipeline 已经成为正确的旗舰示例

`examples/coding_pipeline.py` 是当前示例体系里最有价值的一项，因为它天然覆盖了：

- coordinator + 多 agent 协作
- context gathering + fallback
- code generation / review / test / deploy
- tail failure（notifier）
- condition gate

这比普通的 research demo 更贴近 AgentGuard 想证明的“工程闭环可观测性”。

### 3.3 analysis 层已经开始具备真正的诊断价值

当前 analysis 不再只是统计，而是在试图回答：

- failure root cause 是谁
- failure 是 handled 还是 unhandled
- handoff / context flow 是怎样的
- critical path 和 bottleneck 是什么

只要 viewer 和 examples 继续向 analysis 语义对齐，项目就会越来越像“诊断工具”，而不是“漂亮 trace 面板”。

---

## 4. 文档整理建议

这轮评审最适合单独保存在本文件，而不是混进已有文档：

- `project-direction-review-zh.md` 更适合长期方向和边界判断
- `ui-panel-review-zh.md` 更适合界面表达和可视化路径判断
- 本文档更适合记录“当前主线实现是否自洽”的阶段性审计结果

这样三份文档分别承担不同职责：

- 方向评审
- UI 评审
- 当前状态评审

---

## 5. 下一步优先级

如果只看当前主线，最值得优先收敛的是这三件事：

1. 收紧 viewer 的 handoff 语义，让 UI 不再展示未被记录或未被分析识别的 handoff。
2. 收紧 `docs/examples.md`，让 examples 描述和真实示例行为完全一致。
3. 继续让 web viewer 使用更完整的 analysis 结果，逐步把 context flow / propagation / bottleneck 变成结构化诊断，而不是补充性标签。

---

## 6. 总评

当前仓库已经比之前更像一个真正的产品原型，而不是一个功能散点集合。

它最强的地方不是 eval、不是 replay、也不是 UI 皮相，而是：

- 统一 trace 数据模型
- 低侵入 SDK 接入层
- 开始成型的 orchestration diagnostics 语义

接下来不需要再扩产品边界，反而应该继续做一件更难但更值钱的事：

**把 README、examples、analysis、viewer 说成同一个故事。**

一旦这四层开始完全对齐，AgentGuard 的可信度和差异化都会明显上一个台阶。

---

## 7. 2026-04-12 增量评审（rebase 后复查）

这轮复查后，可以明确分成“已改善”和“仍未解决”两部分看。

### 7.1 已改善

#### viewer 的 handoff 渲染比上一轮更收紧了

上一轮最明显的问题之一，是 web viewer 会把顺序相邻的 agent 直接画成 handoff。

这轮复查后，这个问题已经有所改善：

- handoff 插入不再是无条件渲染
- viewer 现在只会在分析结果识别出 handoff 对时才绘制 handoff 连接

这说明展示层已经开始真正依赖分析语义，而不是继续自行发明一套简化规则。

这不是最终完成态，但它是一个明确的正向变化。

### 7.2 仍未解决的核心问题

#### 顶层 trace 状态仍然不可信

`sdk/recorder.py` 的 trace 收口逻辑仍然是：

- 只要存在任意 failed span
- 整条 trace 就会被标记为 failed

这会带来一个关键语义冲突：

- orchestrator 可能成功完成任务
- 某个尾部动作或已处理失败的局部 span 仍然存在 failed 记录
- 最终 trace 却被整体标成 failed

这和当前项目强调的 handled / unhandled failure 语义并不一致。

只要这条逻辑不改，CLI、web report、README 中关于整体执行结果的表达都会持续带偏。

#### 瓶颈分析仍然把 coordinator 当成 bottleneck

当前 `analyze_bottleneck()` 仍然会把 critical path 上最长的容器型 span 直接当作 bottleneck。

在旗舰示例里，这会把 `coding-pipeline` 这种包住全流程的 coordinator 判成 100% bottleneck。

这不符合用户真实想问的问题。

用户真正想知道的是：

- 哪个可优化的 agent 最慢
- 哪个 tool / sub-agent 真正拖慢了系统

而不是：

- 哪个包裹全流程的根节点活得最久

所以这一块仍然属于高优先级设计缺口，而不是单纯的展示问题。

### 7.3 文档仍有残留错位

这一轮 rebase 后，README 和 examples 整体比之前更完整，但还有几处残留问题：

- README 仍然用了比较强的“real failures, real fallbacks”表述
- `docs/examples.md` 中 coding pipeline 的 bottleneck 描述仍然写到了并不存在于该 pipeline 中的 `analyst`
- subprocess 示例已经注明是 inline simulation，但仍不是一个真正跑通 child init + merge 的端到端例子

这些问题都不是方向性错误，但它们会削弱仓库的第一印象可信度。

### 7.4 当前优先级应当更新为

如果按这轮复查后的真实状态重新排序，我会把当前最优先的问题更新为：

1. 修正 trace 顶层状态的收口语义，让 handled failure 不再直接把整体执行判成 failed。
2. 修正 bottleneck 分析定义，区分 coordinator 容器节点和真正的工作型瓶颈节点。
3. 继续把 README / examples 的描述收紧到当前实现已经稳定成立的语义上。

### 7.5 增量结论

这轮 rebase 不是没有进展，viewer handoff 语义已经比之前更可信了。

但项目当前最核心的两个诊断问题仍然没有真正解决：

- 顶层状态是否成功
- 谁才是真正的性能瓶颈

只要这两点还不准，AgentGuard 就还更像一个“高级 trace 展示器”，而不是一个已经足够可靠的 orchestration diagnostic tool。