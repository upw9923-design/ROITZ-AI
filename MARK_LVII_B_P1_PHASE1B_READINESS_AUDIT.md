# MARK LVII-B P1 Phase 1B — Backend Integration Readiness Audit

**Date:** 2026-11-15  
**Project:** `D:\M MONSTER PROJECT\Roitz-main`  
**Audit Type:** READ-ONLY readiness assessment for Phase 1B  
**Baseline:** Phase 1A (HistoryPanel UI) — ACCEPTED; Phase 0 (ConversationStore) — ACCEPTED

---

## Executive Verdict

### **CONDITIONALLY READY**

**Conditions:**
1. ❌ **Critical API mismatch**: `main.py` calls `ConversationStore.add_message()`, `get_turn_count()`, `end_conversation()` — none exist in `conversation_store.py`
2. ⚠️ **No async worker pattern** for history operations — will need to implement thread-safe background loading
3. ⚠️ **Stale response protection** not yet implemented for pagination/detail/search
4. ✅ UI signals, data models, and database operations are well-defined and tested
5. ✅ Thread-safe singleton `ConversationStore` with WAL mode supports concurrent access

**Phase 1B can proceed** but must first resolve the API mismatch (Condition 1) and implement the async worker pattern.

---

## 1. Current Implementation Map

### 1.1 Database Layer (`memory/conversation_store.py`)

**ConversationStore Class — Public API:**

| Method | Signature | Purpose |
|--------|-----------|---------|
| `create_conversation` | `(conv: Conversation) -> Conversation` | Insert new conversation |
| `get_conversation` | `(conversation_id: str) -> Conversation` | Fetch by ID; raises `ConversationNotFoundError` |
| `update_conversation` | `(conv: Conversation) -> Conversation` | Update metadata; raises `ConversationNotFoundError` |
| `finalize_conversation` | `(conversation_id, summary?, turn_count?) -> Conversation` | Mark ended; set summary/turn_count |
| `delete_conversation` | `(conversation_id: str) -> None` | Cascade delete |
| `list_conversations` | `(limit=50, offset=0, order_by="started_at", descending=True) -> List[ConversationSummary]` | Paginated list |
| `count_conversations` | `() -> int` | Total count |
| `append_message` | `(msg: Message) -> Message` | Insert with auto-sequence; raises `ConversationNotFoundError`, `ValidationError`, `SequenceConflictError` |
| `get_message` | `(message_id: str) -> Message` | Fetch by ID; raises `MessageNotFoundError` |
| `get_messages` | `(conversation_id, limit?, offset=0, order_by="sequence", descending=False) -> List[Message]` | Paginated messages |
| `get_message_count` | `(conversation_id: str) -> int` | Count messages |
| `delete_message` | `(message_id: str) -> None` | Delete single message |
| `search_messages` | `(query, conversation_id?, role?, limit=20, offset=0) -> List[Message]` | Text search with filters |
| `integrity_check` | `() -> Tuple[bool, List[str]]` | SQLite integrity |
| `backup` | `(dest_path: Path) -> None` | Hot backup |

**Threading Model:**
- Single `_lock = threading.Lock()` serializes transactions
- Thread-local connections via `threading.local()`
- WAL mode allows concurrent readers/writers at SQLite level
- All public methods acquire `_lock` for the duration of the operation

**Singleton Access:**
- `get_store()` — thread-safe singleton
- `reset_store()` — for testing

---

### 1.2 Data Models (`memory/conversation_models.py`)

| Class | Key Fields |
|-------|------------|
| `Conversation` | `id, title, started_at, ended_at, turn_count, summary, language, engine, meta_json, created_at, updated_at` |
| `Message` | `id, conversation_id, role, content, content_type, sequence, timestamp_ms, meta_json, created_at` |
| `ConversationSummary` | Lightweight: `id, title, started_at, ended_at, turn_count, summary, language, engine` |

---

### 1.3 UI Layer (`history_panel.py`)

**Signals Emitted (User Actions):**
```python
conversation_selected = pyqtSignal(str)          # conversation_id
list_page_requested = pyqtSignal(int)            # page (0-based)
detail_page_requested = pyqtSignal(int)          # page (0-based)
search_requested = pyqtSignal(str)               # query (debounced 300ms)
```

**Public Methods (Called from MainThread):**
| Method | Parameters | Purpose |
|--------|------------|---------|
| `set_conversation_list` | `conversations: list[dict], page, total_pages, total_count` | Populate list view |
| `set_message_detail` | `conversation_id, title, messages: list[dict], page, total_pages, total_count` | Populate detail view |
| `set_detail_loading` | `loading: bool` | Show/hide loading |
| `set_detail_error` | `error: str` | Show error |
| `set_list_loading` | `loading: bool` | Show/hide list loading |
| `clear_selection` | — | Reset detail to empty |

**Expected Conversation Dict Keys:** `id, title, started_at, ended_at, turn_count, summary, engine`
**Expected Message Dict Keys:** `role, content, content_type, sequence, timestamp_ms`

---

### 1.4 MainWindow Integration (`ui.py`)

**Thread-Safe Signals (from worker threads):**
```python
_history_list_sig   = pyqtSignal(object, int, int, int)  # (conversations, page, total_pages, total_count)
_history_detail_sig = pyqtSignal(str, str, object, int, int, int)  # (conv_id, title, messages, page, total_pages, total_count)
_history_search_sig = pyqtSignal(str)                     # query
_history_error_sig  = pyqtSignal(str)                     # error message
```

**UI Slots (Main Thread):**
```python
_show_history_list(conversations, page, total_pages, total_count)
_show_history_detail(conv_id, title, messages, page, total_pages, total_count)
_on_history_search(query)          # Currently stub — Phase 1B to implement
_show_history_error(error)
```

**User Action Handlers (Currently Stubs):**
```python
_on_history_conversation_selected(conv_id)      # Logs only
_on_history_list_page_requested(page)           # Logs only
_on_history_detail_page_requested(page)         # Logs only
_on_history_search_requested(query)             # Logs only
```

**Thread-Safe Public Methods (on `JarvisUI` / `player`):**
```python
show_history_list(conversations, page, total_pages, total_count)
show_history_detail(conversation_id, title, messages, page, total_pages, total_count)
show_history_search(query)
show_history_error(error)
```

---

### 1.5 Application Flow (`main.py`)

**Conversation Lifecycle:**
1. **Session Start** (`_handle_connection` ~line 3016): Create `ConversationStore`, create `Conversation` if none or previous ended
2. **User Message** (~line 2178): `append_message(Message(role="user", ...))`
3. **Assistant Message** (~line 2212): `append_message(Message(role="assistant", ...))` + update `turn_count`
4. **Session End** (~line 3214): If `turn_count >= 3`:
   - Fetch messages, generate summary via `gemini.text()`
   - Call `end_conversation()` — **DOES NOT EXIST** (should be `finalize_conversation`)
   - Call `save_session_summary()` for `long_term.json`

**Error Handling:** All store calls wrapped in `try/except`; failures logged, session continues in-memory.

---

## 2. Existing APIs and Exact Signatures

### 2.1 Database APIs (Verified Working)

```python
# Conversation listing (pagination ready)
store.list_conversations(limit=50, offset=0, order_by="started_at", descending=True) -> List[ConversationSummary]
store.count_conversations() -> int

# Conversation detail
store.get_conversation(conversation_id) -> Conversation

# Messages (pagination ready)
store.get_messages(conversation_id, limit=None, offset=0, order_by="sequence", descending=False) -> List[Message]
store.get_message_count(conversation_id) -> int

# Search (pagination ready)
store.search_messages(query, conversation_id=None, role=None, limit=20, offset=0) -> List[Message]

# Conversation CRUD
store.create_conversation(conv) -> Conversation
store.update_conversation(conv) -> Conversation
store.finalize_conversation(conversation_id, summary=None, turn_count=None) -> Conversation
store.delete_conversation(conversation_id) -> None

# Message CRUD
store.append_message(msg) -> Message
store.get_message(message_id) -> Message
store.delete_message(message_id) -> None
```

### 2.2 Missing Methods Called by `main.py`

| Called in `main.py` | Exists in Store? | Correct Name / Implementation |
|---------------------|------------------|-------------------------------|
| `add_message(msg)` | ❌ NO | `append_message(msg)` |
| `get_turn_count(conv_id)` | ❌ NO | Compute: `sum(1 for m in get_messages(conv_id) if m.role == "assistant")` |
| `end_conversation(conv_id, summary, turn_count)` | ❌ NO | `finalize_conversation(conv_id, summary, turn_count)` |

**These MUST be fixed before Phase 1B can integrate cleanly.**

---

## 3. UI-to-Database Integration Gaps

### 3.1 Signal Flow (Phase 1B Must Implement)

```
User Action → HistoryPanel Signal → MainWindow Slot → Worker Thread → ConversationStore → _history_*_sig → MainWindow Slot → HistoryPanel.set_*
```

| User Action | HistoryPanel Signal | MainWindow Slot (Current) | Required Implementation |
|-------------|---------------------|---------------------------|-------------------------|
| Click conversation | `conversation_selected(str)` | `_on_history_conversation_selected` (logs) | Load messages page 0; emit `_history_detail_sig` |
| Click list Prev/Next | `list_page_requested(int)` | `_on_history_list_page_requested` (logs) | Load page; emit `_history_list_sig` |
| Click detail Prev/Next | `detail_page_requested(int)` | `_on_history_detail_page_requested` (logs) | Load messages page; emit `_history_detail_sig` |
| Type in search | `search_requested(str)` | `_on_history_search_requested` (logs) | Search; emit `_history_list_sig` or new `_history_search_sig` |

### 3.2 Data Transformation Needed

| Source | Target | Transformation |
|--------|--------|----------------|
| `ConversationSummary` | `dict` for `set_conversation_list` | Extract: `id, title, started_at, ended_at, turn_count, summary, engine` |
| `Message` | `dict` for `set_message_detail` | Extract: `role, content, content_type, sequence, timestamp_ms` |
| `Conversation` | `dict` for detail header | Extract: `title` |

---

## 4. Race-Condition and Concurrency Analysis

### 4.1 Current Protections

| Layer | Mechanism |
|-------|-----------|
| SQLite | WAL mode + `PRAGMA foreign_keys=ON` + `busy_timeout=5000` |
| Store | Single `_lock` per instance serializes transactions |
| Thread-local | Each thread gets own connection |
| UI | All panel updates via `pyqtSignal` → main thread slots |

### 4.2 Required for Phase 1B

| Risk | Scenario | Mitigation Needed |
|------|----------|-------------------|
| **Stale list response** | User clicks page 2, then page 1 quickly; page 2 returns after page 1 | Track `current_list_request_id`; discard responses with older ID |
| **Stale detail response** | User selects conv A, then conv B; conv A messages return after conv B | Track `current_detail_conv_id`; discard if mismatch |
| **Stale search response** | User types "foo", then "bar"; "foo" results return after "bar" | Track `current_search_query`; discard if query changed |
| **Concurrent DB access** | History worker + main session both writing | Store `_lock` already serializes; use same singleton |

### 4.3 Worker Thread Pattern (Existing in Codebase)

```python
# Pattern from ui.py (e.g., line 3819, 4202, 7011)
threading.Thread(target=worker_fn, daemon=True).start()

# Worker calls thread-safe UI methods:
player.show_history_list(...)
player.show_history_detail(...)
player.show_history_error(...)
```

**No `QThread` or `asyncio` in workers** — uses `threading.Thread` + `pyqtSignal` for UI updates.

---

## 5. Security and Privacy Analysis

### 5.1 Data Sensitivity

| Data Type | Risk | Current Handling |
|-----------|------|------------------|
| Conversation titles | Low | Stored in DB, shown in list |
| Message content | **High** | Stored in DB, shown in detail; may contain PII, secrets, credentials |
| Tool results | **High** | `content_type="tool_result"` may contain command output, file contents |
| Metadata (`meta_json`) | Medium | JSON with source, confidence, tool names |

### 5.2 Required Protections

1. **No full conversation dump** in list view — only summary fields
2. **Detail view on-demand** — messages loaded only when conversation selected
3. **Search results** — return `Message` objects; UI must filter sensitive `content_type` if needed
4. **Error messages** — never leak SQL or internal paths
5. **Access control** — none currently (single-user app); future: per-user isolation

### 5.3 `meta_json` Exposure Risk

- `Message.meta_json` may contain: tool names, arguments, results, confidence scores
- `Conversation.meta_json` may contain: resumption status, tags
- **Phase 1B decision**: Do NOT send `meta_json` to UI unless explicitly needed

---

## 6. Required Implementation Tasks (Dependency Order)

### Task 1: Fix `main.py` API Mismatch (BLOCKER)
- [ ] Replace `add_message` → `append_message`
- [ ] Replace `get_turn_count` → compute from messages
- [ ] Replace `end_conversation` → `finalize_conversation`
- **Verification**: `test_conversation_integration.py` passes

### Task 2: Implement History Worker Module
Create `actions/history_worker.py` (or similar) with:
- [ ] `load_conversation_list(page, page_size)` → emits `_history_list_sig`
- [ ] `load_conversation_detail(conv_id, page, page_size)` → emits `_history_detail_sig`
- [ ] `search_conversations(query, page, page_size)` → emits `_history_list_sig` (or new search signal)
- [ ] Stale request cancellation via request IDs
- [ ] Error handling → emits `_history_error_sig`

### Task 3: Connect MainWindow Slots to Worker
- [ ] `_on_history_conversation_selected` → call worker `load_conversation_detail(conv_id, 0, PAGE_SIZE)`
- [ ] `_on_history_list_page_requested` → call worker `load_conversation_list(page, PAGE_SIZE)`
- [ ] `_on_history_detail_page_requested` → call worker `load_conversation_detail(current_conv_id, page, PAGE_SIZE)`
- [ ] `_on_history_search_requested` → call worker `search_conversations(query, 0, PAGE_SIZE)`

### Task 4: Implement Stale Response Protection
- [ ] `self._history_list_request_id` — increment on each list request; worker includes ID; slot discards if mismatch
- [ ] `self._history_detail_conv_id` — track current conv; slot discards if mismatch
- [ ] `self._history_search_query` — track current query; slot discards if mismatch

### Task 5: Loading/Error States
- [ ] Show `set_list_loading(True)` before list request; `False` on response
- [ ] Show `set_detail_loading(True)` before detail request; `False` on response
- [ ] Handle DB errors → `show_history_error()`

### Task 6: Search Result Handling
- [ ] Decision: reuse `list` view for search results, or add dedicated search view?
- [ ] If reuse: `search_conversations` returns `ConversationSummary` list? Or `Message` list?
- [ ] Current `search_messages` returns `Message` — may need new `search_conversations` returning `ConversationSummary`

### Task 7: Integration Tests
- [ ] Test list pagination loads correct pages
- [ ] Test detail pagination loads correct message pages
- [ ] Test conversation selection loads detail
- [ ] Test search returns results
- [ ] Test rapid navigation discards stale responses
- [ ] Test DB error shows error state

---

## 7. Relevant Tests for Verification

| Task | Test File | Test Cases |
|------|-----------|------------|
| Task 1 | `test_conversation_integration.py` | `test_reconnect_resumes_active_conversation`, `test_session_finalization_with_3_or_more_turns` |
| Task 2-3 | New: `test_history_integration.py` | List load, detail load, search, pagination |
| Task 4 | New: `test_history_race_conditions.py` | Rapid click, stale response discard |
| Task 5 | New: `test_history_states.py` | Loading, error, empty states |
| All | Existing: `test_conversation_store.py` | `TestSearchAndPagination`, `TestConcurrentInsertion` |

**Existing Tests Passing (Verified):**
- `test_conversation_store.py`: 42/42 passed
- `test_conversation_integration.py`: 6/6 passed
- `test_history_panel.py`: 23/23 passed

---

## 8. Risks and Unresolved Questions

### 8.1 High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **API mismatch in `main.py`** | Session storage broken; conversations not persisted | Fix before any Phase 1B work (Task 1) |
| **No `search_conversations` API** | Search returns messages, not conversations; UI expects conversations for list view | Add `search_conversations` to store, or adapt UI to show message search results |
| **Stale responses on rapid UI interaction** | Wrong data shown; user confusion | Implement request ID tracking (Task 4) |

### 8.2 Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **DB lock contention** | History worker + main session both hit `_lock` | Keep transactions short; use `LIMIT` in queries; WAL helps |
| **Large conversation detail load** | Fetching all messages for a long conversation blocks UI | Pagination already in `get_messages`; load page-by-page |
| **Search performance** | `LIKE %query%` without FTS5 is slow on large DBs | Acceptable for Phase 1B; FTS5 deferred |

### 8.3 Unresolved Questions

1. **Search UX**: Does search filter the conversation list, or show message matches in a separate view?
   - Current `search_messages` returns `Message` objects with `conversation_id`
   - UI `set_conversation_list` expects conversation dicts
   - **Decision needed**: Add `search_conversations` returning `ConversationSummary`, or change search UI

2. **Page Size**: What is the default page size for list/detail?
   - Store defaults: `list_conversations(limit=50)`, `get_messages(limit=None)`, `search_messages(limit=20)`
   - UI has no page size concept yet
   - **Recommendation**: Define `HISTORY_PAGE_SIZE = 20` constant

3. **Active Conversation Indicator**: List shows "● Active" / "○ Ended" based on `ended_at`. Real-time updates?
   - Current: static at load time
   - Future: signal when conversation ends to refresh list

4. **Conversation Title Editing**: Not in Phase 1B scope, but UI shows titles. Backend supports `update_conversation`.

5. **Dashboard/Phone Sync**: `dashboard/server.py` broadcasts logs. Should history changes broadcast?
   - Not in Phase 1B scope.

---

## 9. Final Verdict

### **CONDITIONALLY READY**

**Blocking Issues (Must Fix First):**
1. `main.py` calls non-existent `ConversationStore` methods (`add_message`, `get_turn_count`, `end_conversation`) — **fix in Task 1**

**Ready to Implement (After Task 1):**
- Database APIs are complete, tested, and support pagination
- UI signals and slots are defined and connected
- Thread-safe signal pattern exists and is used throughout codebase
- Data models match UI expectations
- Error handling patterns established

**Estimated Effort:** ~5-7 focused tasks after API fix

---

*Audit performed read-only. No source files modified.*