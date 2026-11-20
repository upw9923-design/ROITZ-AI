# MARK LVII-B P1 Phase 1B Task 3 — MainWindow Stale Response Protection Readiness Audit

**Date:** 2026-11-15  
**Project:** `D:\M MONSTER PROJECT\Roitz-main`  
**Auditor:** Senior Python/PyQt6 Architect, Concurrency Auditor  
**Mode:** STRICT READ-ONLY — No files modified

---

## 1. Final Verdict: **READY**

The codebase has all necessary primitives for Task 3. Request IDs are generated, propagated, and reach MainWindow slots. No blocking defects exist. Implementation can proceed.

---

## 2. Existing Architecture and Request Lifecycle

### 2.1 Operation: Conversation List Loading

```
User clicks pagination → HistoryPanel.list_page_requested(page) [ui.py:6605-6608]
    → MainWindow._on_history_list_page_requested(page) [ui.py:6605-6608]
        → worker.load_conversation_list(page) [actions/history_worker.py:106-163]
            → request_id = _generate_request_id() [line 120]
            → thread starts with work() closure capturing request_id
            → store.list_conversations(limit, offset) [line 129]
            → player.show_history_list(convs, page, total_pages, total_count, request_id) [line 148]
                → _history_list_sig.emit(..., request_id) [ui.py:7688-7691]
                    → _show_history_list(..., request_id) [ui.py:6568-6578]
                        → _history_panel.set_conversation_list(...) [history_panel.py:360-421]
```

**Request ID Path:** `load_conversation_list()` → `work()` closure → `player.show_history_list()` → `_history_list_sig` → `_show_history_list()`  
**Current Tracking:** None — `request_id` accepted but ignored in `_show_history_list` (line 6568)

### 2.2 Operation: Conversation Detail Loading

```
User clicks conversation → HistoryPanel.conversation_selected(conv_id) [history_panel.py:546-552]
    → MainWindow._on_history_conversation_selected(conv_id) [ui.py:6598-6603]
        → worker.load_conversation_detail(conv_id) [actions/history_worker.py:165-243]
            → request_id = _generate_request_id() [line 185]
            → thread starts with work() capturing request_id, conv_id
            → store.get_conversation(conv_id) + store.get_messages(...) [lines 194, 204]
            → player.show_history_detail(conv_id, title, msgs, page, total_pages, total_count, request_id) [line 226]
                → _history_detail_sig.emit(..., request_id) [ui.py:7717-7721]
                    → _show_history_detail(..., request_id) [ui.py:6580-6584]
                        → _history_panel.set_message_detail(...) [history_panel.py:422-511]
```

**Request ID Path:** `load_conversation_detail()` → `work()` → `player.show_history_detail()` → `_history_detail_sig` → `_show_history_detail()`  
**Current Tracking:** None — `request_id` accepted but ignored in `_show_history_detail` (line 6580)

### 2.3 Operation: Message Search

```
User types in search → HistoryPanel.search_requested(query) [history_panel.py:564-569]
    → MainWindow._on_history_search_requested(query) [ui.py:6615-6618]
        → worker.search_messages(query) [actions/history_worker.py:245-345]
            → request_id = _generate_request_id() [line 273]
            → early return for empty query emits with request_id [lines 276-279]
            → thread starts with work() capturing request_id, query, filters
            → store.search_messages(...) + store.count_search_messages(...) [lines 288, 297]
            → player.show_history_list(results, page, total_pages, total_count, request_id) [line 330]
                → _history_list_sig.emit(..., request_id) [ui.py:7688-7691]
                    → _show_history_list(..., request_id) [ui.py:6568-6578]
                        → _history_panel.set_conversation_list(...) [history_panel.py:360-421]
```

**Request ID Path:** `search_messages()` → `work()` → `player.show_history_list()` → `_history_list_sig` → `_show_history_list()`  
**Current Tracking:** None — search reuses list signal/slot; `request_id` ignored

---

## 3. Exact Stale-Response Vulnerabilities

### Scenario 1: Conversation Detail — **VULNERABLE**
```
User opens Conversation A → Request A (id=req-A) starts
User opens Conversation B → Request B (id=req-B) starts
Response B arrives → _show_history_detail(..., req-B) → UI shows B's messages
Response A arrives → _show_history_detail(..., req-A) → UI OVERWRITTEN with A's messages
```
**Vulnerability:** `_show_history_detail` at `ui.py:6580` ignores `request_id`. No tracking of "current detail request."

### Scenario 2: Search — **VULNERABLE**
```
User searches "alpha" → Request A (id=req-A) starts
User searches "beta"  → Request B (id=req-B) starts
Response B arrives → _show_history_list(..., req-B) → UI shows "beta" results
Response A arrives → _show_history_list(..., req-A) → UI OVERWRITTEN with "alpha" results
```
**Vulnerability:** Search reuses `_history_list_sig` → `_show_history_list` which ignores `request_id`. No tracking of "current search request."

### Scenario 3: Conversation List — **VULNERABLE**
```
User requests page 1 → Request A (id=req-A) starts
User requests page 2 → Request B (id=req-B) starts
Response B arrives → _show_history_list(..., req-B) → UI shows page 2
Response A arrives → _show_history_list(..., req-A) → UI OVERWRITTEN with page 1
```
**Vulnerability:** `_show_history_list` at `ui.py:6568` ignores `request_id`. No tracking of "current list request."

### Scenario 4: Cross-Operation Independence — **PARTIALLY PROTECTED**
- Detail uses `_history_detail_sig` → `_show_history_detail`
- List/Search both use `_history_list_sig` → `_show_history_list`
- **Risk:** A stale search response could overwrite a fresh list page (or vice versa) because they share the same slot
- **Mitigation needed:** Separate request tracking per operation type

### Scenario 5: Errors and Empty Results — **VULNERABLE**
```
Request A (detail) starts → loading indicator shown
Request B (detail) starts → loading indicator shown
Response B succeeds → UI shows B's messages, loading hidden
Response A fails → _show_history_error(..., req-A) → _show_history_error ignores request_id
    → Sets error on detail view, CLEARING B's messages!
```
**Vulnerability:** `_show_history_error` at `ui.py:6592` ignores `request_id`. An old error overwrites a newer success.

---

## 4. Exact Files, Methods, Slots, and Line Numbers

### Files Requiring Changes

| File | Methods/Slots | Lines | Current State |
|------|---------------|-------|---------------|
| `ui.py` | `_show_history_list` | 6568-6578 | Accepts `request_id` but ignores it |
| `ui.py` | `_show_history_detail` | 6580-6584 | Accepts `request_id` but ignores it |
| `ui.py` | `_on_history_search` | 6586-6590 | Accepts `request_id` but does nothing (stub) |
| `ui.py` | `_show_history_error` | 6592-6596 | Accepts `request_id` but ignores it |
| `ui.py` | `_on_history_conversation_selected` | 6598-6603 | Must call worker + track request |
| `ui.py` | `_on_history_list_page_requested` | 6605-6608 | Must call worker + track request |
| `ui.py` | `_on_history_detail_page_requested` | 6610-6613 | Must call worker + track request |
| `ui.py` | `_on_history_search_requested` | 6615-6618 | Must call worker + track request |
| `ui.py` | `MainWindow.__init__` | ~4800 | Must initialize request tracking state |

### HistoryWorker Integration Points (Already Ready)

| File | Methods | Lines | Status |
|------|---------|-------|--------|
| `actions/history_worker.py` | `load_conversation_list` | 106-163 | Returns `request_id` ✅ |
| `actions/history_worker.py` | `load_conversation_detail` | 165-243 | Returns `request_id` ✅ |
| `actions/history_worker.py` | `search_messages` | 245-345 | Returns `request_id` ✅ |

### HistoryPanel State Methods (Already Exist)

| Method | File | Lines | Purpose |
|--------|------|-------|---------|
| `set_list_loading(bool)` | `history_panel.py` | 528-532 | List loading indicator |
| `set_detail_loading(bool)` | `history_panel.py` | 513-518 | Detail loading indicator |
| `set_detail_error(str)` | `history_panel.py` | 520-526 | Detail error display |
| `clear_selection()` | `history_panel.py` | 534-542 | Reset detail view |

---

## 5. Minimal Implementation Plan

### 5.1 Add Request Tracking State to MainWindow

```python
# In MainWindow.__init__ (around line 4810)
self._history_list_request_id = None      # Tracks current list/search request
self._history_detail_request_id = None    # Tracks current detail request
self._history_search_request_id = None    # Tracks current search request (separate from list)
self._current_detail_conv_id = None       # Tracks which conversation detail is for
```

### 5.2 Update Request Initiation Slots

```python
def _on_history_list_page_requested(self, page: int):
    req_id = self._history_worker.load_conversation_list(page=page)
    self._history_list_request_id = req_id
    self._history_panel.set_list_loading(True)

def _on_history_conversation_selected(self, conv_id: str):
    self._current_detail_conv_id = conv_id
    req_id = self._history_worker.load_conversation_detail(conv_id)
    self._history_detail_request_id = req_id
    self._history_panel.set_detail_loading(True)

def _on_history_detail_page_requested(self, page: int):
    if self._current_detail_conv_id:
        req_id = self._history_worker.load_conversation_detail(
            self._current_detail_conv_id, page=page
        )
        self._history_detail_request_id = req_id
        self._history_panel.set_detail_loading(True)

def _on_history_search_requested(self, query: str):
    req_id = self._history_worker.search_messages(query)
    self._history_search_request_id = req_id
    self._history_list_request_id = req_id  # Search reuses list signal
    self._history_panel.set_list_loading(True)
```

### 5.3 Update Response Slots with Stale Rejection

```python
def _show_history_list(self, conversations, page, total_pages, total_count, request_id=None):
    # Reject stale list responses
    if request_id != self._history_list_request_id:
        return
    self._history_panel.set_conversation_list(conversations, page, total_pages, total_count)
    self._history_panel.set_list_loading(False)
    # ... rest unchanged

def _show_history_detail(self, conv_id, title, messages, page, total_pages, total_count, request_id=None):
    # Reject stale detail responses (also verify conv_id matches)
    if request_id != self._history_detail_request_id:
        return
    if conv_id != self._current_detail_conv_id:
        return  # Wrong conversation
    self._history_panel.set_message_detail(conv_id, title, messages, page, total_pages, total_count)
    self._history_panel.set_detail_loading(False)
    self._history_panel.set_detail_error("")

def _show_history_error(self, error, request_id=None):
    # Reject stale errors — check both detail and list contexts
    if request_id == self._history_detail_request_id:
        self._history_panel.set_detail_error(error)
        self._history_panel.set_detail_loading(False)
    if request_id == self._history_list_request_id:
        self._history_panel.set_list_loading(False)
    # Don't clear detail view if error is for list, and vice versa

def _on_history_search(self, query, request_id=None):
    # Search result handling — can share list slot but track separately
    # This slot receives the search query echo; actual results come via _show_history_list
    pass  # No-op for now; results handled by _show_history_list with request_id check
```

### 5.4 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Separate `_history_list_request_id` and `_history_search_request_id` | Search reuses list signal; they must not interfere |
| Detail tracks `_current_detail_conv_id` | Double-check: request_id + conv_id must match |
| Error slot checks both request IDs | Errors must not clear the wrong view |
| Loading indicators set before worker call | Prevents flash; cleared only on matching response |
| No HistoryWorker changes needed | All APIs return request_id; signals carry it |

---

## 6. Test Plan

### 6.1 Deterministic Stale Response Tests (New Tests)

| Test | Scenario | Verification |
|------|----------|--------------|
| `test_stale_detail_rejected` | Two detail requests; second response arrives first | First response ignored; UI shows second conversation |
| `test_stale_search_rejected` | Two search requests; first response arrives last | First response ignored; UI shows second query results |
| `test_stale_list_rejected` | Page 1 then page 2; page 1 response arrives last | Page 1 ignored; UI shows page 2 |
| `test_detail_and_search_independent` | Detail request + search request concurrent | Stale detail doesn't affect search results; stale search doesn't affect detail |
| `test_old_error_not_overwrite_success` | Detail request A fails after B succeeds | B's results preserved; A's error ignored |
| `test_old_empty_not_overwrite_results` | Empty result from old request after new success | New results preserved |
| `test_loading_indicators_correct` | Stale response rejected | Loading cleared only for accepted response |
| `test_cross_operation_isolation` | List + detail + search all active | Each tracks own request ID independently |

### 6.2 Implementation Approach for Tests

- Use `MockPlayer` capturing calls with timestamps
- Simulate out-of-order completion using `threading.Event` barriers
- Verify UI state after all responses processed
- No arbitrary `time.sleep()` — use synchronization primitives

### 6.3 Regression Tests (Must Continue Passing)

| Test Suite | Tests | Purpose |
|------------|-------|---------|
| `test_history_worker.py` | 37 | Worker API unchanged |
| `test_history_panel.py` | 23 | Panel UI methods unchanged |
| `test_conversation_store.py` | 42 | Store unchanged |
| `test_conversation_integration.py` | 6 | Session lifecycle unchanged |

---

## 7. Risks and Compatibility Concerns

| Risk | Severity | Mitigation |
|------|----------|------------|
| Search and list share signal | MEDIUM | Track both with same ID during search; list pagination uses separate ID |
| Error handling conflates list/detail | MEDIUM | Error slot checks both request IDs; only clears loading for matching operation |
| Rapid user clicks create many threads | LOW | HistoryWorker already has shutdown protection; UI can disable buttons during loading |
| Existing callers without request_id | NONE | All slots accept `request_id=None` default; backward compatible |
| HistoryPanel API changes | NONE | Panel methods unchanged; only MainWindow slots modified |
| Signal signature mismatch | NONE | Signals already updated in Task 2; slots accept extra param |

---

## 8. Confirmation: No Files Modified

This audit was performed in **strict read-only mode**. The following files were inspected but not modified:

- `actions/history_worker.py`
- `memory/conversation_store.py`
- `ui.py`
- `history_panel.py`
- `tests/unit/test_history_worker.py`
- `tests/unit/test_history_panel.py`
- `MARK_LVII_B_P1_PHASE1B_TASK2_CORRECTION_REPORT.md`
- `MARK_LVII_B_P1_PHASE1B_TASK2_INDEPENDENT_ACCEPTANCE_AUDIT.md`

---

## 9. Summary

**Task 3 is READY for implementation.**

The codebase provides:
- ✅ Request IDs generated and returned by all HistoryWorker operations
- ✅ Request IDs propagated through player methods, signals, and MainWindow slots
- ✅ Separate signals for list (`_history_list_sig`) and detail (`_history_detail_sig`)
- ✅ Loading/error/empty state methods on HistoryPanel
- ✅ All slots accept optional `request_id` parameter (backward compatible)

**Implementation requires only MainWindow changes:**
1. Add 4 tracking fields to `MainWindow.__init__`
2. Update 4 request-initiation slots to store request IDs and set loading
3. Update 3 response slots (`_show_history_list`, `_show_history_detail`, `_show_history_error`) to reject stale responses
4. No HistoryWorker or HistoryPanel changes needed

**Report Path:** `D:\M MONSTER PROJECT\Roitz-main\MARK_LVII_B_P1_PHASE1B_TASK3_READINESS_AUDIT.md`