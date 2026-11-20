# ROITZ Task 3 Phase 1: Architecture Audit — Autonomous Agent & Planning

**Status:** Architecture Audit Only (No Implementation)  
**Date:** 2026-11-11  
**Scope:** Inventory existing autonomous capabilities, design smallest safe implementation integrating with existing architecture

---

## 1. Executive Summary

This audit inventories JARVIS's existing autonomous capabilities across seven dimensions and proposes a minimal, safe architecture for an autonomous agent that integrates with the current system. The key finding: **JARVIS already has significant autonomous infrastructure** — the DevAgent (`actions/dev_agent.py`) and ProactiveEngine (`actions/proactive.py`) demonstrate planning, execution monitoring, error handling/recovery, memory integration, tool integration, and safety/permission integration. The gap is a **unified task lifecycle** that can compose these capabilities for arbitrary goals.

---

## 2. Existing Capability Inventory

### 2.1 Goal Understanding

| Component | Capability | Location |
|-----------|-----------|----------|
| **DevAgent** | Parses natural language descriptions into structured project plans (JSON with files, dependencies, run commands) | `actions/dev_agent.py:_plan_project()` |
| **DevAgent (Improve)** | Reads entire project folder, understands existing codebase via `_scan()` + `_context()`, generates change plans | `actions/dev_agent.py:_plan_changes()` |
| **ProactiveEngine** | Builds context-rich prompts with memory, time-of-day, monitor topics, recent conversation | `actions/proactive.py:build_prompt()` |
| **Gemini Ladder** | Multi-tier model selection (FAST/SMART/SEARCH/LIVE/PROVIDER_PREFIX) with cooldown/fallback | `core/gemini.py` |
| **Local LLM** | Ollama/OpenAI-compatible backend support with warmup | `core/llm_client.py` |

**Gap:** No general-purpose goal decomposition for non-coding tasks. DevAgent only handles "build project" or "improve folder" goals.

---

### 2.2 Task Decomposition

| Component | Capability | Location |
|-----------|-----------|----------|
| **DevAgent (Build)** | `_plan_project()` → returns ordered file list with imports, dependencies, run command | Lines 132-179 |
| **DevAgent (Improve)** | `_plan_changes()` → returns summary + list of `{path, action, what}` changes | Lines 929-965 |
| **DevAgent (Write)** | `_write_file()` writes individual files in dependency order (topological sort by imports) | Lines 181-263, 515-553 |
| **ProactiveEngine** | Rotates through 3 focus areas (projects/goals, wellbeing, interesting facts) to vary prompts | Lines 74-90 |

**Gap:** No generic task graph / DAG decomposition. DevAgent's decomposition is hardcoded to file-per-module code generation.

---

### 2.3 Planning

| Component | Capability | Location |
|-----------|-----------|----------|
| **DevAgent** | Two-phase: Plan (JSON) → Execute (write files in order) | `_plan_project()` + `_build_project()` loop |
| **DevAgent (Improve)** | Plan → Backup → Write → Cross-file review → Syntax fix → Test → Fix → Undo registration | `_improve_folder()` lines 1268-1506 |
| **ProactiveEngine** | Decides *when* to act (silence + cooldown gates), builds prompt, Gemini decides *what* | `should_trigger()` + `build_prompt()` |

**Gap:** No persistent plan object with status tracking, rollback points, or human-in-the-loop checkpoints for arbitrary multi-step tasks.

---

### 2.4 Execution Monitoring

| Component | Capability | Location |
|-----------|-----------|----------|
| **DevAgent** | `_JOB` global dict tracks: folder, model, kind, phases, request, status, started/finished, summary, files{path→{action,state,what}}, steps, result | Lines 673-681, `_update()`, `_publish()` |
| **DevAgent** | Real-time UI updates via `player.show_code_job()` (thread-safe signal) | Lines 708-716, `_publish()` |
| **DevAgent** | Background thread execution with `_run_job()` — returns immediately, result spoken later | Lines 1535-1572 |
| **ProactiveEngine** | `_last_triggered`, `_rotation` track cooldown and focus rotation | Lines 32-33, 44-46 |
| **Main** | `engine_task`, `proactive_task`, `monitor_task` background asyncio tasks tracked in `JarvisLive` | `main.py` ~lines 200-250 |

**Gap:** No unified execution monitor for arbitrary tasks. DevAgent's `_JOB` is coding-specific.

---

### 2.5 Error Handling & Recovery

| Component | Capability | Location |
|-----------|-----------|----------|
| **DevAgent** | `_classify_error()` → dependency/syntax/import/runtime error types | Lines 92-112 |
| **DevAgent** | `_has_error()` filters out timeouts, empty output | Lines 115-126 |
| **DevAgent** | `_try_auto_install()` for missing modules | Lines 354-374 |
| **DevAgent** | `_fix_files()` — targeted fixes using traceback parsing (`_parse_traceback()`) | Lines 376-463 |
| **DevAgent** | `_review_interfaces()` — cross-file interface validation (imports, calls, flags, keys) | Lines 1055-1106 |
| **DevAgent** | `_syntax_error()` — compile/check without running | Lines 1109-1121 |
| **DevAgent** | `_test_and_fix()` — runs project tests, blames changes, fixes regressions | Lines 1202-1265 |
| **DevAgent** | Backup + undo stack (`core.undo.push_undo`) for full rollback | Lines 1360-1393, 1459-1476 |
| **DevAgent** | Rate limit handling with retry/backoff (`RateLimitError`) | Lines 128-129, 175-179, etc. |
| **Gemini** | Cooldown ladder for quota errors (429) — 60s cooldown per model | `core/gemini.py` ~lines 100-150 |
| **PermissionGuard** | Atomic approval token consumption, denies unknown operations by default | `core/permission_guard.py` |

**Gap:** No generic retry policy framework. DevAgent's recovery is hardcoded to code generation (write→run→fix loop).

---

### 2.6 Memory & Context Management

| Component | Capability | Location |
|-----------|-----------|----------|
| **MemoryManager** | Long-term JSON store: identity, preferences, projects, relationships, wishes, notes | `memory/memory_manager.py` |
| **MemoryManager** | Prompt budgeting: `PROMPT_CORE_CHARS=900` (always-on), `PROMPT_INDEX_CHARS=420` (keys only) | Lines 40-45 |
| **MemoryManager** | `format_memory_for_prompt()` — identity always, recent entries by recency, per-category cap (6) | Lines 194-324 |
| **MemoryManager** | `search_memory()` — lexical scoring, backs `recall_memory` tool | Lines 329-380 |
| **MemoryManager** | Session summaries: `save_session_summary()` / `pop_last_session()` (consumed once) | Lines 431-479 |
| **DevAgent** | Project brief caching (`_project_brief()`) — studies project once, caches by fingerprint | Lines 1127-1190 |
| **ProactiveEngine** | Injects formatted memory + recent turns + monitor topics into proactive prompt | `build_prompt()` lines 100-127 |

**Gap:** No working memory / scratchpad for in-progress task state. Session memory is conversation-only.

---

### 2.7 Tool/Use Integration

| Component | Capability | Location |
|-----------|-----------|----------|
| **ActionLoader** | Auto-discovers `actions/*.py` with `TOOL` dict (name, description, parameters, handler) | `core/action_loader.py` |
| **PluginLoader** | Auto-discovers `plugins/*.py` with `PLUGIN` dict + `run()` + optional `PLUGIN_SETTINGS` | `core/plugin_loader.py` |
| **ActionRegistry** | `get_tool_declarations()` → Gemini function declarations (strips META_KEYS) | Lines 148-163 |
| **PluginRegistry** | `get_tool_declarations()` — respects enable/disable from config | Lines 105-124 |
| **PermissionGuard** | `wrap_handler()` / `guarded_call()` — checks `OPERATION_SPECS`, validates templates, consumes approvals | `core/permission_guard.py` lines 147-191 |
| **ActionRegistry.run()** | Permission check → template validation → `_call_handler()` with signature introspection | Lines 177-211 |
| **PluginRegistry.run()** | Same pattern, passes `player` + `session_memory` | Lines 135-172 |
| **Main._execute_tool()** | Dispatches to action_registry or plugin_registry, handles scheduling (WHEN_IDLE/SILENT/INTERRUPT) | `main.py` |

**Gap:** No tool composition / chaining abstraction. Each tool call is independent; no "macro" or "workflow" concept.

---

### 2.8 Safety & Permission Integration

| Component | Capability | Location |
|-----------|-----------|----------|
| **PermissionManager** | Persistent grants + one-time approval tokens (HMAC-signed, TTL) | `core/permission_manager.py` |
| **PermissionGuard** | `OPERATION_SPECS` registry maps `operation_name` → capability, template, additional caps | `core/permission_guard.py` lines 31-87 |
| **Confirm Module** | UI-issued confirmation tokens (not model-forgeable), 90s timeout, non-blocking | `core/confirm.py` |
| **Action/Plugin Loaders** | Both integrate permission check in `run()` before handler execution | `action_loader.py:182-191`, `plugin_loader.py:142-151` |
| **Command Templates** | `proc.exec` operations validated against approved templates (e.g., `pytest_project`, `pip_install_approved`) | `core/command_templates.py` |
| **Protection (code_checks)** | Protects secrets/config files from model edits | `core/code_checks.py` |

**Gap:** No capability-based sandbox for autonomous multi-step tasks. Each step checks permissions independently; no "task-level" grant.

---

## 3. Architecture Analysis

### 3.1 Threading Model (Critical Constraint)

```
┌─────────────────────────────────────────────────────────────┐
│                    Qt Main Thread (ui.py)                   │
│  MainWindow, HudCanvas, LogWidget, overlays, signals        │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ pyqtSignal (QueuedConnection)
                              │
┌─────────────────────────────────────────────────────────────┐
│              Asyncio Event Loop (main.py background)        │
│  JarvisLive: session, tool execution, background tasks      │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ threading.Thread / asyncio.to_thread
                              │
┌─────────────────────────────────────────────────────────────┐
│                  Worker Threads (actions/plugins)           │
│  file_controller, dev_agent, proactive, browser_control...  │
│  MUST NEVER create/touch Qt widgets                         │
└─────────────────────────────────────────────────────────────┘
```

**Rule:** Autonomous agent logic must live in worker threads. UI updates via `player` methods (signals).

---

### 3.2 Existing "Agent" Patterns

| Pattern | Example | Reusable? |
|---------|---------|-----------|
| **Background job with UI progress** | DevAgent `_JOB` + `player.show_code_job()` | ✅ Yes |
| **Plan → Execute → Monitor → Fix loop** | DevAgent `_build_project()` / `_improve_folder()` | ✅ Yes (coding-specific) |
| **Non-blocking confirmation gate** | `core/confirm.py` request/resolve | ✅ Yes |
| **Permission-checked tool dispatch** | ActionRegistry/PluginRegistry `run()` | ✅ Yes |
| **Context-rich prompt building** | ProactiveEngine `build_prompt()` | ✅ Yes |
| **Model ladder with fallback** | `core/gemini.py` tier system | ✅ Yes |
| **Undo/rollback** | `core/undo.py` + DevAgent backup | ✅ Yes |

---

## 4. Design Proposal: Minimal Autonomous Agent

### 4.1 Core Concept: `TaskAgent`

A **single new action** (`actions/task_agent.py`) that composes existing primitives:

```python
# Minimal interface
TOOL = {
    "name": "task_agent",
    "description": "Run a multi-step autonomous task with planning, execution, monitoring, and recovery.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {"type": "STRING", "description": "What to accomplish in user's words"},
            "mode": {"type": "STRING", "enum": ["plan", "execute", "status", "cancel"], "default": "execute"},
            "task_id": {"type": "STRING", "description": "Resume/cancel existing task"},
            "max_steps": {"type": "INTEGER", "default": 10},
            "require_confirmation": {"type": "BOOLEAN", "default": True},
        },
        "required": ["goal"]
    },
    "handler": task_agent,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}
```

### 4.2 Task Lifecycle

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PLANNING  │────▶│  CONFIRM    │────▶│  EXECUTING  │────▶│  COMPLETED  │
│  (Gemini)   │     │  (UI gate)  │     │  (steps)    │     │  / FAILED   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
  - Parse goal        - Show plan         - Run steps          - Save result
  - Decompose         - User approves     - Monitor each       - Update memory
  - Estimate steps    - Or reject         - Handle errors      - Speak summary
  - Check permissions - Returns           - Retry/skip         - Push undo if
  - Return plan       - immediately       - UI progress        -   destructive
```

### 4.3 Data Structures

```python
@dataclass
class TaskStep:
    id: str                    # "step_1", "step_2"
    description: str           # Human-readable
    tool: str                  # Action/plugin name
    parameters: dict           # Tool parameters
    requires_confirmation: bool
    depends_on: list[str]      # Step IDs (for DAG, initially linear)
    status: str                # pending/running/done/failed/skipped
    result: str | None
    error: str | None
    retry_count: int = 0

@dataclass
class TaskPlan:
    task_id: str
    goal: str
    steps: list[TaskStep]
    created_at: float
    status: str                # planned/confirmed/executing/completed/failed/cancelled
    current_step: int
    result: str | None
    undo_token: str | None     # For rollback if destructive
```

### 4.4 Integration Points (Reuse Existing)

| Need | Reuse |
|------|-------|
| Goal → Plan | `gemini.as_json()` with structured prompt (like DevAgent `_plan_project`) |
| Plan storage | In-memory dict + persist to `memory/tasks.json` (like session summaries) |
| Step execution | `ActionRegistry.run()` / `PluginRegistry.run()` (permission-checked) |
| Progress UI | `player.show_content()` or new `player.show_task_progress()` (signal-based) |
| Confirmation | `core.confirm.request()` / `resolve()` (UI-issued tokens) |
| Error classification | Extend DevAgent `_classify_error()` to generic tool errors |
| Retry/backoff | DevAgent `RateLimitError` pattern + configurable policy |
| Memory injection | `memory_manager.format_memory_for_prompt()` + `search_memory()` |
| Undo | `core.undo.push_undo()` for destructive operations |

### 4.5 Safety Design

1. **No new permissions** — uses existing `OPERATION_SPECS`; each step checked individually
2. **Confirmation gate** — destructive steps (fs.write, proc.exec, etc.) require UI confirmation via `core.confirm`
3. **Step budget** — `max_steps` default 10, hard cap 20
4. **Timeout** — per-step deadline (default 60s), overall task deadline (default 10 min)
5. **Cancellation** — `mode="cancel"` sets flag, worker checks between steps
6. **No widget creation** — all UI via `player` methods (thread-safe signals)
7. **Audit log** — every step logged to activity log via `player.write_log()`

---

## 5. Testing Strategy

### 5.1 Unit Tests (New File: `tests/unit/test_task_agent.py`)

| Test | Description |
|------|-------------|
| `test_plan_generation` | Goal → valid TaskPlan with steps, no hallucinated tools |
| `test_step_execution_success` | Single step runs via ActionRegistry, result captured |
| `test_step_execution_failure` | Failed step returns error, status=failed |
| `test_confirmation_gate` | Destructive step pauses for confirm, resumes on accept |
| `test_confirmation_rejection` | Rejected step → task status=cancelled |
| `test_retry_on_rate_limit` | 429 error → retry with backoff, max 3 attempts |
| `test_cancellation` | `mode="cancel"` stops between steps |
| `test_max_steps_enforced` | 11th step rejected |
| `test_persistence` | TaskPlan survives process restart (load from memory/tasks.json) |
| `test_undo_registration` | Destructive step pushes undo, rollback works |

### 5.2 Integration Tests

| Test | Description |
|------|-------------|
| `test_multi_step_file_operations` | create_file → write → read → delete (with confirm on delete) |
| `test_proactive_triggered_task` | ProactiveEngine suggests task, user confirms, executes |
| `test_dev_agent_composition` | TaskAgent calls dev_agent as a step (sub-task) |
| `test_permission_denied` | Step requiring ungranted capability → proper error to model |

### 5.3 Safety Tests

| Test | Description |
|------|-------------|
| `test_no_qt_widgets_created` | Run in worker thread, verify no QWidget instantiation |
| `test_approval_token_consumed` | Confirmation uses one-time token, cannot replay |
| `test_unknown_operation_denied` | Hallucinated tool name → denied by PermissionGuard |

---

## 6. Implementation Batches

### Batch 1: Foundation (Minimal Viable)
**Files:** `actions/task_agent.py`, `tests/unit/test_task_agent.py`
- TaskPlan/TaskStep dataclasses
- Planner prompt → `gemini.as_json()` → TaskPlan
- Linear step executor using `ActionRegistry.run()` / `PluginRegistry.run()`
- In-memory task store + `memory/tasks.json` persistence
- `mode="status"` / `"cancel"`
- Unit tests for planning + execution + cancellation

### Batch 2: Safety & Confirmation
**Files:** `actions/task_agent.py` (extend), `core/confirm.py` (reuse)
- `requires_confirmation` per step (auto-detect from `OPERATION_SPECS` destructive caps)
- Integrate `core.confirm.request()` / `resolve()`
- Confirmation timeout handling (90s)
- Undo registration for destructive steps
- Unit tests for confirmation gate + undo

### Batch 3: Monitoring & Recovery
**Files:** `actions/task_agent.py` (extend)
- Per-step timeout + overall task timeout
- Error classification (reuse DevAgent patterns)
- Retry policy (exponential backoff, max 3)
- Progress UI via `player.show_content()` or new `show_task_progress()`
- Unit tests for timeout, retry, error handling

### Batch 4: Memory & Context
**Files:** `actions/task_agent.py` (extend)
- Inject formatted memory into planner prompt
- `search_memory()` available as a step tool
- Session summary on completion → `save_session_summary()`
- Project brief caching for coding tasks (reuse DevAgent `_project_brief()`)

### Batch 5: Advanced (Post-Phase 1)
- DAG dependencies between steps (parallel execution)
- Human-in-the-loop checkpoints (not just confirmations)
- Task templates / recipes
- ProactiveEngine integration (suggest tasks autonomously)

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Model hallucinates invalid tool names | Medium | High | PermissionGuard denies unknown ops; planner prompt includes available tool list |
| Infinite loop on retries | Low | High | Hard max_steps + max_retries + overall timeout |
| UI thread violation | Low | Critical | All UI via `player` methods; tests verify no QWidget creation |
| Permission bypass | Low | Critical | Every step goes through ActionRegistry/PluginRegistry `run()` |
| Memory corruption | Low | Medium | JSON persistence with validation; backup on write |
| Rate limit exhaustion | Medium | Medium | Gemini ladder cooldowns + task-level backoff |

---

## 8. Conclusion

**JARVIS already has 80% of the infrastructure needed for autonomous agents.** The DevAgent and ProactiveEngine demonstrate planning, execution monitoring, error recovery, memory integration, tool dispatch, and safety gates — all in production use.

The **TaskAgent** design proposes a **thin composition layer** (≈400 lines) that:
- Reuses every existing primitive (no new threading, no new permission model, no new UI framework)
- Adds only: task lifecycle, step orchestration, generic planner prompt, persistence
- Can be implemented in 4 focused batches with comprehensive tests
- Ships behind a single new tool `task_agent` with `NON_BLOCKING` behavior

This is the **smallest safe implementation** that unlocks general-purpose autonomy while respecting JARVIS's architectural constraints.