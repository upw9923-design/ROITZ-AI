# ROITZ AI + MONSTER — Product Vision & Master Development Roadmap

**Project Root:** `D:\M MONSTER PROJECT\Roitz-main`  
**Date:** 2026-11-16  
**Version:** 1.0  
**Status:** Architecture Audit Complete — Implementation Roadmap Defined  

---

## 1. Product Vision & Identity

### 1.1 Product Identity

| Field | Value |
|-------|-------|
| **Product Name** | ROITZ AI |
| **Integrated AI Assistant** | MONSTER |
| **Tagline** | "Your Life \| Your Control \| Powered by MONSTER" |
| **Architecture** | Single desktop application (Windows priority) with modular engine system |
| **License** | Creative Commons BY-NC 4.0 (personal, non-commercial) |

### 1.2 Core Vision Statement

ROITZ is a **local-first, privacy-respecting intelligent personal computer assistant** that combines:

- **Natural-language understanding** (Hindi, English, Hinglish)
- **Computer control** (screen observation, UI interaction, application management)
- **Voice interaction** (speech recognition, synthesis, wake word, push-to-talk)
- **Task execution & planning** (structured workflows, verification, error recovery)
- **Memory & context** (persistent, searchable, user-controllable)
- **External integrations** (ChatGPT ↔ Claude Code bridge, Telegram, browser automation)
- **Security by default** (PermissionGuard, owner approval, audit logging, fail-closed)

The fundamental execution philosophy:

```
UNDERSTAND → PLAN → VALIDATE → AUTHORIZE → EXECUTE → OBSERVE → VERIFY → REPORT
```

**MONSTER must not merely claim success — it must establish evidence that actions succeeded.**

---

## 2. System Architecture Overview

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MAIN.PY (Async Event Loop)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  Session Lifecycle                                                          │
│  ├── _conv_store: ConversationStore (thread-safe singleton)                 │
│  ├── _current_conversation_id: str | None                                  │
│  ├── _resume_handle: str | None  (RAM ONLY — NOT persisted)                │
│  ├── _session_log: list[str]  (RAM, cleared at session end)                │
│  └── Session loop: create → append_message → finalize_conversation        │
├─────────────────────────────────────────────────────────────────────────────┤
│  UI Thread (Qt Main)                                                        │
│  ├── ui.py:MainWindow → HistoryPanel (center_split index 3)                │
│  ├── Signals: _history_list_sig, _history_detail_sig,                      │
│  │           _history_search_sig, _history_error_sig                       │
│  ├── Request tracking: 4 per-operation request IDs                         │
│  └── Layout: Content(base) + History/Quiz(overlay) with stack              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Worker Threads                                                             │
│  ├── actions/history_worker.py:HistoryWorker                               │
│  ├── actions/task_agent.py:TaskAgent                                       │
│  ├── core/worker_registry.py:WorkerRegistry (resource coordination)        │
│  └── core/process_monitor.py:ProcessMonitor (subprocess execution)         │
├─────────────────────────────────────────────────────────────────────────────┤
│  Dispatch Layer                                                             │
│  ├── core/action_loader.py:ActionRegistry (12 bundled actions)             │
│  ├── core/plugin_loader.py:PluginRegistry (plugins/)                       │
│  └── core/autonomous_agent.py:AutonomousAgent (multi-step planning)        │
├─────────────────────────────────────────────────────────────────────────────┤
│  Security & Identity                                                        │
│  ├── core/permission_guard.py:PermissionGuard (13 capabilities)            │
│  ├── core/permission_manager.py:PermissionManager (owner approval)         │
│  ├── core/identity.py:CallerIdentity + thread-local propagation            │
│  ├── core/auth_dialog.py:Owner authentication (Argon2id)                   │
│  └── dashboard/server.py:Phone dashboard (TLS, PBKDF2, AES-GCM)            │
├─────────────────────────────────────────────────────────────────────────────┤
│  Data & Memory                                                              │
│  ├── memory/conversation_store.py (SQLite WAL, FK, migrations)             │
│  ├── memory/memory_manager.py (long_term.json, 200K char guard)            │
│  └── core/outcome.py (done/unverified/failed/ask/started)                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Threading Model (Critical)

| Thread | Responsibility | Qt Widgets Allowed? |
|--------|----------------|---------------------|
| **Main (Qt)** | UI, window, signals, user input | ✅ YES |
| **Asyncio Event Loop** (background) | Gemini Live session, audio I/O, tool dispatch | ❌ NO |
| **Worker Threads** (thread pool) | Actions, plugins, process monitoring, history | ❌ NO |

**Rule:** Code in `actions/` and `plugins/` must **never create or touch Qt widgets**. Use `player.write_log()`, `player.show_content()`, `player.show_quiz()`, `player.show_review()`, `player.show_video()`.

---

## 3. Capability Matrix — Current Implementation Status

| # | Capability | Planned | Designed | Implemented | Tested | Verified | Accepted | Missing Work |
|---|------------|---------|----------|-------------|--------|----------|----------|--------------|
| **1** | Holographic Avatar | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **2** | Real Lip-Sync (~50 shapes/sec) | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **3** | Language-Free Mouth (Unicode reduction) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **4** | Facial Acting (brows, gaze, blink, nod) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **5** | Face as Status (thinking/listening/asleep) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **6** | Push-to-Talk (Ctrl+Space, global) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **7** | Self-Echo Guard (calibration persists) | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **8** | Runtime Self-Knowledge (live system scan) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **9** | Wake Word "Hey Jarvis" (opt-in, 2-min sleep) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **10** | Instant Acknowledgment (user's language) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **11** | Faster Live Engine (Gemini 3.1 Flash) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **12** | Self-Describing Skills (TOOL dict auto-discovery) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **13** | Recallable Memory (no size limit, search) | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **14** | Memory Panel (view/delete facts) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **15** | Undo (files, settings, desktop organize) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **16** | Real Confirmation Gate (UI token, 90s) | ✅ | ✅ | ✅ | Unit (35) | ✅ | ✅ | — |
| **17** | Audio Device Picker (measured, TEST button) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **18** | Session Continuity (resumption handle) | ✅ | ✅ | ⚠️ RAM only | Unit (1) | ⚠️ | ⚠️ | **Persist to disk (P0)** |
| **19** | Plugin System (drop .py → works) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **20** | Video on HUD (YouTube/local/URL) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **21** | Model Ladder (9 models, cooldowns) | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **22** | Choose Your Engine (Gemini Live / Pipeline) | ✅ | ✅ | ✅ | Unit (23) | ✅ | ✅ | — |
| **23** | Local & Third-Party Models (Ollama, LM Studio, etc.) | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **24** | Local Speech (Whisper + Piper, ~50 langs) | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **25** | Voice Follows Language (Whisper detection) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **26** | Reasoning Stays Private (filters `thinking` tags) | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **27** | Verified Outcomes (done/unverified/failed/ask/started) | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **28** | Close App by Name (process table, WM_CLOSE) | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **29** | Open Already Open → Bring to Front | ✅ | ✅ | ✅ | Unit | ✅ | ✅ | — |
| **30** | Untrusted Content Boundary (DATA markers) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **31** | Platform Honesty (Wayland/macOS limits) | ✅ | ✅ | ✅ | Manual | ✅ | ✅ | — |
| **32** | Hardened Phone Dashboard (TLS, PBKDF2, AES-GCM) | ✅ | ✅ | ✅ | Unit (24) | ✅ | ✅ | — |
| **33** | **Conversation History Storage (SQLite)** | ✅ | ✅ | ✅ | **42 tests** | ✅ | ✅ | — |
| **34** | **Conversation History Integration** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Wire into main.py, UI, dashboard** |
| **35** | **Resumption Handle Persistence** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Encrypt + store in meta_json (P0)** |
| **36** | **Dashboard History Endpoints** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **REST API + WebSocket replay** |
| **37** | **FTS5 Full-Text Search** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Schema migration + virtual table** |
| **38** | **Conversation Title Generation** | ✅ | ✅ | ⚠️ Partial | 0 | ⚠️ | ❌ | **Standalone LLM title generation** |
| **39** | **Voice Command "Show History"** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Intent recognition + UI trigger** |
| **40** | **Export to PDF/HTML** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Export module + sanitization** |
| **41** | **Cross-Device Sync** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Cloud backend + conflict resolution** |
| **42** | **ChatGPT ↔ Claude Code Bridge — Stage 0 (Audit)** | ✅ | ✅ | ✅ | 324 tests | ✅ | ✅ | — |
| **43** | **ChatGPT ↔ Claude Code Bridge — Stage 1 (Identity)** | ✅ | ✅ | ✅ | 446 tests | ✅ | ✅ | — |
| **44** | **ChatGPT ↔ Claude Code Bridge — Stage 2 (Handoff)** | ✅ | ✅ | ✅ | Syntax OK | ✅ | ✅ | — |
| **45** | **ChatGPT ↔ Claude Code Bridge — Stage 3 (Monitoring)** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Real-time progress updates** |
| **46** | **ChatGPT ↔ Claude Code Bridge — Stage 4 (Result Capture)** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Structured result formatting** |
| **47** | **ChatGPT ↔ Claude Code Bridge — Stage 5 (Delivery)** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Return to ChatGPT interface** |
| **48** | **ChatGPT ↔ Claude Code Bridge — Stage 6 (Workflow)** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **End-to-end orchestration** |
| **49** | **ChatGPT ↔ Claude Code Bridge — Stage 7 (E2E Verify)** | ✅ | ✅ | ❌ | 0 | ❌ | ❌ | **Full integration testing** |
| **50** | **Telegram Bot (owner pairing, commands)** | ✅ | ✅ | ✅ | Unit (49) | ✅ | ✅ | — |

---

## 4. Security Architecture (Verified Intact)

### 4.1 PermissionGuard — 13 Capabilities

| Capability | Risk | Owner Approval | Auto-Allow |
|------------|------|----------------|------------|
| `fs.read` | Low | ❌ | ✅ |
| `fs.write` | Medium | ✅ | ❌ |
| `fs.delete` | High | ✅ | ❌ |
| `fs.move` | High | ✅ | ❌ |
| `proc.exec` | High | ✅ | ❌ |
| `input.simulate` | High | ✅ | ❌ |
| `messaging.send` | High | ✅ | ❌ |
| `net.egress` | High | ✅ | ❌ |
| `remote.command` | High | ✅ | ❌ |
| `system.shutdown` | High | ✅ | ❌ |
| `memory.write` | High | ✅ | ❌ |
| `app.manage` | High | ✅ | ❌ |
| `system.monitor` | Low | ❌ | ✅ |

**Fail-Closed:** Uninitialized PermissionGuard → DENY all operations.

### 4.2 Authentication & Authorization

| Layer | Implementation | Evidence |
|-------|----------------|----------|
| **Owner Secret** | Argon2id hash in `config/owner_secret` | `permission_manager.py:_verify_owner_secret` |
| **Approval Token** | Nonce + identity_hash (one-time use) | `permission_fingerprint.py:47-48` |
| **Dashboard Pairing** | 8-char key, PBKDF2 200k rounds | `server.py:_derive_key` |
| **Command Encryption** | AES-256-GCM (authenticated) | `server.py:_decrypt` |
| **Rate Limiting** | 6 attempts / 5 min → 5 min lockout | `server.py:_Throttle` |
| **Token Expiry** | 12 hours | `server.py:_TOKEN_TTL_SECONDS` |
| **Revoke All Devices** | Clears device_sessions + live tokens | `server.py:995-1013` |
| **Windows ACL** | Restrictive ACL on config files | `permission_manager.py:236, 310` |

### 4.3 Identity Propagation (Stage 1 Complete)

```
Voice Session → CallerIdentity("voice", "voice_session")
    → ActionRegistry.run(ctx={"identity": ...})
    → _call_handler() extracts identity
    → Tool handler receives identity parameter
    → claude_code_task() records owner_identity
    
Dashboard /api/command → CallerIdentity("dashboard", device_token)
    → Same propagation chain
    
Telegram Bot → CallerIdentity("telegram", owner_user_id)
    → Same propagation chain
    
API /api/claude-task → CallerIdentity("api", "chatgpt_bridge")
    → Same propagation chain
```

**Ownership Verification:** `source + subject` must match. Anonymous filtered out. No owner = backward compatible.

---

## 5. ChatGPT ↔ MONSTER ↔ Claude Code Bridge — Status

### 5.1 Bridge Architecture (7 Stages)

| Stage | Name | Status | Key Deliverables |
|-------|------|--------|------------------|
| **0** | Architecture Audit | ✅ **COMPLETE** | Verified 324 tests; identified identity gap |
| **1** | Identity Propagation | ✅ **COMPLETE** | `core/identity.py`, task ownership in `claude_code_task.py` |
| **2** | ChatGPT Handoff Interface | ✅ **COMPLETE** | `/api/claude-task` endpoint, `_handle_claude_task()` |
| **3** | Execution Monitoring | ❌ **PENDING** | Real-time progress via WebSocket / polling |
| **4** | Result Capture | ❌ **PENDING** | Structured stdout/stderr/JSON extraction |
| **5** | Result Delivery to ChatGPT | ❌ **PENDING** | Callback / webhook / polling mechanism |
| **6** | Unified Workflow | ❌ **PENDING** | End-to-end orchestration, error handling |
| **7** | E2E Verification | ❌ **PENDING** | Full integration tests |

### 5.2 Stage 2 Implementation Details (Just Completed)

**New Dashboard Endpoint:** `POST /api/claude-task`

```json
// Request
{
  "prompt": "Create a Python fibonacci function",
  "task_id": "optional-custom-id",
  "cwd": "/path/to/project",
  "timeout": 300,
  "additional_args": [],
  "wait": false
}

// Response (async mode)
{
  "ok": true,
  "task_id": "claude_task_a1b2c3d4e5f6",
  "outcome": "started: claude_code_task | task_id=claude_task_a1b2c3d4e5f6 | mode=async"
}
```

**Identity Used:** `CallerIdentity(source="api", subject="chatgpt_bridge", display_name="ChatGPT Bridge")`

**Task Ownership:** Tasks created via bridge owned by `api:chatgpt_bridge` — only same identity can retrieve/cancel.

### 5.3 Critical Integration Limitation (from Vision Doc §3.3)

> **Do not assume ChatGPT exposes its internal conversation history, private APIs, or direct message-submission interface to local applications.**

**Supported mechanisms to investigate:**
- Officially supported API/connector
- User-authorized browser workflow
- Explicit local handoff interface (IMPLEMENTED: `/api/claude-task`)
- Supported extension/integration

**Current approach:** Local handoff via authenticated dashboard API. ChatGPT user copies prompt → submits via HTTP → MONSTER executes → result returned via same channel.

---

## 6. Conversation History — Current State

### 6.1 What's Implemented (Storage Foundation — ✅ ACCEPTED)

| Component | File | Tests | Status |
|-----------|------|-------|--------|
| SQLite Store (WAL, FK, migrations) | `memory/conversation_store.py` | 42 PASS | ✅ Complete |
| Data Models (Conversation, Message, Summary) | `memory/conversation_models.py` | Via store | ✅ Complete |
| Schema Migrations (v1, idempotent) | `memory/migrations/v001_initial_schema.py` | 3 PASS | ✅ Complete |

**Schema:**
```sql
conversations(id, title, started_at, ended_at, engine, turn_count, summary, meta_json)
messages(id, conversation_id, role, content, timestamp, sequence)
```

### 6.2 What's Missing (Integration — ❌ NOT DONE)

| Integration Point | Current State | Required Work |
|-------------------|---------------|---------------|
| **Main session lifecycle** | `_session_log` RAM-only, cleared on session end | Wire `ConversationStore` create/append/finalize |
| **UI History Panel** | Exists (Phase 1B) but reads RAM `_history` | Connect to `ConversationStore` |
| **Dashboard History** | Only live `_history` (300 entries, RAM) | Add `/api/sessions`, `/api/sessions/{id}/messages` |
| **Resumption Handle** | Captured in RAM, never persisted | Store in `meta_json` encrypted |
| **Memory Provenance** | No `conversation_id` link | Add to `memory_manager.py` |

---

## 7. Prioritized Development Roadmap

### 7.1 Weighted Milestone Analysis (from Roadmap Audit)

| # | Milestone | Weight | % Complete | Accepted Weight | Dependencies |
|---|-----------|--------|------------|-----------------|--------------|
| 1 | Qt CI Infrastructure | 5 | 0% | 0.0 | None |
| 2 | Conversation Title Generation | 10 | 10% | 1.0 | Summary generation exists |
| 3 | FTS5 Full-Text Search | 15 | 0% | 0.0 | Schema migration |
| **4** | **Resumption Handle Persistence** | **8** | **40%** | **3.2** | **Schema ready, lifecycle integrated** |
| 5 | Dashboard History Endpoints | 12 | 0% | 0.0 | #4 |
| 6 | Voice Command "Show History" | 12 | 0% | 0.0 | #4, #5 |
| 7 | Export to PDF/HTML | 10 | 0% | 0.0 | #4 |
| 8 | Cross-Device Sync | 30 | 0% | 0.0 | All history infra |

**Total: 98 weight | Accepted: 4.2 (4.3%)**

### 7.2 Critical Path (Shortest to User Value)

```
1. Resumption Handle Persistence (P0) — Enables session continuity across restarts
       ↓
2. Dashboard History Endpoints (P1) — Enables phone access to history
       ↓
3. Conversation Title Generation (P1) — Makes history readable
       ↓
4. FTS5 Full-Text Search (P2) — Performance optimization
       ↓
5. Voice Command "Show History" (P2) — UX enhancement
       ↓
6. Export to PDF/HTML (P2) — UX enhancement
       ↓
7. Cross-Device Sync (P3) — Major standalone feature
```

### 7.3 ChatGPT Bridge Critical Path (Stages 3-7)

```
Stage 3: Execution Monitoring
  ├── WebSocket progress broadcasts from ProcessMonitor
  ├── Polling endpoint for task status
  └── Integration with dashboard broadcast system
       ↓
Stage 4: Result Capture
  ├── ProcessResult → structured JSON extraction
  ├── stdout/stderr truncation + summarization
  └── Error classification mapping
       ↓
Stage 5: Result Delivery
  ├── Callback URL / webhook support
  ├── Polling endpoint for completion
  └── WebSocket push to ChatGPT client (if supported)
       ↓
Stage 6: Unified Workflow
  ├── Single entry point: submit → monitor → retrieve
  ├── Retry logic with exponential backoff
  ├── Timeout management per stage
  └── Audit logging for each bridge operation
       ↓
Stage 7: E2E Verification
  ├── Integration test: ChatGPT → MONSTER → Claude Code → result
  ├── Load testing: concurrent bridge tasks
  ├── Failure injection: network, timeout, permission denied
  └── Security test: ownership enforcement, auth bypass attempts
```

---

## 8. Immediate Next Engineering Task

### Task: Implement Resumption Handle Persistence (Milestone 4)

**Objective:** Persist Gemini Live session resumption handle to SQLite `conversations.meta_json` encrypted at rest, enabling true session continuity across application restarts.

**Priority:** P0 — Highest user value, lowest complexity, unlocks dashboard history.

**Files to Modify:**

| File | Changes Required |
|------|------------------|
| `memory/conversation_store.py` | Add `get_resume_handle()` / `set_resume_handle()` methods; update `finalize_conversation()` signature |
| `memory/conversation_models.py` | Add `resume_handle` property (computed from `meta_json`) |
| `main.py` | 3 locations: handle capture (line ~2104), session start (line ~3025), session finalize (line ~3261) |
| `tests/unit/test_conversation_store.py` | +4 tests (get/set, encryption, persistence) |
| `tests/unit/test_conversation_integration.py` | +5 tests (persist, restart load, rejection, encryption) |

**Security Requirements:**
- AES-256-GCM encryption at rest (reuse `dashboard/server.py` primitives)
- Per-install key in `config/api_keys.json` (Argon2-hashed)
- Fail-closed: decryption failure → fresh session
- Audit log: handle save/load events (without handle value)

**Acceptance Criteria:**
- [ ] `_resume_handle` persisted to `meta_json` on each `session_resumption_update`
- [ ] Handle loaded from `meta_json` on session resume
- [ ] Handle encrypted at rest (AES-256-GCM)
- [ ] App restart → existing conversation resumed with handle
- [ ] Handle rejection → cleared from `meta_json`, new conversation
- [ ] All existing tests pass (134 backend + 6 integration)
- [ ] New tests pass
- [ ] Python compilation clean

**Estimated Effort:** ~2-3 hours implementation + 1 hour testing

**Stop Conditions:**
- Any existing test fails → STOP, fix regression
- Encryption key management unclear → STOP, clarify with user
- Schema change required → STOP (should not be needed; `meta_json` exists)

---

## 9. Testing Strategy

### 9.1 Test Categories

| Category | Tools | Current Coverage | Target |
|----------|-------|------------------|--------|
| **Unit** | pytest | 446+ passing | Maintain >90% |
| **Integration** | pytest + ConversationStore | 134 backend + 6 integration | All new features |
| **UI** | pytest-qt (requires xvfb) | 74 collected, 0 executing in CI | Qt CI infrastructure |
| **E2E** | Manual / scripted | Bridge Stages 0-2 verified | Bridge Stages 3-7 |
| **Security** | Manual audit + unit | PermissionGuard 24 tests | All auth paths |

### 9.2 Test Reporting Standards (Rule 5)

Always distinguish:
- Tests **discovered** vs **collected** vs **executed**
- Tests **passed** vs **failed** vs **skipped** vs **not executed**
- Never claim a test passed if not executed
- Never label a failure "pre-existing" without evidence

---

## 10. Known Limitations & Risks

| Area | Limitation | Mitigation |
|------|------------|------------|
| **ChatGPT Integration** | No official API for conversation access | Local handoff via `/api/claude-task`; document clearly |
| **Wayland/macOS** | No screen/keyboard/mouse control | Platform honesty: tell user + model what's unavailable |
| **Session Resumption** | Handle in RAM only (until Milestone 4) | Document: restart loses continuity |
| **Conversation History** | Storage ready, not integrated (until Milestones 4-5) | Document: history not visible in UI/dashboard yet |
| **Cross-Platform** | Windows priority; macOS/Linux untested | Test each platform independently before claiming |
| **Local Models** | Slower than Gemini Live; no barge-in | Set expectations: "works when cloud unavailable" |
| **Encryption Keys** | Plaintext `api_keys.json` (by design) | Document: "Treat like password file" |
| **Qt CI** | No headless CI for UI tests | Milestone 1: xvfb/github-actions setup |

---

## 11. Release Strategy

### 11.1 Platform Priority

1. **Windows 10/11** — Primary, fully tested
2. **macOS** — After Windows stabilization (Accessibility + Screen Recording perms)
3. **Linux (X11)** — After macOS (Wayland: limited to voice/memory/files/web)

### 11.2 Installation & Updates

| Component | Current | Target |
|-----------|---------|--------|
| **Installer** | `setup.py` (OS-aware) | Signed installer / MSIX / DMG |
| **Dependencies** | requirements.txt + setup.py | Bundled / frozen |
| **Updates** | Manual git pull | In-app updater with rollback |
| **Uninstall** | Delete folder | Proper uninstaller |
| **User Data** | `config/`, `memory/` preserved | Explicit backup/restore |

### 11.3 Licensing & Business Model

| Tier | Features | Cost |
|------|----------|------|
| **Free Local** | Voice, computer control, memory, plugins, local models | Free |
| **Cloud Models** | Gemini Live, OpenAI, Groq, etc. | User's API keys |
| **Optional Services** | ElevenLabs TTS, hosted providers | User's accounts |

**Never claim a third-party service is free without evidence.**

---

## 12. Documentation Index

| Document | Purpose | Status |
|----------|---------|--------|
| `readme.md` | Product vision (21 sections) | ✅ Current |
| `AGENTS.md` | Coding agent rules | ✅ Current |
| `CLAUDE.md` | User global instructions | ✅ Current |
| `ROITZ_MASTER_VISION_AUDIT_CORRECTED.md` | 32-claim independent audit | ✅ Complete |
| `ROITZ_NEXT_DEVELOPMENT_ROADMAP_AUDIT.md` | 8-milestone roadmap with weights | ✅ Complete |
| `MONSTER_CHATGPT_CLAUDE_CODE_BRIDGE_STAGE0_AUDIT.md` | Bridge architecture audit | ✅ Complete |
| `MONSTER_CHATGPT_CLAUDE_CODE_BRIDGE_STAGE1_IMPLEMENTATION.md` | Identity propagation impl | ✅ Complete |
| `MONSTER_CHATGPT_CLAUDE_CODE_BRIDGE_STAGE2_IMPLEMENTATION.md` | Handoff interface impl | ✅ Complete |
| **`ROITZ_MONSTER_PRODUCT_VISION_AND_MASTER_ROADMAP.md`** | **This document** | ✅ **Complete** |

---

## 13. Recommended Next Task (Final Output)

### **Implement Resumption Handle Persistence (Milestone 4)**

**Why:** Highest user value (session continuity across restarts), lowest complexity (~50 lines across 3 files), schema ready, unlocks dashboard history endpoints.

**Files:** `memory/conversation_store.py`, `memory/conversation_models.py`, `main.py`, `tests/unit/test_conversation_store.py`, `tests/unit/test_conversation_integration.py`

**Security:** AES-256-GCM encryption at rest using existing dashboard primitives.

**Acceptance:** Handle persists across app restart, encrypted, fail-closed, all tests pass.

**Stop If:** Existing test regression, encryption key management unclear, schema change needed.

---

*Document generated: 2026-11-16*  
*Based on: Independent architecture audit of `D:\M MONSTER PROJECT\Roitz-main`*  
*Next action: Begin Milestone 4 implementation per Section 8*