# Conversation History Architecture Audit (Mark LVII-B)

**Date:** 2026-11-14  
**Type:** Independent Read-Only Audit  
**Scope:** Persistent conversation history feature — session lifecycle, memory storage, session resumption, audio/voice lifecycle, TaskAgent/WorkerRegistry interactions, persistence/backup/restore, UI components, existing tests

---

## Executive Summary

The JARVIS codebase implements **partial conversation persistence** with significant gaps:

| Component | Status | Notes |
|-----------|--------|-------|
| **Long-term memory** (facts) | ✅ Persisted | `memory/long_term.json` — identity, preferences, projects, relationships, wishes, notes |
| **Session summaries** | ✅ Persisted | 1-2 sentence summaries saved to `long_term.json['sessions']` (max 3) |
| **Gemini Live resumption handle** | ❌ **NOT persisted** | Kept in RAM only (`_resume_handle`); lost on app restart |
| **Full conversation history** (turns) | ❌ **NOT persisted** | `_session_log` in RAM only; cleared at session end after summary |
| **Activity log display** | ❌ In-memory only | `LogWidget` capped at 600 lines; no persistence |
| **Dashboard history** | ❌ In-memory only | `_history` capped at 300 messages; no persistence |
| **UI for past conversations** | ❌ Missing | No interface to view/load previous sessions |

**Verdict:** The system remembers *facts about the user* and *session summaries*, but **does not persist or expose the actual conversation history**. A fresh launch starts with zero conversation context — only the morning briefing can reference the previous session's summary (once, then it's consumed via `pop_last_session()`).

---

## 1. Session Lifecycle (`main.py`)

### 1.1 In-Memory Conversation Log
```python
# Line 669
self._session_log: list[str] = []  # conversation turns for end-of-session summary
```

- Populated in `_receive_audio()` (lines 2172, 2191):
  ```python
  self._session_log.append(f"User: {full_in}")
  self._session_log.append(f"{self._asst_name}: {full_out}")
  ```
- **Cleared immediately** after summary generation (line 2522):
  ```python
  self._session_log = []  # reset immediately so the next session starts clean
  ```
- Only sessions with ≥3 turns trigger summary (line 2520)

### 1.2 Session Summary Persistence
```python
# Lines 2517-2543: _save_session_summary()
# Calls memory_manager.save_session_summary(summary, lang)
```
- Summarized via Gemini (SMART tier, 30s timeout)
- Saved to `long_term.json['sessions']` with date, summary, language
- **Max 3 sessions retained** (line 447 in memory_manager.py)

### 1.3 Morning Briefing Integration
```python
# Lines 2418-2429: pop_last_session() called once per process launch
last = await asyncio.to_thread(pop_last_session)
# Injects into greeting: "Also briefly mention that yesterday: {summary}"
```
- **Consumes** the session entry (removed from storage)
- Only works for the **most recent** session
- No way to access older summaries after they're popped

---

## 2. Memory Storage (`memory/memory_manager.py`)

### 2.1 Long-Term Memory Structure (`long_term.json`)
```json
{
  "identity":      { "name": {"value": "...", "updated": "2026-11-14"}, ... },
  "preferences":   { ... },
  "projects":      { ... },
  "relationships": { ... },
  "wishes":        { ... },
  "notes":         { ... },
  "sessions":      [ {"date": "2026-11-13", "summary": "...", "language": "English"} ]
}
```

### 2.2 Key Characteristics
- **Thread-safe** with `Lock()` (line 17)
- **Runaway guard**: `MEMORY_MAX_CHARS = 200,000` (line 40)
- **Prompt budget**: `PROMPT_CORE_CHARS = 900` + `PROMPT_INDEX_CHARS = 420` (lines 41-42)
- **Recency-based** prompt inclusion with per-category caps
- **Index** of omitted keys enables `recall_memory` tool

### 2.3 Session Storage
```python
# Lines 431-454: save_session_summary()
# Lines 457-479: pop_last_session() — REMOVES entry after reading
```
- Sessions are **ephemeral** — popped on next briefing
- No query interface for historical sessions
- No UI exposure beyond morning briefing

---

## 3. Gemini Live Session Resumption

### 3.1 Resumption Handle Flow
```python
# Line 662: In RAM only
self._resume_handle: str | None = None

# Line 1367-1369: Passed to connect config
session_resumption=types.SessionResumptionConfig(
    handle=self._resume_handle
),

# Lines 2095-2100: Captured from server updates
_sru = getattr(response, "session_resumption_update", None)
if _sru and _sru.resumable and _sru.new_handle:
    self._resume_handle = _sru.new_handle
```

### 3.2 Critical Gaps
| Issue | Impact |
|-------|--------|
| **Not persisted to disk** | App restart = fresh conversation (no resumption) |
| **No backup/restore** | Handle loss = conversation context loss |
| **Handle rejection handling** (lines 3043-3053) | Drops handle on `INVALID_ARGUMENT`/`NOT_FOUND` — starts fresh |
| **Voice change drops handle** (line 918) | `keep_context=False` forces clean slate |

### 3.3 What Resumption Actually Preserves
- Server-side conversation context (model's memory of the dialogue)
- **Not** the local `_session_log` (that's local only)
- **Not** the activity log display
- **Not** any UI state

---

## 4. Audio/Voice Conversation Lifecycle

### 4.1 Activity Log (HUD) — `ui.py:LogWidget`
```python
# Line 1013: Hard cap
self.document().setMaximumBlockCount(600)
```
- **In-memory only** — Qt document model
- No serialization, no persistence
- Typewriter animation for display (lines 1069-1099)
- Color-coded by speaker (You/JARVIS/SYS/ERR/FILE)

### 4.2 Dashboard History — `dashboard/server.py`
```python
# Line 729
self._history: list[dict] = []

# Lines 834-836: Broadcast with cap
self._history.append(msg)
if len(self._history) > 300:
    self._history = self._history[-300:]
```
- In-memory, 300 message cap
- Sent to new WebSocket clients on connect (lines 1166+)
- **Lost on server restart**

### 4.3 PipelineEngine History — `providers/engine_pipeline.py`
```python
# Line 143
self._history: list[dict] = []

# Lines 224-245: get_history_for_context()
# Returns tail fitting history_chars budget
```
- Local pipeline only (fallback engine)
- Not used by default (Gemini Live is default)
- No persistence

---

## 5. TaskAgent / WorkerRegistry Interactions

### 5.1 WorkerRegistry (`core/worker_registry.py`)
- Tracks workers for resource conflict detection
- **In-memory only** — `WorkerRegistry._workers: dict[str, WorkerRecord]`
- No persistence across restarts
- `request_task_cancellation()` called on interrupt (main.py:1190-1209)

### 5.2 Confirmation System (`core/confirm.py`)
- Single pending confirmation (`_pending: _Pending`)
- Key format: `"task_{task_id}_{step_id}"`
- `cancel_for_task()` clears on interrupt (line 164-197)
- **In-memory only** — no persistence

### 5.3 Auth Dialog (`core/auth_dialog.py`)
- Similar pattern to confirm
- `cancel_for_task()` on interrupt
- In-memory only

### 5.4 Permission Manager (`core/permission_manager.py`)
- ACLs and approval tokens persisted in `config/api_keys.json`
- Approval tokens have nonce + expiry
- **But**: pending approvals cancelled on interrupt (not persisted mid-flow)

---

## 6. Persistence / Backup / Restore Systems

### 6.1 What IS Persisted
| File | Contents | Survives Restart |
|------|----------|------------------|
| `memory/long_term.json` | Facts, preferences, session summaries (≤3) | ✅ |
| `config/api_keys.json` | API keys, settings, permission ACLs | ✅ |
| `config/certs/` | TLS certificates for dashboard | ✅ |

### 6.2 What is NOT Persisted
| Data | Location | Lost On |
|------|----------|---------|
| Conversation turns (`_session_log`) | RAM (main.py) | Session end |
| Resumption handle (`_resume_handle`) | RAM (main.py) | App restart |
| Activity log (HUD) | Qt document (ui.py) | App restart |
| Dashboard history | RAM (dashboard/server.py) | Server restart |
| WorkerRegistry state | RAM (worker_registry.py) | App restart |
| Pending confirmations/auth | RAM (confirm.py, auth_dialog.py) | App restart |
| PipelineEngine history | RAM (engine_pipeline.py) | App restart |

### 6.3 No Backup/Restore Mechanism
- No export/import for conversation history
- No automated backup of `long_term.json`
- No migration path for schema changes

---

## 7. UI Components for Conversation Display

### 7.1 Current UI (HUD)
- **LogWidget** (ui.py:1004-1100) — Activity log only
- Shows: User turns, JARVIS responses, SYS messages, ERR, FILE
- **No**: Timestamps, search, filtering, persistence, session boundaries

### 7.2 Dashboard UI (app.html)
- Real-time feed only (WebSocket)
- Shows last 300 messages from server `_history`
- **No**: Historical session loading, date separation, search

### 7.3 Missing UI Capabilities
| Capability | Status |
|------------|--------|
| View past conversations | ❌ |
| Search conversation history | ❌ |
| Load/resume specific session | ❌ |
| Export conversation | ❌ |
| Session timeline/calendar | ❌ |
| Per-session memory context | ❌ |

---

## 8. Existing Tests Coverage

### 8.1 Relevant Test Files
| File | Coverage |
|------|----------|
| `test_interrupt_recovery.py` | Interrupt state recovery (queues, generation, workers, confirmations) |
| `test_task_agent.py` | Task execution, some session handling |
| `test_gemini_live_interrupt.py` | Batch 4: Live interrupt integration |
| `test_confirmation_interrupt.py` | Batch 3: Confirmation cancellation |
| `test_worker_cancellation.py` | Batch 2: Worker cancellation |

### 8.2 Missing Test Coverage
- ❌ Session summary save/load
- ❌ Resumption handle capture/replay
- ❌ Memory persistence across restarts
- ❌ Morning briefing session injection
- ❌ Conversation history persistence
- ❌ Long-term memory trim/notifier
- ❌ Dashboard history broadcast

---

## 9. Critical Architecture Findings

### 9.1 The "Conversation" is Split Across Three Unconnected Systems
```
┌─────────────────────────────────────────────────────────────────┐
│  LOCAL FACTS (long_term.json)                                   │
│  ├── identity, preferences, projects, relationships, wishes,   │
│  │   notes — PERSISTED, queried via recall_memory tool         │
│  └── sessions[≤3] — summaries only, POPPED on briefing        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  GEMINI LIVE SESSION (server-side)                              │
│  ├── Resumption handle (_resume_handle) — RAM ONLY             │
│  ├── Server maintains conversation context                     │
│  └── Handle rejected → fresh session (no local fallback)       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LOCAL DISPLAY (ephemeral)                                      │
│  ├── LogWidget (600 lines) — HUD activity log                  │
│  ├── Dashboard _history (300 msgs) — phone feed                │
│  └── _session_log (RAM) — cleared after summary                │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Session Resumption ≠ Conversation History
- Resumption restores **server-side model context** only
- Local `_session_log` is **not** restored
- Activity log is **not** restored
- User sees "Reconnected — conversation restored" but **scrollback is gone**

### 9.3 Morning Briefing is the Only History Bridge
- Single summary injected once
- Then **consumed and deleted** (`pop_last_session`)
- No access to older sessions
- No user control over briefing content

### 9.4 No "Conversation" Entity Exists
- No `Conversation` class or data structure
- No session ID correlation across components
- No way to associate memory facts with specific conversations
- No provenance tracking (which conversation yielded which fact)

---

## 10. Recommendations (Priority Order)

### P0 — Data Loss Prevention
1. **Persist resumption handle** to disk (encrypted) for surviving app restarts
2. **Persist `_session_log`** alongside handle for local scrollback restoration
3. **Add session metadata** (id, start_time, end_time, turn_count) to summaries

### P1 — History Access
4. **Create `ConversationHistory` module** with:
   - Session enumeration (date, summary, turn count)
   - Full turn retrieval for a session
   - Search across sessions
5. **Add UI panel** for conversation history (timeline + search)
6. **Dashboard endpoint** for historical session loading

### P2 — Architecture
7. **Introduce `Conversation` dataclass** linking:
   - Session ID ↔ Resumption handle ↔ Local turns ↔ Summary ↔ Memory facts
8. **Add provenance** to memory entries (which session created them)
9. **Implement backup/restore** for `long_term.json`

### P3 — Resilience
10. **Handle rejection fallback**: On handle rejection, offer to "restore from local log" if available
11. **Periodic checkpoint**: Save `_session_log` + handle every N turns
12. **Migration tool** for schema changes to memory format

---

## 11. Files Referenced

| File | Key Lines |
|------|-----------|
| `main.py` | 669, 1102-1210, 1367-1369, 2095-2100, 2172, 2191, 2517-2543, 2949-2953, 3043-3053 |
| `memory/memory_manager.py` | 47-55, 431-479, 194-324, 329-380 |
| `ui.py` | 1004-1100 (LogWidget), 7526-7527 (write_log) |
| `dashboard/server.py` | 729, 834-836, 1166+ |
| `providers/engine_pipeline.py` | 143, 224-245 |
| `core/worker_registry.py` | 440-455 (request_task_cancellation) |
| `core/confirm.py` | 164-197 (cancel_for_task) |
| `core/auth_dialog.py` | 194-228 (cancel_for_task) |
| `actions/proactive.py` | 100-104 (recent_turns usage) |
| `tests/unit/test_interrupt_recovery.py` | SessionLifecycleRecovery class |

---

## 12. Conclusion

**The JARVIS codebase does not implement a persistent conversation history feature.** It implements:

1. **Long-term fact memory** (well-designed, persisted, queried on demand)
2. **Session summaries** (persisted but ephemeral — consumed by briefing)
3. **Server-side session resumption** (works for reconnects, lost on restart)
4. **Ephemeral display logs** (HUD + dashboard, capped, in-memory only)

**Critical gap:** There is no way for a user to:
- See what they talked about last week
- Resume a specific past conversation
- Search conversation history
- Export their conversation data
- Correlate memory facts with the conversations that created them

The architecture treats "conversation history" as three disconnected concerns rather than a unified feature. A proper implementation would require a `ConversationHistory` module with persistence, query API, and UI — none of which exist today.