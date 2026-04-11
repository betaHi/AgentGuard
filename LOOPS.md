# AgentGuard — Multi-Loop Development Architecture

> 解决单 Loop 上下文耗尽问题 + 并行开发效率

## 问题

单个 Ralph Loop 有三个瓶颈：
1. **上下文窗口有限** — 一个 session 不可能装下整个项目
2. **串行低效** — SDK 和 Eval 可以并行开发，没必要排队
3. **知识丢失** — session 结束后，下一个 session 不知道上一个做了什么

## 解决方案：Multi-Loop + Handoff Protocol

### 架构

```
program.md (人类编辑 — 总方向)
    │
    ├── Loop-1: SDK Loop ──────── sdk-progress.md
    ├── Loop-2: Eval Loop ─────── eval-progress.md
    ├── Loop-3: CLI Loop ──────── cli-progress.md
    └── Loop-4: Docs Loop ─────── docs-progress.md
    
    每个 Loop:
    ┌──────────────────────────────────────┐
    │  1. 读 program.md (总方向)           │
    │  2. 读 {module}-progress.md (进度)   │
    │  3. 读相关代码文件                    │
    │  4. 执行一个 sprint                  │
    │  5. 跑测试                           │
    │  6. 更新 {module}-progress.md        │
    │  7. 检查上下文预算                    │
    │     - 充裕 → 继续下一轮              │
    │     - 紧张 → 写 handoff → 新 session │
    └──────────────────────────────────────┘
```

### 上下文管理策略

#### 策略 1：Scoped Context（限定范围）
每个 Loop 只加载自己需要的文件，不要贪：

```
SDK Loop 只需要看:
  - program.md (方向)
  - sdk-progress.md (进度)
  - agentguard/core/*.py
  - agentguard/sdk/*.py
  - tests/test_trace.py, tests/test_decorators.py

Eval Loop 只需要看:
  - program.md
  - eval-progress.md
  - agentguard/core/trace.py (数据模型，只读)
  - agentguard/eval/*.py
  - tests/test_eval.py
```

#### 策略 2：Handoff Protocol（交班协议）
当上下文快满时，Loop 必须写一份 handoff 文件给下一个 session：

```markdown
# Handoff: SDK Loop Session 3 → Session 4

## 完成了什么
- @record_agent 和 @record_tool 已实现并测试
- TraceRecorder 支持多线程
- JSON 序列化/反序列化通过

## 还没完成
- [ ] Context propagation across async calls
- [ ] Trace export to OTel format

## 当前状态
- Tests: 15/15 passing
- 无已知 bug

## 下一步
1. 实现 async 版本的 decorator
2. 添加 OTel exporter

## 关键设计决定（别改）
- Span 用 flat list + parent_span_id，不用嵌套结构存储
- trace_id 用 uuid 前 16 位
```

#### 策略 3：Progress File（进度文件）
每个模块有一个持久化的进度文件，是 Loop 之间的"记忆"：

```
.loops/
├── sdk-progress.md      # SDK 模块进度
├── eval-progress.md     # Eval 模块进度
├── cli-progress.md      # CLI 模块进度
├── docs-progress.md     # 文档进度
└── handoffs/            # 交班记录
    ├── sdk-session-3-to-4.md
    └── eval-session-1-to-2.md
```

#### 策略 4：Context Budget Check（上下文预算检查）
每轮 Loop 开始时估算上下文使用情况：

```
Rule of thumb:
- 每个 .py 文件 ≈ 100-300 tokens
- program.md ≈ 500 tokens
- progress.md ≈ 200 tokens
- 测试输出 ≈ 200 tokens

如果一个 Loop 需要操作 5 个 .py 文件:
  5 × 200 + 500 + 200 + 200 = ~2000 tokens 输入
  加上对话历史，大约 3-5 轮后就该考虑交班
```

### 并行 Loop 定义

#### Loop 1: SDK Loop
```
职责: agentguard/core/ + agentguard/sdk/
输入: program.md, sdk-progress.md
输出: 代码 + 测试 + sdk-progress.md
sprint 周期: 1-2 个功能点
```

#### Loop 2: Eval Loop
```
职责: agentguard/eval/
输入: program.md, eval-progress.md, core/trace.py (只读)
输出: 代码 + 测试 + eval-progress.md
依赖: SDK Loop 完成 core schemas
sprint 周期: 1 个评估器
```

#### Loop 3: CLI Loop
```
职责: agentguard/cli/
输入: program.md, cli-progress.md, core/ + sdk/ + eval/ (只读)
输出: CLI 代码 + cli-progress.md
依赖: SDK Loop + Eval Loop
sprint 周期: 1-2 个命令
```

#### Loop 4: Docs Loop
```
职责: README.md, docs/, examples/
输入: program.md, docs-progress.md, 所有代码 (只读)
输出: 文档 + 示例 + docs-progress.md
独立运行，随时可以启动
```

### 跨 Loop 通信规则

1. **只通过文件通信** — 不共享内存、不共享上下文
2. **progress.md 是唯一的状态源** — 每个 Loop 写自己的，读别人的
3. **代码是共享产物** — 一个 Loop 写的代码，另一个 Loop 可以读
4. **不要跨界修改** — SDK Loop 不改 eval/ 代码，反之亦然
5. **依赖通过 interface 解耦** — Eval Loop 只依赖 core/trace.py 的 schema，不依赖 SDK 实现

### 启动命令

```bash
# 启动 SDK Loop（Sprint 2: async support + OTel export）
# 读 program.md + sdk-progress.md，开始工作

# 启动 Eval Loop（Sprint 2: rule-based assertions）  
# 读 program.md + eval-progress.md，开始工作

# 两个可以并行跑
```

### Dogfooding

最酷的地方：**AgentGuard 的多 Loop 开发过程本身就是一个多 Agent 协作场景。**

我们可以用 AgentGuard 来记录和观测自己的开发 Loop：
- Loop 1 = Agent "SDK-Dev"
- Loop 2 = Agent "Eval-Dev"  
- 它们的执行、交班、依赖关系，正好用 AgentGuard trace 来展示

**用自己做的工具来观测自己做这个工具的过程。** Meta-dogfooding.

---

_This architecture is itself a living document. Update as we learn._
