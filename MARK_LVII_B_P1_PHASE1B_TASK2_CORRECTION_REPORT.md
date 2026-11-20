# MARK LVII-B P1 Phase 1B Task 2 — History Worker Correction Report

**Date:** 2026-11-15  
**Project:** `D:\M MONSTER PROJECT\Roitz-main`  
**Task:** Correct three HIGH-severity findings from the Task 2 independent audit

---

## Executive Summary

**ALL THREE HIGH-SEVERITY FINDINGS CORRECTED** — History Worker now ready for Task 3 integration.

| Finding | Severity | Status | Files Modified |
|---------|----------|--------|----------------|
| Request ID / Correlation Tracking | HIGH | ✅ Fixed | `actions/history_worker.py`, `ui.py` |
| Shutdown Race Correction | HIGH | ✅ Fixed | `actions/history_worker.py` |
| Accurate Search Pagination Count | HIGH | ✅ Fixed | `memory/conversation_store.py`, `actions/history_worker.py` |

**Additional Corrections:**
- Empty/whitespace query early return
- Signal emission failure handling (RuntimeError)
- Documentation of `ConversationStore.close()` thread-local behavior

**Tests:** 37/37 new HistoryWorker tests pass, 71/71 regression tests pass. Python compilation OK.

---

## 1. Files Created or Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `actions/history_worker.py` | Modified | Request ID tracking, shutdown synchronization, search count fix, error handling |
| `memory/conversation_store.py` | Modified | Added `_build_search_conditions()` and `count_search_messages()` |
| `ui.py` | Modified | Signal signatures updated with `request_id`, player methods updated, slots updated for compatibility |
| `tests/unit/test_history_worker.py` | Modified | Added 20 new tests for corrections (37 total, was 17) |

---

## 2. Root Cause and Correction for Each Finding

### 2.1 Request ID / Correlation Tracking

**Root Cause:** No request ID generation or propagation. Multiple concurrent requests could complete out of order, causing stale responses to overwrite newer results in the UI.

**Correction:**

1. **HistoryWorker** (`actions/history_worker.py`):
   - Added `_generate_request_id()` using `uuid.uuid4().hex[:16]`
   - All three public methods (`load_conversation_list`, `load_conversation_detail`, `search_messages`) now:
     - Generate a request ID at call time
     - Return the request ID to the caller
     - Pass it through to player methods
     - Include it in error emissions

2. **Player methods** (`ui.py`):
   - `show_history_list(conversations, page, total_pages, total_count, request_id=None)`
   - `show_history_detail(conv_id, title, messages, page, total_pages, total_count, request_id=None)`
   - `show_history_search(query, request_id=None)`
   - `show_history_error(error, request_id=None)`
   - All wrapped in `try/except RuntimeError` for destroyed MainWindow safety

3. **Signal signatures** (`ui.py:4498-4501`):
   ```python
   _history_list_sig   = pyqtSignal(object, int, int, int, object)  # +request_id
   _history_detail_sig = pyqtSignal(str, str, object, int, int, int, object)  # +request_id
   _history_search_sig = pyqtSignal(str, object)  # (query, request_id)
   _history_error_sig  = pyqtSignal(str, object)  # (error, request_id)
   ```

4. **MainWindow slots** (`ui.py:6568-6596`): Updated to accept optional `request_id=None` for backward compatibility (Task 3 will implement stale response rejection logic).

**Request ID Propagation Flow:**
```
MainWindow slot (e.g. _on_history_list_page_requested)
    → worker.load_conversation_list(page=1)  # returns request_id
    → worker thread executes DB query
    → player.show_history_list(..., request_id)
    → _history_list_sig.emit(..., request_id)
    → _show_history_list(..., request_id)  # Task 3: compare with current_request_id
```

---

### 2.2 Shutdown Race Correction

**Root Cause:** `_shutdown` flag checked without synchronization; thread appended to `_active_threads` after check. Race window: shutdown sets flag → new request passes check → thread added → shutdown joins old list only.

**Correction:** Added `self._lifecycle_lock = threading.Lock()` protecting all lifecycle state.

**Synchronized Operations:**

| Operation | Lock Protection |
|-----------|-----------------|
| Thread admission (`_run_in_thread`) | Check `_shutdown` + append to `_active_threads` atomically |
| Shutdown (`shutdown`) | Set `_shutdown=True` + snapshot `threads_to_join` atomically |
| `is_busy()` | Read `_active_threads` under lock |
| Thread cleanup (`_cleanup_finished_threads`) | Filter `_active_threads` under lock |

**Shutdown Sequence (no lock during join):**
```python
def shutdown(self, wait=False, timeout=2.0):
    threads_to_join = []
    with self._lifecycle_lock:
        self._shutdown = True
        if wait:
            threads_to_join = list(self._active_threads)  # Snapshot
    
    if wait:
        for thread in threads_to_join:
            thread.join(timeout=timeout)  # OUTSIDE lock
    
    with self._lifecycle_lock:
        self._active_threads.clear()
```

**Key Properties:**
- ✅ Thread admission and shutdown check atomic
- ✅ No thread admitted after `_shutdown=True`
- ✅ `shutdown()` takes consistent snapshot
- ✅ Lock never held during `join()`
- ✅ `is_busy()` and cleanup protected
- ✅ No claim of forced termination (docstring clarifies `join(timeout)` only waits)

**Tests Added:**
- `TestHistoryWorkerShutdownRace.test_no_new_threads_after_shutdown`
- `TestHistoryWorkerShutdownRace.test_concurrent_shutdown_and_request`

---

### 2.3 Accurate Search Pagination Count

**Root Cause:** `search_messages` used `len(seen_conv_ids)` from current page as `total_count`, showing wrong totals (e.g., page 1 of 3 showing "Total: 3" instead of "Total: 30").

**Correction:**

1. **ConversationStore** (`memory/conversation_store.py`):
   - Extracted `_build_search_conditions(query, conversation_id, role)` → returns `(where_clause, params)`
   - Used by both `search_messages` and new `count_search_messages`
   - Ensures identical WHERE conditions for count and data queries

   ```python
   def count_search_messages(self, query, conversation_id=None, role=None) -> int:
       where_clause, params = self._build_search_conditions(query, conversation_id, role)
       if not where_clause:
           return 0
       with self._lock:
           conn = self._get_connection()
           row = conn.execute(f"SELECT COUNT(*) FROM messages {where_clause}", params).fetchone()
       return row[0] if row else 0
   ```

2. **HistoryWorker** (`actions/history_worker.py`):
   - `search_messages` now calls `store.count_search_messages()` with same filters
   - `total_count` = actual matching messages across all pages
   - `total_pages` = `max(1, (total_count + page_size - 1) // page_size)`

**Search Flow:**
```
search_messages("Python", conversation_id="conv-1", role="assistant", page=0, page_size=10)
    → store._build_search_conditions("Python", "conv-1", "assistant")
    → WHERE content LIKE ? AND conversation_id = ? AND role = ?
    → store.search_messages(..., limit=10, offset=0)  # page data
    → store.count_search_messages("Python", "conv-1", "assistant")  # exact total
    → total_pages = ceil(total_count / page_size)
    → emit with accurate total_count and total_pages
```

**Tests Added:**
- `test_search_pagination_multiple_pages` — verifies 30 matches, 3 pages, consistent totals
- `test_search_combined_filters` — verifies count with both conversation_id and role filters
- `test_search_whitespace_only_query` — early return with total_count=0

---

## 3. Signal Signatures Before and After

### Before (Original Task 2)
```python
_history_list_sig   = pyqtSignal(object, int, int, int)
_history_detail_sig = pyqtSignal(str, str, object, int, int, int)
_history_search_sig = pyqtSignal(str)
_history_error_sig  = pyqtSignal(str)
```

### After (Corrected)
```python
_history_list_sig   = pyqtSignal(object, int, int, int, object)   # +request_id
_history_detail_sig = pyqtSignal(str, str, object, int, int, int, object)  # +request_id
_history_search_sig = pyqtSignal(str, object)  # (query, request_id)
_history_error_sig  = pyqtSignal(str, object)  # (error, request_id)
```

### Player Methods Before
```python
show_history_list(conversations, page, total_pages, total_count)
show_history_detail(conv_id, title, messages, page, total_pages, total_count)
show_history_search(query)
show_history_error(error)
```

### Player Methods After
```python
show_history_list(conversations, page, total_pages, total_count, request_id=None)
show_history_detail(conv_id, title, messages, page, total_pages, total_count, request_id=None)
show_history_search(query, request_id=None)
show_history_error(error, request_id=None)
# All wrapped in try/except RuntimeError
```

### MainWindow Slots Before
```python
_show_history_list(conversations, page, total_pages, total_count)
_show_history_detail(conv_id, title, messages, page, total_pages, total_count)
_on_history_search(query)
_show_history_error(error)
```

### MainWindow Slots After (Compatibility Fix)
```python
_show_history_list(conversations, page, total_pages, total_count, request_id=None)
_show_history_detail(conv_id, title, messages, page, total_pages, total_count, request_id=None)
_on_history_search(query, request_id=None)
_show_history_error(error, request_id=None)
```

---

## 4. Request ID Propagation Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Qt Main Thread                               │
├─────────────────────────────────────────────────────────────────────┤
│  User clicks page 2 → _on_history_list_page_requested(2)          │
│       │                                                             │
│       ▼                                                             │
│  request_id = worker.load_conversation_list(page=2)  ◄── returns ID │
│       │                                                             │
│       │  (MainWindow stores request_id as _current_list_request_id) │
│       │                                                             │
└───────┼─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Worker Thread                                  │
├─────────────────────────────────────────────────────────────────────┤
│  DB query executes...                                               │
│       │                                                             │
│       ▼                                                             │
│  player.show_history_list(convs, 2, 3, 25, request_id)            │
│       │                                                             │
│       ▼                                                             │
│  _history_list_sig.emit(convs, 2, 3, 25, request_id)              │
│       │                                                             │
└───────┼─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Qt Main Thread                               │
├─────────────────────────────────────────────────────────────────────┤
│  _show_history_list(convs, 2, 3, 25, request_id)                  │
│       │                                                             │
│       │  Task 3: if request_id != _current_list_request_id: return │
│       │         (stale response discarded)                         │
│       ▼                                                             │
│  _history_panel.set_conversation_list(convs, 2, 3, 25)            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Shutdown Synchronization Design

```
┌─────────────────────────────────────────────────────────────────┐
│                     _lifecycle_lock (threading.Lock)           │
├─────────────────────────────────────────────────────────────────┤
│  Protected State:                                               │
│    - _shutdown: bool                                            │
│    - _active_threads: List[Thread]                             │
├─────────────────────────────────────────────────────────────────┤
│  Critical Sections (atomic under lock):                        │
│                                                                 │
│  1. Thread Admission (_run_in_thread):                         │
│     with lock:                                                  │
│         if not _shutdown:                                       │
│             _active_threads.append(thread)                     │
│             thread.start()                                     │
│                                                                 │
│  2. Shutdown Snapshot (shutdown):                              │
│     with lock:                                                  │
│         _shutdown = True                                       │
│         if wait: threads_to_join = list(_active_threads)       │
│     # join OUTSIDE lock                                        │
│     for t in threads_to_join: t.join(timeout)                  │
│     with lock: _active_threads.clear()                         │
│                                                                 │
│  3. is_busy():                                                 │
│     with lock: return any(t.is_alive() for t in _active_threads)│
│                                                                 │
│  4. Cleanup (_cleanup_finished_threads):                       │
│     with lock: _active_threads = [t for t in _active_threads   │
│                                    if t.is_alive()]             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Search Count SQL/API Design

### ConversationStore API

```python
def _build_search_conditions(
    self,
    query: str,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
) -> tuple[str, list]:
    """Build WHERE clause and params shared by search and count."""
    # Returns: ("WHERE content LIKE ? AND conversation_id = ?", ["%Python%", "conv-1"])
    # Or: ("", []) for empty query

def search_messages(
    self,
    query: str,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> List[Message]:
    where_clause, params = self._build_search_conditions(query, conversation_id, role)
    params.extend([limit, offset])
    # SELECT * FROM messages {where_clause} ORDER BY timestamp_ms DESC LIMIT ? OFFSET ?

def count_search_messages(
    self,
    query: str,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
) -> int:
    where_clause, params = self._build_search_conditions(query, conversation_id, role)
    # SELECT COUNT(*) FROM messages {where_clause}
```

### Key Properties
- ✅ Single source of truth for WHERE conditions
- ✅ Identical filters for count and data queries
- ✅ Empty query returns 0 immediately (no DB round-trip)
- ✅ Invalid role raises `ValidationError` in both methods
- ✅ Thread-safe via existing `_lock`

---

## 7. Exact Test Commands and Results

### New HistoryWorker Tests (37 tests)
```bash
py -m pytest tests/unit/test_history_worker.py -v
```
**Result:** **37 passed** in 16.81s

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestHistoryWorkerConversationList` | 4 | Pagination + unique request IDs |
| `TestHistoryWorkerConversationDetail` | 3 | Message pagination, missing conv error |
| `TestHistoryWorkerSearch` | 8 | Basic, filters, pagination, empty/whitespace, combined filters |
| `TestHistoryWorkerErrorHandling` | 3 | DB errors in list, detail, search with request_id |
| `TestHistoryWorkerLifecycle` | 4 | Shutdown wait/no-wait, busy tracking, clears threads |
| `TestHistoryWorkerThreadSafety` | 2 | No Qt imports, concurrent requests |
| `TestHistoryWorkerWithNonePlayer` | 1 | None player no crash |
| `TestHistoryWorkerShutdownRace` | 2 | No new threads after shutdown, concurrent shutdown+request |
| `TestHistoryWorkerSignalEmissionFailure` | 4 | RuntimeError handling on all 4 signals |
| `TestHistoryWorkerRequestIdPropagation` | 6 | Request ID returned and propagated in all responses |

### Regression Tests (71 tests)
```bash
py -m pytest tests/unit/test_conversation_store.py tests/unit/test_conversation_integration.py tests/unit/test_history_panel.py -v
```
**Result:** **71 passed** in 14.01s

- 42 ConversationStore tests
- 6 Conversation Integration tests
- 23 HistoryPanel tests

### Python Compilation
```bash
py -m py_compile actions/history_worker.py memory/conversation_store.py ui.py
```
**Result:** `Compilation OK` — no syntax errors.

---

## 8. Remaining Limitations

| Limitation | Impact | Phase |
|------------|--------|-------|
| No `search_conversations` API in store | Search groups messages by conversation in worker; acceptable for now | Task 6 |
| MainWindow stale response rejection not implemented | Request IDs propagated but not yet compared; Task 3 will implement | Task 3 |
| `join(timeout)` cannot forcibly terminate blocked threads | Threads holding DB locks may delay shutdown; documented | Known |
| Turn count computed via full message fetch | Extra DB round-trip per assistant message; acceptable for Phase 1B | Future |
| No dedicated `get_turn_count` in store | Could be added later for efficiency | Future |

---

## 9. Explicit Confirmation: Task 3 Not Started

| Task 3 Requirement | Status |
|-------------------|--------|
| Connect MainWindow slots to HistoryWorker | ❌ Not started |
| Implement stale response rejection in slots | ❌ Not started |
| Loading/error states in UI | ❌ Not started |
| Search result handling (search_conversations API or UI adaptation) | ❌ Not started |
| Integration tests | ❌ Not started |

**Only minimal compatibility fixes applied to MainWindow slots** (added optional `request_id=None` parameter) to prevent signal-slot signature mismatch. No integration logic implemented.

---

## 10. Final Status

**TASK 2 CORRECTIONS COMPLETE**

- ✅ All three HIGH-severity audit findings corrected
- ✅ Request ID tracking implemented and propagated
- ✅ Shutdown race fixed with `threading.Lock` synchronization
- ✅ Accurate search pagination via `count_search_messages()` store API
- ✅ Empty/whitespace query early return
- ✅ Signal emission failure handling (RuntimeError)
- ✅ `ConversationStore.close()` documented as thread-local
- ✅ 37/37 HistoryWorker tests pass (20 new tests added)
- ✅ 71/71 regression tests pass
- ✅ Python compilation OK for all modified files
- ✅ Task 3 explicitly NOT started

**Ready for Task 3: Connect MainWindow slots to HistoryWorker with stale response protection.**