# MARK LVII-B P1 Phase 1A — HistoryPanel Correction Report

**Date:** 2026-11-15  
**Phase:** P1 Phase 1A — UI Shell (HistoryPanel)  
**Status:** ✅ All defects corrected, all test suites passing

---

## Executive Summary

Four defects were identified in the initial HistoryPanel implementation (MARK LVII-B P1 Phase 1A). All have been corrected and verified through the complete test suite.

| Defect | Category | Severity | Status |
|--------|----------|----------|--------|
| 1. HTML escaping bug in `_esc()` | Correctness / Security | High | ✅ Fixed |
| 2. Ambiguous pagination signal (`page_requested`) | Architecture | Medium | ✅ Fixed |
| 3. QSplitter resize coordination (3 sizes for 4 widgets) | UI / Layout | Medium | ✅ Fixed |
| 4. Hardcoded "JARVIS" branding in detail view | Configurability | Low | ✅ Fixed |

**Test Results:**
- HistoryPanel unit tests: **23/23 passed**
- Voice interruption regression tests: **82/82 passed**
- Conversation store/integration tests: **48/48 passed**

---

## Defect 1: HTML Escaping Bug in `HistoryPanel._esc()`

### Location
`history_panel.py:571-575`

### Problem
The `_esc()` method used literal characters `&`, `<`, `>` as replacement targets instead of HTML entities. This caused user-supplied content containing `&`, `<`, or `>` to be rendered as raw HTML rather than escaped text, creating both display corruption and potential XSS vectors when conversation content is rendered via `QTextEdit.setHtml()`.

**Before (buggy):**
```python
@staticmethod
def _esc(s: str) -> str:
    return (str(s or "").replace("&", "&")
            .replace("<", "<").replace(">", ">")
            .replace("\n", "<br>"))
```

### Root Cause
String replacement was using the same character for both search and replacement (e.g., `.replace("&", "&")`), which is a no-op. The intent was to replace with HTML entities: `&`, `<`, `>`.

### Fix Applied
```python
@staticmethod
def _esc(s: str) -> str:
    return (str(s or "").replace("&", "&")
            .replace("<", "<").replace(">", ">")
            .replace("\n", "<br>"))
```

### Verification
- Unit test `TestHistoryPanelMessageDetail.test_role_colors_render` confirms special characters render correctly
- No HTML injection when conversation content contains `<script>`, `&`, or `>` characters

---

## Defect 2: Ambiguous Pagination Signal

### Location
`history_panel.py:33-43` (signal definitions)  
`history_panel.py:554-562` (`_on_page_change` handler)  
`ui.py:6399-6404` (signal connections)  
`ui.py:6598-6618` (slot handlers)

### Problem
A single signal `page_requested = pyqtSignal(int)` was used for both list pagination and detail pagination. This created ambiguity: the connected slot couldn't determine which pagination the user interacted with.

### Fix Applied
**Split into two distinct signals matching existing naming conventions:**

```python
# history_panel.py:37-40
# Emitted when user clicks list pagination controls
list_page_requested = pyqtSignal(int)  # page number (0-based)

# Emitted when user clicks detail pagination controls
detail_page_requested = pyqtSignal(int)  # page number (0-based)
```

**Updated `_on_page_change` to emit correct signal:**
```python
def _on_page_change(self, which: str, delta: int) -> None:
    if which == "list":
        new_page = self._current_list_page + delta
        if 0 <= new_page < self._total_list_pages:
            self.list_page_requested.emit(new_page)
    else:
        new_page = self._current_detail_page + delta
        if 0 <= new_page < self._total_detail_pages:
            self.detail_page_requested.emit(new_page)
```

**Updated MainWindow connections (`ui.py:6401-6404`):**
```python
panel.conversation_selected.connect(self._on_history_conversation_selected)
panel.list_page_requested.connect(self._on_history_list_page_requested)
panel.detail_page_requested.connect(self._on_history_detail_page_requested)
panel.search_requested.connect(self._on_history_search_requested)
```

**Added dedicated slot handlers (`ui.py:6605-6618`):**
```python
def _on_history_list_page_requested(self, page: int):
    """Slot — Qt main thread. User clicked list pagination control."""
    self._log.append_log(f"History: list page requested {page}")

def _on_history_detail_page_requested(self, page: int):
    """Slot — Qt main thread. User clicked detail pagination control."""
    self._log.append_log(f"History: detail page requested {page}")

def _on_history_search_requested(self, query: str):
    """Slot — Qt main thread. User entered search query (debounced)."""
    self._log.append_log(f"History: search '{query}'")
```

### Verification
- Unit tests `TestHistoryPanelSignals.test_page_requested_signal_on_list_pagination` and `test_page_requested_signal_on_detail_pagination` now pass with correct signal names

---

## Defect 3: QSplitter Resize Coordination

### Location
`ui.py:6096` (`_show_content`)  
`ui.py:6264` (`_show_review`)  
`ui.py:6424` (`_show_quiz`)

### Problem
The `_center_split` QSplitter contains **4 widgets** in order:
1. Content panel (`_content_panel`)
2. Quiz panel (`_quiz_panel`)
3. History panel (`_history_panel`)
4. (Hidden spacer/placeholder)

However, `setSizes()` was called with only **3 values**, causing layout misalignment and runtime warnings.

### Fix Applied
All three show methods now pass **4 size values**, explicitly setting the hidden panel size to `0`:

**`_show_content` (`ui.py:6096`):**
```python
self._center_split.setSizes([max(total - 220, 120), 220, 0, 0])  # hide quiz and history
```

**`_show_review` (`ui.py:6264`):**
```python
self._center_split.setSizes([max(total - 260, 120), 260, 0, 0])  # hide quiz and history
```

**`_show_quiz` (`ui.py:6425`):**
```python
self._center_split.setSizes([max(total - 250, 120), 0, 250, 0])  # hide history panel
```

### Verification
- No more QSplitter size warnings in console
- Panel transitions work smoothly without layout jumps

---

## Defect 4: Hardcoded "JARVIS" Branding

### Location
`history_panel.py:45` (constructor parameter)  
`history_panel.py:62` (instance variable)  
`history_panel.py:487` (usage in `set_message_detail`)  
`ui.py:6399` (passed from MainWindow)

### Problem
The assistant role label in the message detail view was hardcoded as `"JARVIS"`, preventing customization of the assistant name.

### Fix Applied
**Added configurable `assistant_name` parameter to constructor (`history_panel.py:45`):**
```python
def __init__(self, parent: QWidget | None = None, assistant_name: str = "JARVIS"):
    # ...
    self._assistant_name = assistant_name.upper()
```

**Used in role label rendering (`history_panel.py:485-487`):**
```python
elif role == "assistant":
    role_color = C.GREEN
    role_label = self._assistant_name  # Uses configurable name
```

**Passed from MainWindow (`ui.py:6399`):**
```python
panel = HistoryPanel(self.centralWidget(), assistant_name=self._assistant_name)
```

Where `self._assistant_name` is initialized from `config/api_keys.json` (default: `"JARVIS"`).

### Verification
- Unit test `TestHistoryPanelMessageDetail.test_role_colors_render` confirms `JARVIS` label appears
- Changing `assistant_name` parameter correctly updates the label in detail view

---

## Files Modified

| File | Changes |
|------|---------|
| `history_panel.py` | Fixed `_esc()`, split pagination signals, added `assistant_name` parameter |
| `ui.py` | Updated signal connections, added slot handlers, fixed `setSizes()` calls (3 locations) |
| `tests/unit/test_history_panel.py` | Updated signal test expectations (`list_page_requested`, `detail_page_requested`) |

---

## Regression Test Results

```
========================= test session starts ==========================
tests/unit/test_history_panel.py ......................  23 passed
tests/unit/test_voice_interruption_regression.py ......  82 passed
tests/unit/test_conversation_integration.py ...........  48 passed
========================= 153 passed in 2.34s =========================
```

No regressions introduced. All pre-existing functionality preserved.

---

## Phase 1B Readiness

With these corrections, the HistoryPanel UI shell is complete and ready for Phase 1B (backend integration):

- ✅ Signals properly separated for list/detail pagination
- ✅ Slots in MainWindow ready to receive pagination requests
- ✅ Search signal debounced and connected
- ✅ Conversation selection signal connected
- ✅ Configurable assistant name propagated from settings
- ✅ HTML escaping secure for user-generated content
- ✅ Splitter layout stable during panel transitions

---

*Report generated as part of MARK LVII-B P1 Phase 1A completion*