# MARK LVII-B P1 Phase 1B Task 3 — MainWindow Stale Response Protection Implementation Report

**Date:** 2026-11-15  
**Project:** `D:\M MONSTER PROJECT\Roitz-main`  
**Task:** Implement stale response protection for conversation history UI

---

## Executive Summary

**TASK 3 COMPLETE** — MainWindow now tracks request IDs per operation type and rejects stale responses that complete out of order.

| Component | Changes | Status |
|-----------|---------|--------|
| `ui.py` (MainWindow) | Request tracking state, 4 initiation slots updated, 3 response slots with stale rejection | ✅ |
| `main.py` (JarvisLive) | HistoryWorker initialization and shutdown wiring | ✅ |
| `tests/unit/test_history_worker.py` | 7 new deterministic stale response tests added | ✅ |
| **Total Tests** | 44 HistoryWorker + 71 regression = **115 passing** | ✅ |

---

## 1. Implementation Details

### 1.1 Request Tracking State Added to MainWindow

```python
# In MainWindow.__init__ (ui.py ~line 4806)
self._history_list_request_id = None      # Tracks current list/search request
self._history_detail_request_id = None    # Tracks current detail request
self._current_detail_conv_id = None       # Tracks which conversation detail is for
```

### 1.2 Request Initiation Slots Updated (4 slots)

| Slot | Action | Tracks |
|------|--------|--------|
| `_on_history_list_page_requested(page)` | `worker.load_conversation_list(page)` | `_history_list_request_id` |
| `_on_history_conversation_selected(conv_id)` | `worker.load_conversation_detail(conv_id)` | `_history_detail_request_id`, `_current_detail_conv_id` |
| `_on_history_detail_page_requested(page)` | `worker.load_conversation_detail(current_conv, page)` | `_history_detail_request_id` |
| `_on_history_search_requested(query)` | `worker.search_messages(query)` | `_history_search_request_id`, `_history_list_request_id` |

All set loading indicators (`set_list_loading(True)` / `set_detail_loading(True)`) before worker call.

### 1.3 Response Slots with Stale Rejection (3 slots)

#### `_show_history_list` (line 6574)
```python
def _show_history_list(self, conversations, page, total_pages, total_count, request_id=None):
    if request_id != self._history_list_request_id:
        self._log.append_log(f"History: stale list response ignored (req={request_id}, current={self._history_list_request_id})")
        return
    # ... process normally
```

#### `_show_history_detail` (line 6590)
```python
def _show_history_detail(self, conv_id, title, messages, page, total_pages, total_count, request_id=None):
    if request_id != self._history_detail_request_id:
        return  # Stale
    if conv_id != self._current_detail_conv_id:
        return  # Wrong conversation
    # ... process normally
```

#### `_show_history_error` (line 6610)
```python
def _show_history_error(self, error, request_id=None):
    handled = False
    if request_id == self._history_detail_request_id:
        self._history_panel.set_detail_error(error)
        self._history_panel.set_detail_loading(False)
        handled = True
    if request_id == self._history_list_request_id:
        self._history_panel.set_list_loading(False)
        handled = True
    if not handled:
        self._log.append_log(f"History: stale error ignored (req={request_id})")
```

### 1.4 HistoryWorker Wiring in JarvisLive (main.py)

```python
# In run() method, before reconnect loop (line ~2925)
self._history_worker = HistoryWorker(player=self.ui)
self.ui.set_history_worker(self._history_worker)

# In request_shutdown() (line ~1233)
if hasattr(self, "_history_worker") and self._history_worker is not None:
    self._history_worker.shutdown(wait=True, timeout=2.0)
```

### 1.5 New JarvisUI Method

```python
def set_history_worker(self, worker: "HistoryWorker") -> None:
    """Set the HistoryWorker instance for history operations."""
    self._win._history_worker = worker
```

---

## 2. Stale Response Scenarios Protected

| Scenario | Before | After |
|----------|--------|-------|
| **Detail: A then B, B arrives first** | A overwrites B | A rejected, B shown |
| **Search: "alpha" then "beta", "alpha" arrives last** | "alpha" overwrites "beta" | "alpha" rejected |
| **List: Page 1 then Page 2, Page 1 arrives last** | Page 1 overwrites Page 2 | Page 1 rejected |
| **Error after success (detail)** | Error clears success data | Error rejected if stale |
| **Cross-operation (list + detail + search)** | Shared signal could interfere | Each tracks independently |

---

## 3. Deterministic Tests Added

Added 7 new tests in `TestHistoryWorkerStaleResponseRejection` class:

| Test | Verification |
|------|--------------|
| `test_stale_detail_rejected` | Two detail requests; second response arrives first → first ignored |
| `test_stale_search_rejected` | Two search requests; first response arrives last → first ignored |
| `test_stale_list_rejected` | Page 1 then page 2; page 1 response arrives last → page 1 ignored |
| `test_detail_and_search_independent` | Detail + search concurrent → each tracks independently |
| `test_old_error_not_overwrite_success` | Detail A fails after B succeeds → B's results preserved |
| `test_loading_indicators_correct` | Stale response rejected → loading cleared only for accepted |
| `test_cross_operation_isolation` | List + detail + search all active → independent tracking |

**Implementation approach:** Uses `threading.Event` barriers (not `time.sleep`) for deterministic out-of-order completion simulation. Verifies UI state after all responses processed.

---

## 4. Test Results

### New Tests (44 total in test_history_worker.py)
```
TestHistoryWorkerStaleResponseRejection::test_cross_operation_isolation PASSED
TestHistoryWorkerStaleResponseRejection::test_detail_and_search_independent PASSED
TestHistoryWorkerStaleResponseRejection::test_loading_indicators_correct PASSED
TestHistoryWorkerStaleResponseRejection::test_old_error_not_overwrite_success PASSED
TestHistoryWorkerStaleResponseRejection::test_stale_detail_rejected PASSED
TestHistoryWorkerStaleResponseRejection::test_stale_list_rejected PASSED
TestHistoryWorkerStaleResponseRejection::test_stale_search_rejected PASSED
```
**All 44 tests pass in ~19s**

### Regression Tests (71 tests)
- `test_conversation_store.py`: 42 passed
- `test_conversation_integration.py`: 6 passed
- `test_history_panel.py`: 23 passed

**All 71 regression tests pass in ~13s**

### Python Compilation
```bash
py -m py_compile actions/history_worker.py memory/conversation_store.py ui.py main.py
# Result: OK — no syntax errors
```

---

## 5. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Separate `_history_list_request_id` and `_history_search_request_id` | Search reuses `_history_list_sig` signal; they must not interfere |
| Detail tracks `_current_detail_conv_id` | Double-check: request_id + conv_id must both match |
| Error slot checks both request IDs | Errors must not clear the wrong view's loading state |
| Loading indicators set before worker call | Prevents flash; cleared only on matching response |
| No HistoryWorker changes needed | All APIs already return request_id; signals already carry it |
| Backward compatible slots | All accept `request_id=None` default; existing callers unaffected |

---

## 6. Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `ui.py` | ~4806 (init), 6574-6625 (slots) | Request tracking, stale rejection logic |
| `main.py` | ~2925 (run), ~1233 (shutdown) | HistoryWorker initialization and cleanup |
| `tests/unit/test_history_worker.py` | +7 new tests (lines ~905-1020) | Deterministic stale response tests |

---

## 7. Verification Checklist

- ✅ Request IDs generated and returned by all HistoryWorker operations
- ✅ Request IDs propagated through player methods, signals, and MainWindow slots
- ✅ MainWindow tracks current request ID per operation type (list, detail, search)
- ✅ Stale responses rejected in `_show_history_list`, `_show_history_detail`, `_show_history_error`
- ✅ Detail view double-checks conversation ID matches
- ✅ Loading indicators set on request, cleared only on matching response
- ✅ Errors only affect matching operation (detail error doesn't clear list, vice versa)
- ✅ Cross-operation isolation: list, detail, search track independently
- ✅ All 44 HistoryWorker tests pass (37 original + 7 new)
- ✅ All 71 regression tests pass
- ✅ Python compilation OK

---

## 8. Next Steps

Task 3 is complete. The history UI now correctly handles concurrent requests and out-of-order responses. Ready for:

- **Task 4:** Search conversation grouping (dedicated `search_conversations` API)
- **Task 5:** UI polish (keyboard navigation, accessibility)
- **Task 6:** Integration with session management

---

**Report Path:** `D:\M MONSTER PROJECT\Roitz-main\MARK_LVII_B_P1_PHASE1B_TASK3_IMPLEMENTATION_REPORT.md`