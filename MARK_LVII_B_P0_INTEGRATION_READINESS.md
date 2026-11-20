# MARK LVII-B — P0 ConversationStore Integration Readiness Audit

**Scope**: Strict read-only audit. Determines how to integrate the existing SQLite `ConversationStore` (Batch 1: 42 tests passing) into `main.py`'s conversation/session lifecycle.  
**Out of scope**: Gemini resumption handles (separate security design task), modifications to any source file, configuration changes, new tests.

---

## 1. Current Lifecycle Map (with exact source references)

### 1.1 Session Initialization — `JarvisLive.run()` (main.py:2820-3145)

| Phase | Lines | What Happens | State Variables Initialized |
|-------|-------|--------------|-----------------------------|
| Pre-connect setup | 2826-2882 | Permission/auth/dashboard wiring | `confirm_gate`, `auth_bind`, `pm`, `guard`, `_dashboard` |
| Reconnect loop entry | 2883-2887 | Checks `_shutdown_requested` | — |
| Model selection | 2889-2899 | Picks Live model via `_gemini.live_model()` | `LIVE_MODEL`, `live_model` |
| Resumption check | 2901 | Reads `_resume_handle` from prior session | `_resumed_with = self._resume_handle is not None` |
| Engine caps resolve | 2907 | `_resolve_engine_caps()` → `None` (Gemini) or caps dict | `_engine_caps` |
| Config build | 2908 | `_build_config()` with tools/declarations | `config` |
| Session open | 2915-2918 | `async with _open_session(...) as session` | `self.session`, `audio_in_queue`, `out_queue`, `_turn_done_event`, `_rx_deadline` |
| Transient reset | 2940-2946 | Clears vision/interrupt state | `_pending_vision`, `_vision_*`, `_interrupted` |
| Reconnect notification | 2949-2953 | If `_resumed_with`: logs "conversation restored" | — |
| Wake state | 2957-2965 | Sets `_awake` and UI state (SLEEPING/LISTENING) | `_awake`, UI state |
| Background tasks | 2989-3000 | Spawns 7-8 tasks in `TaskGroup` | `_watch_reconnect`, `_watch_stall`, `_send_realtime`, `_listen_audio`, `_receive_audio`, `_play_audio`, monitors |
| Engine warmup | 3002-3007 | If pipeline: `engine.warmup()` | `_engine` |
| Morning briefing | 3009-3014 | If enabled & not wake mode: `_send_startup_briefing()` | `_briefing_sent` |

**Critical observation**: No `Conversation` object is created here. `_session_log` (a `list[str]`) is initialized at class level (line 669) but never reset on new session — it accumulates across reconnects until `_save_session_summary()` clears it (line 2522).

### 1.2 User Message Ingestion — `_receive_audio()` (main.py:2076-2222)

| Event | Lines | Current Handling | Log Entry |
|-------|-------|------------------|-----------|
| `input_transcription` received | 2145-2149 | Appends to `in_buf` list | — |
| `turn_complete` fires | 2151-2198 | Joins `in_buf` → `full_in`, logs, appends to `_session_log` | `self.ui.write_log(f"You: {full_in}")` (2171), `self._session_log.append(f"User: {full_in}")` (2172) |
| Dashboard broadcast | 2173-2178 | If `_dashboard`: async broadcast | `type: "log", speaker: "user"` |

**Critical observation**: User message is only available at `turn_complete`. No per-message persistence. `_session_log` entry format: `"User: <text>"`.

### 1.3 Assistant Response — `_receive_audio()` (main.py:2125-2198)

| Event | Lines | Current Handling | Log Entry |
|-------|-------|------------------|-----------|
| `output_transcription` streaming | 2128-2143 | Appends to `out_buf`, feeds visemes | — |
| `turn_complete` fires | 2181-2198 | Joins `out_buf` → `full_out`, dedup check, logs, appends to `_session_log` | `self.ui.write_log(f"{self._asst_name}: {full_out}")` (2190), `self._session_log.append(f"{self._asst_name}: {full_out}")` (2191) |
| Dashboard broadcast | 2192-2197 | If `_dashboard`: async broadcast | `type: "log", speaker: "jarvis"` |

**Critical observation**: Assistant response is only available at `turn_complete`. `_session_log` entry format: `"Jarvis: <text>"` (or configured `_asst_name`).

### 1.4 Interrupt / Barge-In — `interrupt()` (main.py:1102-1210)

| Action | Lines | Effect on Conversation |
|--------|-------|------------------------|
| Set `_interrupted = True` | 1108 | Guards against duplicate |
| Increment `_generation` | 1111 | Invalidates in-flight audio chunks |
| Drain `audio_in_queue` | 1115-1125 | Discards assistant audio not yet played |
| Drain `out_queue` | 1128-1138 | Discards user audio not yet sent |
| Reset visemes/play cursor | 1141-1143 | Clears mouth animation state |
| Clear `_turn_done_event` | 1144-1145 | Resets turn boundary |
| Call `_engine.interrupt()` if pipeline | 1149-1153 | PipelineEngine increments its own `_generation`, clears `_mic`, cancels generation task, drains output queue (engine_pipeline.py:409-445) |
| Cancel task_agent executors | 1155-1187 | Cancels workers, confirmations, auth, approvals |
| Cancel inline workers | 1188-1209 | Via `WorkerRegistry.request_task_cancellation()` |

**Critical observation**: `interrupt()` does **not** reset `_session_log`. The partial assistant response that was interrupted remains in `out_buf` and is discarded at next `turn_complete` (lines 2161-2166: `in_buf = []; out_buf = []; self._visemes.reset(); continue`). No conversation-level record of the interruption exists.

### 1.5 Reconnect / Session Resumption — `_watch_reconnect()` (main.py:1367-1420 approx)

| Trigger | Lines | Behavior |
|---------|-------|----------|
| Voice change / manual reconnect | 3026-3035 | `_is_reconnect_signal(e)` → clears `_resume_handle` if clean slate, `_conn_backoff = 0`, `continue` loop |
| Resumption handle rejected | 3037-3053 | If `_resumed_with` and error mentions "resum"/"handle"/INVALID_ARGUMENT/NOT_FOUND → clears `_resume_handle`, logs "starting fresh", `continue` |
| Network error | 3117-3128 | Exponential backoff (max 60s), logs retry |
| Model quota exhausted | 3059-3074 | `_gemini.note_live_failure()` → picks next model, logs switch, immediate or 15s retry |

**Critical observation**: On reconnect, a **new** `async with _open_session()` block runs (line 2915). All transient state is reset (lines 2940-2946). `_session_log` is **not** cleared — it persists across reconnects. `_resume_handle` is only for Gemini Live server-side context; it does not restore local conversation history.

### 1.6 Session End / Summary Save — `run()` finally block (main.py:3131-3145)

```python
finally:
    self.session = None
    # Only save if there was a real conversation (≥3 turns)
    if len(self._session_log) >= 3:
        asyncio.create_task(self._save_session_summary())
```

`_save_session_summary()` (main.py:2517-2543):
1. Takes `self._session_log` (list of "User: ..." / "Jarvis: ..." strings)
2. Resets `self._session_log = []` **immediately** (line 2522)
3. Calls `gemini.text()` with last 40 turns to generate 1-2 sentence summary
4. Calls `save_session_summary(summary, lang)` → writes to `long_term.json["sessions"]` (memory_manager.py:431-454)
5. Session summaries capped at 3 entries, consumed by `pop_last_session()` on next startup (main.py:2419)

**Critical observation**: The detailed conversation (`_session_log`) is **destroyed** after summary generation. Only the 1-2 sentence summary survives in `long_term.json`. No link to any SQLite conversation ID.

---

## 2. PipelineEngine Local History (providers/engine_pipeline.py)

| Method | Lines | History Operation |
|--------|-------|-------------------|
| `send_client_content` | 315-343 | `self._history.append({"role": "user", "content": content})` |
| `send_tool_response` | 345-373 | `self._history.append({"role": "tool", "tool_call_id": ..., "name": ..., "content": ...})` |
| `_messages()` | 225-227 | Returns `[system] + self._trimmed()` |
| `_trimmed()` | 229-245 | Trims from front by char budget, preserves tool-call integrity |
| `interrupt()` | 409-445 | **Does not clear `_history`** (comment: "whatever was already said was heard") |
| `close()` | 382-386 | Sets `_closed = True`, cancels generation, queues `None` |

**Critical observation**: PipelineEngine maintains its own in-memory `_history` for LLM context. This is **separate** from `main.py`'s `_session_log` and from `ConversationStore`. On reconnect, a new `PipelineEngine` is created (main.py:2807-2817) → new empty `_history`.

---

## 3. ConversationStore Capabilities (memory/conversation_store.py)

| Capability | Method | Notes |
|------------|--------|-------|
| Create conversation | `create_conversation(Conversation)` | Auto-generates UUID, sets `started_at` |
| End conversation | `end_conversation(id, summary, turn_count)` | Sets `ended_at`, `summary`, `turn_count` |
| Add message | `add_message(Message)` | Auto-sequence, FK to conversation, CHECK role/content_type |
| Get conversation | `get_conversation(id)` | Returns `Conversation` or None |
| Get messages | `get_messages(conversation_id, limit, offset)` | Paginated, ordered by sequence |
| Search messages | `search_messages(query, limit, conversation_id)` | FTS5 on content |
| List conversations | `list_conversations(limit, offset)` | Returns `ConversationSummary` list |
| Get turn count | `get_turn_count(conversation_id)` | Count of messages |
| Update conversation | `update_conversation(id, **fields)` | Partial update |
| Delete conversation | `delete_conversation(id)` | CASCADE deletes messages |
| Backup | `backup(dest_path)` | SQLite online backup API |
| Integrity check | `integrity_check()` | `PRAGMA integrity_check` |
| WAL checkpoint | `wal_checkpoint(mode)` | `PASSIVE`/`FULL`/`RESTART`/`TRUNCATE` |
| Vacuum | `vacuum()` | `VACUUM` |
| Context manager | `__enter__`/`__exit__` | Commits on exit, rollback on exception |

**Thread model**: Each `ConversationStore` instance has thread-local connections (`self._local = threading.local()` in `__init__`). Connections are per-thread, shared within thread. Safe for multi-threaded use.

**Schema** (migrations/v001_initial_schema.py):
- `conversations` table: id (PK), title, started_at, ended_at, turn_count, summary, language, engine, meta_json, created_at, updated_at
- `messages` table: id (PK), conversation_id (FK CASCADE), role, content, content_type, sequence (UNIQUE with conversation_id), timestamp_ms, meta_json, created_at
- Indexes on `messages(conversation_id, sequence)`, `messages(conversation_id, timestamp_ms)`, `conversations(started_at DESC)`
- `user_version = 1`

---

## 4. Proposed Minimal Integration Points

### 4.1 Integration Point A: Session Start — Create Conversation

**Location**: `JarvisLive.run()`, inside `async with _open_session(...) as session:` block, after line 2934 (`self.session = session`)

**Action**:
```python
# Create ConversationStore and start new conversation
from memory.conversation_store import ConversationStore
from memory.conversation_models import Conversation
import time

self._conv_store = ConversationStore()  # instance variable
conv = Conversation(
    title="",  # empty → store will use first user message or timestamp
    started_at=int(time.time() * 1000),
    engine="gemini_live" if self._engine is None else "pipeline",
    meta_json=json.dumps({"resumed": _resumed_with}),
)
self._conv_store.create_conversation(conv)
self._current_conversation_id = conv.id
```

**Why here**: Session is fully initialized, engine known, resumption status known. Before any user message arrives.

### 4.2 Integration Point B: User Message — Store at turn_complete

**Location**: `_receive_audio()`, lines 2168-2172 (after `full_in` is constructed)

**Action**:
```python
if full_in and self._current_conversation_id:
    from memory.conversation_models import Message
    import time
    msg = Message(
        conversation_id=self._current_conversation_id,
        role="user",
        content=full_in,
        content_type="text",
        timestamp_ms=int(time.time() * 1000),
        meta_json=json.dumps({"source": "microphone"}),
    )
    self._conv_store.add_message(msg)
```

**Why here**: `turn_complete` is the only reliable point where the full user utterance is known. `input_transcription` streams partial results.

### 4.3 Integration Point C: Assistant Message — Store at turn_complete

**Location**: `_receive_audio()`, lines 2188-2191 (after `full_out` passes dedup check)

**Action**:
```python
if full_out and self._current_conversation_id:
    from memory.conversation_models import Message
    import time
    msg = Message(
        conversation_id=self._current_conversation_id,
        role="assistant",
        content=full_out,
        content_type="text",
        timestamp_ms=int(time.time() * 1000),
        meta_json=json.dumps({"source": "gemini_live" if self._engine is None else "pipeline"}),
    )
    self._conv_store.add_message(msg)
    # Update conversation turn_count
    turn_count = self._conv_store.get_turn_count(self._current_conversation_id)
    self._conv_store.update_conversation(self._current_conversation_id, turn_count=turn_count)
```

**Why here**: Symmetric with user message. `turn_count` updated for conversation list display.

### 4.4 Integration Point D: Tool Calls / Tool Results (Optional — Phase 2)

**Location**: `_execute_tool()` return (main.py:1516-1559) and `_receive_audio()` tool_call handling (lines 2209-2218)

**Action**: Store `content_type="tool_call"` and `content_type="tool_result"` messages with `meta_json` containing tool name, args, result.

**Deferral reason**: Adds complexity; core user/assistant flow works without it. Can be added after P0 validated.

### 4.5 Integration Point E: Session End — Finalize Conversation

**Location**: `run()` finally block, lines 3131-3135 (replaces current `_save_session_summary()` call)

**Action**:
```python
finally:
    self.session = None
    # Finalize conversation in SQLite store
    if hasattr(self, '_current_conversation_id') and self._current_conversation_id:
        turn_count = self._conv_store.get_turn_count(self._current_conversation_id)
        if turn_count >= 3:  # same threshold as before
            # Generate summary from stored messages (not _session_log)
            messages = self._conv_store.get_messages(self._current_conversation_id, limit=40)
            convo_text = "\n".join(f"{m.role}: {m.content}" for m in messages)
            # ... generate summary via gemini ...
            if summary:
                self._conv_store.end_conversation(
                    self._current_conversation_id,
                    summary=summary,
                    turn_count=turn_count
                )
                # Also save to long_term.json for morning briefing
                save_session_summary(summary, lang)
    # Reset for next session
    self._current_conversation_id = None
    self._conv_store = None
```

**Why here**: Replaces the destructive `_session_log` → summary flow with persistent storage. Keeps `long_term.json` session summary for backward compatibility (morning briefing).

### 4.6 Integration Point F: Reconnect — Resume Conversation

**Location**: `run()`, line 2901 (where `_resumed_with` is checked)

**Action**:
```python
_resumed_with = self._resume_handle is not None
if _resumed_with and hasattr(self, '_current_conversation_id') and self._current_conversation_id:
    # Verify conversation still exists
    conv = self._conv_store.get_conversation(self._current_conversation_id)
    if conv and conv.ended_at is None:
        # Resume existing conversation
        pass  # keep _current_conversation_id
    else:
        # Conversation ended or missing → start new
        self._current_conversation_id = None
```

**Why here**: Gemini Live resumption handle (`_resume_handle`) is independent of local conversation ID. They can diverge. Must verify local conversation is still open.

---

## 5. Data-Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         JARVIS SESSION LIFECYCLE                            │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │  run()       │
    │  (main.py)   │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐     ConversationStore.create_conversation()
    │ _open_session│──────────────────────────────────────────►
    │  (session)   │          Conversation(id, started_at, ...) │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐     _receive_audio()
    │  TaskGroup   │──────────────────┐
    └──────┬───────┘                  │
           │                          │
           ▼                          ▼
    ┌──────────────┐          ┌──────────────┐
    │_receive_audio│          │_play_audio   │
    └──────┬───────┘          └──────────────┘
           │
    ┌──────┴──────┐
    │ turn_complete│◄── input_transcription (streaming)
    └──────┬──────┘
           │
    ┌──────┴──────┐
    │ full_in =   │
    │ " ".join()  │
    └──────┬──────┘
           │
    ┌──────┴──────┐     ConversationStore.add_message()
    │ _session_log│──────────────────────────────────►
    │ .append()   │   Message(role="user", content=full_in)
    └──────┬──────┘
           │
           ▼
    ┌──────────────┐     ConversationStore.add_message()
    │ output_transc.│──────────────────────────────────►
    │ (streaming)  │   Message(role="assistant", content=full_out)
    └──────┬───────┘
           │
    ┌──────┴──────┐
    │ turn_complete│◄── output_transcription (streaming)
    └──────┬──────┘
           │
    ┌──────┴──────┐
    │ full_out =  │
    │ " ".join()  │
    └──────┬──────┘
           │
    ┌──────┴──────┐     ConversationStore.add_message()
    │ _session_log│──────────────────────────────────►
    │ .append()   │   Message(role="assistant", ...)
    └──────┬──────┘
           │
           ▼
    ┌──────────────┐
    │ interrupt()  │     (no ConversationStore action — partial messages
    │ (barge-in)   │      discarded at next turn_complete)
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Reconnect?   │──Yes──► _resume_handle check → resume or new conversation
    └──────┬───────┘
           │No
           ▼
    ┌──────────────┐     ConversationStore.end_conversation()
    │ Session end  │──────────────────────────────────►
    │ (finally)    │   Conversation(ended_at, summary, turn_count)
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐     save_session_summary() → long_term.json["sessions"]
    │ Morning      │──────────────────────────────────► (for briefing)
    │ briefing     │
    └──────────────┘
```

---

## 6. Failure and Recovery Behavior

| Failure Point | Current Behavior | With ConversationStore | Recovery Strategy |
|---------------|------------------|------------------------|-------------------|
| **Process crash mid-session** | `_session_log` lost; only prior `long_term.json` sessions remain | SQLite WAL: uncommitted transactions rolled back; committed messages persist. Conversation row exists with `ended_at=NULL`. | On next start: `list_conversations()` finds unclosed conversation → UI can offer "Resume last conversation?" |
| **Power loss / kill -9** | Same as crash | SQLite WAL + `fsync`: durable. At most last few msgs in WAL may be lost (checkpoint interval). | Same as crash. |
| **Disk full** | `long_term.json` write fails silently (logged) | `ConversationStore` methods raise `sqlite3.OperationalError` | Catch at integration points, log, continue without persistence (degraded mode). |
| **SQLite corruption** | N/A | `integrity_check()` detects; `backup()` before repair | Run `integrity_check()` on startup; if fails, auto-backup corrupt file, create fresh DB. |
| **Reconnect during turn** | `_session_log` preserved; partial buffers discarded | Current conversation ID preserved; messages already committed stay. | Integration Point F verifies conversation still open; if not, starts new. |
| **Gemini resumption handle rejected** | Logs "starting fresh", clears `_resume_handle` | Local conversation ID independent → can keep local history even if server context lost | Do NOT clear `_current_conversation_id` on handle rejection. Only clear on explicit "new conversation" user intent. |
| **PipelineEngine interrupt** | `_history` preserved (by design) | Messages already stored in SQLite unaffected | No action needed — interrupt only affects in-flight generation. |
| **Concurrent store access** | N/A | Thread-local connections; WAL allows concurrent readers + one writer | Integration points run on asyncio loop thread; store methods are thread-safe. |

---

## 7. Test Plan (Regression + New)

### 7.1 Regression Tests (Must Not Break)

| Test | Location | What It Verifies |
|------|----------|------------------|
| `test_session_log_captured` | New | `_session_log` still receives User/Jarvis entries at turn_complete |
| `test_save_session_summary_called` | New | `_save_session_summary()` invoked on session end with ≥3 turns |
| `test_morning_briefing_pop` | New | `pop_last_session()` returns and removes last entry |
| `test_interrupt_clears_buffers` | Existing | `in_buf`/`out_buf` cleared on interrupt, no duplicate logs |
| `test_reconnect_preserves_log` | Existing | `_session_log` survives reconnect (until summary saved) |
| `test_pipeline_history_preserved_on_interrupt` | Existing | PipelineEngine `_history` not cleared on interrupt |

### 7.2 New Integration Tests

| Test | Description |
|------|-------------|
| `test_conversation_created_on_session_start` | `ConversationStore.create_conversation()` called with correct engine, resumption flag |
| `test_user_message_stored_at_turn_complete` | Message with role="user", correct conversation_id, sequence=1 |
| `test_assistant_message_stored_at_turn_complete` | Message with role="assistant", sequence=2, turn_count updated |
| `test_multiple_turns_sequences_increment` | Sequence numbers 1,2,3... per conversation |
| `test_interrupt_does_not_create_partial_messages` | No message rows for interrupted assistant response |
| `test_reconnect_resumes_same_conversation` | `_current_conversation_id` reused if conversation not ended |
| `test_reconnect_starts_new_if_ended` | New conversation if prior was ended |
| `test_session_end_finalizes_conversation` | `end_conversation()` called with summary, turn_count |
| `test_session_end_saves_to_long_term_json` | `save_session_summary()` still called for backward compatibility |
| `test_conversation_store_thread_safety` | Concurrent add_message from multiple threads (simulated) |
| `test_integrity_check_on_startup` | Corrupt DB detected, backed up, fresh DB created |

### 7.3 Test Infrastructure

- Use existing `ConversationStore` (42 tests) as fixture
- Mock `gemini.text()` for summary generation
- Use `sqlite3` `:memory:` for unit tests, file DB for integration tests
- Run in `tests/unit/` alongside existing test suite

---

## 8. Risks and Unresolved Decisions

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Conversation ID / Resumption handle divergence** | High | Treat as independent: local conversation persists even if Gemini handle rejected. Document clearly. |
| **`_session_log` vs SQLite dual-write** | Medium | Phase 1: dual-write (keep `_session_log` for summary generation). Phase 2: generate summary from SQLite, remove `_session_log`. |
| **Tool call/result storage** | Low | Defer to Phase 2. Core user/assistant flow works without. |
| **PipelineEngine `_history` vs SQLite** | Medium | They serve different purposes: `_history` = LLM context (trimmed), SQLite = full archival. Document distinction. |
| **Morning briefing depends on `long_term.json`** | Low | Keep `save_session_summary()` call — dual persistence ensures briefing works. |
| **Database file location / permissions** | Low | `ConversationStore` defaults to `memory/conversations.db` (same dir as `long_term.json`). Uses existing `get_base_dir()`. |
| **Schema migration on upgrade** | Low | `MigrationRunner` handles `user_version`. Current version = 1. |
| **WAL file cleanup on Windows** | Medium | `wal_checkpoint(TRUNCATE)` on clean shutdown. Test backup/restore on Windows. |
| **Concurrent dashboard access to conversations** | Low | Dashboard reads via `list_conversations()` / `get_messages()` — read-only, WAL allows concurrent readers. |

### Unresolved Decisions (Require Human Input)

1. **Conversation title generation**: Auto-generate from first user message? Use timestamp? Leave empty?
2. **Retention policy**: Keep all conversations forever? Archive old ones? Configurable?
3. **UI for conversation history**: New dashboard endpoint? Existing panel? Separate viewer?
4. **Search integration**: Expose `search_messages()` via tool? Dashboard API?
5. **Export/Import**: JSON export of conversation? Import from other sources?

---

## 9. Files That Would Need Modification (Read-Only Audit — Not Doing It)

| File | Changes Required | Risk |
|------|------------------|------|
| `main.py` | 6 integration points (A-F) + instance vars `_conv_store`, `_current_conversation_id` | Medium — core loop, well-tested areas |
| `memory/conversation_store.py` | None (already complete) | — |
| `memory/conversation_models.py` | None (already complete) | — |
| `memory/migrations/v001_initial_schema.py` | None (already complete) | — |
| `memory/migrations/__init__.py` | None (already complete) | — |
| `memory/memory_manager.py` | None (keep `save_session_summary` for backward compat) | — |
| `providers/engine_pipeline.py` | None (keep local `_history` for LLM context) | — |
| `dashboard/server.py` | Optional: add `/api/conversations` endpoints | Low — separate feature |

---

## 10. Explicit Out-of-Scope List

| Item | Reason |
|------|--------|
| Gemini resumption handle security design | Separate task (credential/token handling, server-side trust) |
| Dashboard conversation history UI | Feature work, not integration |
| Tool call/result message storage | Phase 2 — adds schema complexity (tool_call_id, name, args) |
| Conversation search tool (`search_conversations`) | New plugin, not core integration |
| Export/import functionality | Separate feature |
| Retention/archival policy | Product decision |
| Multi-device conversation sync | Architectural change (requires cloud/backend) |
| Encryption at rest for conversations | Security hardening, separate audit |
| Conversation branching/alternatives | UX feature, not storage integration |

---

## 11. Acceptance Criteria for P0 Integration

1. **Every session creates exactly one `Conversation` row** (or zero if <3 turns)
2. **Every user turn creates one `Message(role="user")`** with correct sequence
3. **Every assistant turn creates one `Message(role="assistant")`** with correct sequence
4. **Interrupted assistant responses produce NO message rows** (discarded at next turn_complete)
5. **Reconnect reuses same `Conversation` if not ended**; creates new if ended
6. **Session end calls `end_conversation()` with summary and turn_count**
7. **`save_session_summary()` still called** → morning briefing unchanged
8. **All 42 existing ConversationStore tests pass** + new regression tests pass
9. **No SQLite errors in normal operation** (WAL, FK, constraints)
10. **Process crash mid-session leaves recoverable conversation** (`ended_at=NULL`)

---

*End of audit. This document is read-only — no source modifications made.*