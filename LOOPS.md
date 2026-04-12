# AgentGuard Development Loop Architecture

> How this project is built: a multi-agent loop running inside OpenClaw.

## Architecture

```
┌─────────────────────────────────────────────┐
│  OpenClaw (Harness)                         │
│  ├── Session management                     │
│  ├── Message routing (Feishu ↔ Claude)      │
│  ├── Heartbeat / keepalive                  │
│  └── Sub-agent orchestration                │
│                                             │
│  ┌───────────────────────────────────────┐  │
│  │  Main Session (基围小小虾 🦐)          │  │
│  │  Role: Planner + Evaluator            │  │
│  │  ├── Reads program.md (priorities)    │  │
│  │  ├── Decomposes into stories          │  │
│  │  ├── Dispatches to sub-agents         │  │
│  │  ├── Reviews results (evaluator)      │  │
│  │  └── Updates progress + memory        │  │
│  └───────────────────────────────────────┘  │
│          │                                   │
│          ▼ spawn per story                   │
│  ┌───────────────────────────────────────┐  │
│  │  Sub-Agent (Generator)                │  │
│  │  = Fresh context each time            │  │
│  │  ├── Reads: story spec + CLAUDE.md    │  │
│  │  ├── Implements code + tests          │  │
│  │  ├── Runs pytest                      │  │
│  │  ├── Commits + pushes                 │  │
│  │  └── Reports back completion          │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  大大虾 (Human)                              │
│  ├── Sets direction (program.md)            │
│  ├── Code review (current-state-review)     │
│  ├── Course correction via chat             │
│  └── Final acceptance                       │
└─────────────────────────────────────────────┘
```

## Comparison with Known Patterns

| Aspect | Ralph (snarktank) | Anthropic 3-Agent | Our Loop |
|--------|-------------------|-------------------|----------|
| Harness | bash script | Custom Python | OpenClaw |
| Generator | Claude Code CLI (fresh per iteration) | Generator agent | Sub-agent (fresh context) |
| Evaluator | typecheck + pytest | Separate Evaluator agent | Main session + 大大虾 review |
| Planner | PRD → prd.json | Planner agent | Main session reads program.md |
| State | git + progress.txt + prd.json | Structured artifacts | git + program.md + memory/*.md |
| Context reset | New CLI instance per iteration | New agent per phase | New sub-agent per story |
| Human role | Writes PRD, reviews final | Writes spec | Sets direction, reviews, course corrects |

## Key Design Decisions

### Why OpenClaw, not raw Claude Code CLI?
- Already has session persistence + message routing
- Sub-agent system provides context isolation
- Heartbeat keeps the loop alive
- Human can intervene mid-loop via chat

### Why Main Session as Planner+Evaluator?
- Maintains continuity: understands project history and direction
- Can evaluate holistically: does this change fit the overall vision?
- Avoids the "self-praise" problem: evaluates sub-agent output, not own output

### Why Sub-Agents as Generators?
- Fresh context = no context anxiety
- Focused scope = better code quality
- Failure isolation = one bad story doesn't corrupt the whole session

## State Files

| File | Purpose | Analogous to |
|------|---------|-------------|
| `program.md` | Direction, priorities, progress log | prd.json |
| `CLAUDE.md` | Instructions for generator agents | prompt.md |
| `GUARDRAILS.md` | Lines that must not be crossed | — |
| `memory/*.md` | Daily notes, intermediate state | progress.txt |
| `docs/*-review-zh.md` | 大大虾's evaluations | — |
| Git history | All code changes | Same |

## Failure Modes & Mitigations

### Context Anxiety
**Problem**: Agent starts wrapping up prematurely as context fills.
**Mitigation**: Context reset via sub-agents. Main session compresses memory at 50%.

### Self-Evaluation Bias
**Problem**: Generator agent rates own work too highly (Anthropic finding).
**Mitigation**: Main session evaluates sub-agent output. 大大虾 provides external review.

### Lateral Drift
**Problem**: Agent keeps adding modules instead of deepening (happened to us).
**Mitigation**: program.md enforces "Trace depth > feature breadth". 大大虾 course corrects.

### State Loss Between Sessions
**Problem**: New session loses all context from previous work.
**Mitigation**: program.md progress log + memory files + git history as structured handoff.

## Lessons Learned

1. **Compaction < Context Reset**: Summarizing old context helps, but a fresh agent with a structured handoff is better (matches Anthropic's finding).
2. **Binary story completion matters**: "Is this done? yes/no" prevents drift. Our early iterations lacked this.
3. **Human review is the strongest evaluator**: 大大虾's code reviews caught semantic issues (trace status, bottleneck logic) that automated tests missed.
4. **Direction documents > conversation history**: program.md and review docs carry more signal than 300 turns of chat.

---

## Improvement Plan (from Ralph + Anthropic analysis)

### ✅ Already in place
- Git as persistence layer
- program.md as direction document
- Human review as external evaluator
- CLAUDE.md as generator instructions

### 🔧 Need to implement

#### 1. Structured story tracking (from Ralph)
Replace prose progress log with structured checklist:
```markdown
## Current Stories
- [x] Fix trace status for handled failures
- [x] Fix bottleneck to exclude coordinators
- [ ] Align docs/examples.md with real behavior
- [ ] Make viewer handoff only show recorded handoffs
```
Each story = one sub-agent dispatch. Binary: done or not done.

#### 2. Append-only progress log (from Ralph)
Add `progress.txt` that is never overwritten, only appended:
```
[2026-04-12 05:44] Learned: bottleneck analysis must exclude container spans
[2026-04-12 05:50] Learned: handled failures should not mark trace as FAILED
```

#### 3. Explicit evaluation criteria (from Anthropic)
Define criteria that the evaluator (main session) checks:
- Does the change have tests? (pytest passes)
- Does it match the story spec exactly?
- Does it avoid introducing new modules? (unless story says so)
- Does it align with GUARDRAILS.md?
- Would 大大虾's review pass it?

#### 4. Structured handoff format (from Anthropic)
When passing work between sessions or sub-agents:
```json
{
  "completed_stories": ["fix-trace-status", "fix-bottleneck"],
  "current_story": "align-docs-examples",
  "blocked_on": null,
  "key_decisions": ["handled failures don't affect trace status"],
  "known_issues": ["viewer still shows inferred handoffs"],
  "test_count": 704,
  "commit_count": 210
}
```

#### 5. Sub-agent per story (context reset)
Instead of doing everything in main session:
- Main session = read program.md, pick next story, spawn sub-agent
- Sub-agent = fresh context, focused on ONE story, commit when done
- Main session = evaluate result, update checklist, pick next

This eliminates context anxiety and self-evaluation bias.
