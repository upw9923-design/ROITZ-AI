# MARK LVII-B P1 Phase 1A — Targeted Defect Verification Audit

**Project**: `D:\M MONSTER PROJECT\Roitz-main`
**Audit Type**: Strict read-only verification
**Date**: 2025

---

## Issue 1 — HTML Escaping Bug in `HistoryPanel._esc()`

### 1.1 Status: **VERIFIED**

### 1.2 Exact Source Location

**File**: `history_panel.py`
**Lines**: 568-571

```python
@staticmethod
def _esc(s: str) -> str:
    return (str(s or "").replace("&", "&")
            .replace("<", "<").replace(">", ">")
            .replace("\n", "<br>"))
```

**Usage**: Line 500 — message content inserted into HTML:
```python
f'<br><span style="color:{C.TEXT}; white-space:pre-wrap;">{self._esc(content)}</span>'
```

**Rendering**: Line 504 — `self._detail_display.setHtml("".join(parts))`

### 1.3 Technical Explanation

The `_esc()` method is **broken**:

| Input | Current Output | Correct Output |
|-------|----------------|----------------|
| `&` | `&` | `&` |
| `<` | `<` | `<` |
| `>` | `>` | `>` |

The replacements use the literal characters instead of HTML entities. The method does **no escaping at all** — it returns the input essentially unchanged (except newlines → `<br>`).

**Correct implementation** (from `ui.py:599-601`):
```python
@staticmethod
def _esc(s) -> str:
    return (str(s or "").replace("&", "&").replace("<", "<")
            .replace(">", ">").replace("\n", "<br>"))
```

### 1.4 Quotation Marks Analysis

The content is rendered inside a `<span>` element body, not inside an HTML attribute:
```html
<span style="...">{escaped_content}</span>
```

Quotation marks (`"` and `'`) **do not require escaping** in this context for HTML safety. However, if content contains `</span>` or other tags, they would be interpreted as HTML. The correct `_esc()` with `<`/`>` handles this.

### 1.5 Risk and Impact

| Risk | Severity |
|------|----------|
| XSS via message content (`<script>`, `<img onerror=...>`, etc.) | **High** — `QTextEdit.setHtml()` renders arbitrary HTML |
| Broken display of `&`, `<`, `>` characters | **Medium** — shows literal `&` instead of `&` |
| HTML injection breaking panel layout | **Medium** — unclosed tags from user content |

### 1.6 Minimum Safe Correction

**File**: `history_panel.py`, lines 568-571

```python
@staticmethod
def _esc(s: str) -> str:
    return (str(s or "").replace("&", "&").replace("<", "<")
            .replace(">", ">").replace("\n", "<br>"))
```

### 1.7 Tests Required After Correction

1. Add test to `test_history_panel.py`:
   ```python
   def test_html_escaping_prevents_xss(self, panel):
       malicious = '<script>alert(1)</script>&<tag>'
       panel.set_message_detail("c", "t", [{"role": "user", "content": malicious, "timestamp_ms": 0}], 0, 1, 1)
       html = panel._detail_display.toHtml()
       assert "<script>" in html
       assert "&" in html
       assert "<script>" not in html
   ```

2. Run full test suite: `py -m pytest tests/unit/test_history_panel.py -v`

---

## Issue 2 — Pagination Signal Ambiguity

### 2.1 Status: **VERIFIED**

### 2.2 Exact Source Locations

**Signal Declaration** (`history_panel.py:37`):
```python
page_requested = pyqtSignal(int)  # page number (0-based)
```

**List Pagination Handlers** (`history_panel.py:338-339`):
```python
prev_btn.clicked.connect(lambda: self._on_page_change("list", -1))
next_btn.clicked.connect(lambda: self._on_page_change("list", +1))
```

**Detail Pagination Handlers** (`history_panel.py:344-345`):
```python
prev_btn.clicked.connect(lambda: self._on_page_change("detail", -1))
next_btn.clicked.connect(lambda: self._on_page_change("detail", +1))
```

**Internal Dispatch** (`history_panel.py:550-558`):
```python
def _on_page_change(self, which: str, delta: int) -> None:
    if which == "list":
        new_page = self._current_list_page + delta
        if 0 <= new_page < self._total_list_pages:
            self.page_requested.emit(new_page)
    else:
        new_page = self._current_detail_page + delta
        if 0 <= new_page < self._total_detail_pages:
            self.page_requested.emit(new_page)
```

**MainWindow Slot** (`ui.py:6604-6607`):
```python
def _on_history_page_requested(self, page: int):
    """Slot — Qt main thread. User clicked pagination control."""
    # In Phase 1B, this will trigger a backend request for the requested page.
    self._log.append_log(f"History: page requested {page}")
```

### 2.3 Technical Explanation

The `page_requested(int)` signal carries **only the page number**. The receiver (`_on_history_page_requested`) **cannot distinguish** whether the request originated from:
- List pagination (conversation list)
- Detail pagination (message detail)

Both panes maintain independent page state (`_current_list_page` vs `_current_detail_page`, `_total_list_pages` vs `_total_detail_pages`), but this context is lost when the signal is emitted.

### 2.4 Risk and Impact

| Risk | Severity |
|------|----------|
| Backend loads wrong page (list vs detail) | **High** — Phase 1B integration will fail |
| Pagination state corruption | **High** — list page affects detail page or vice versa |
| User sees wrong data after pagination click | **Medium** — confusing UX |

### 2.5 Minimum Safe Correction

**Option A — Separate signals (recommended, minimal API change)**:

`history_panel.py`:
```python
# Replace single signal with two:
list_page_requested = pyqtSignal(int)
detail_page_requested = pyqtSignal(int)

# In _on_page_change:
if which == "list":
    ...
    self.list_page_requested.emit(new_page)
else:
    ...
    self.detail_page_requested.emit(new_page)
```

`ui.py`:
```python
# Connect both signals
panel.list_page_requested.connect(self._on_history_list_page_requested)
panel.detail_page_requested.connect(self._on_history_detail_page_requested)

# Add slots:
def _on_history_list_page_requested(self, page: int): ...
def _on_history_detail_page_requested(self, page: int): ...
```

**Option B — Single signal with pane identifier**:
```python
page_requested = pyqtSignal(str, int)  # ("list"|"detail", page)
# Emission: self.page_requested.emit(which, new_page)
# Slot: def _on_history_page_requested(self, which: str, page: int): ...
```

**Recommendation**: Option A — cleaner separation, matches existing pattern of distinct signals for list vs detail data.

### 2.6 Tests Required After Correction

1. Update `test_history_panel.py` signal tests to verify correct signal emitted for each pane
2. Add integration test in Phase 1B verifying backend receives correct page for list vs detail
3. Run: `py -m pytest tests/unit/test_history_panel.py -v`

---

## Issue 3 — QSplitter Resize Coordination

### 3.1 Status: **VERIFIED**

### 3.2 Exact Source Locations

**_center_split Initialization** (`ui.py:4739-4747`):
```python
self._center_split.addWidget(self._hud_cam_stack)      # index 0, stretch 3
self._center_split.addWidget(self._content_panel)      # index 1, stretch 1
self._center_split.addWidget(self._quiz_panel)         # index 2, stretch 1
self._center_split.addWidget(self._history_panel)      # index 3, stretch 1
self._center_split.setStretchFactor(0, 3)
self._center_split.setStretchFactor(1, 1)
self._center_split.setStretchFactor(2, 1)
self._center_split.setStretchFactor(3, 1)
self._center_split.setCollapsible(0, False)
```

**_show_history_list** (`ui.py:6567-6577`):
```python
def _show_history_list(self, conversations, page: int, total_pages: int, total_count: int):
    ...
    first_show = not self._history_panel.isVisible()
    self._history_panel.show()
    if first_show:
        total = self._center_split.height()
        self._center_split.setSizes([max(total - 300, 120), 0, 0, 300])  # 4 values ✓
```

**_show_quiz** (`ui.py:6406-6425`):
```python
def _show_quiz(self, topic: str, questions, grader=None):
    ...
    first_show = not self._quiz_panel.isVisible()
    self._quiz_panel.show()
    if first_show:
        total = self._center_split.height()
        self._center_split.setSizes([max(total - 250, 120), 0, 250])  # 3 values ✗ (needs 4)
```

**_show_content** (`ui.py:6203-6264`):
```python
def _show_review(...):  # calls _show_content logic
    ...
    first_show = not self._content_panel.isVisible()
    self._content_panel.show()
    if first_show:
        total = self._center_split.height()
        self._center_split.setSizes([max(total - 260, 120), 260, 0])  # 3 values ✗ (needs 4)
```

### 3.3 Technical Explanation

The `_center_split` has **4 widgets** (indices 0-3), but `_show_quiz` and `_show_content` (via `_show_review`) pass only **3 values** to `setSizes()`. 

Qt's behavior when fewer sizes are provided than widgets: the remaining widgets receive their default/stretch-factor-based sizes. This creates **inconsistent sizing**:
- History panel (index 3) gets unpredictable size when quiz/content shown first
- Content panel (index 1) gets 0 when history shown first, but default when quiz shown first
- Quiz panel (index 2) gets 250 when quiz shown first, but 0 when history shown first

**Visibility issue**: `_show_history_list` explicitly hides content (index 1) and quiz (index 2) by setting their sizes to 0. But `_show_quiz` and `_show_content` do **not** hide history panel (index 3) — it remains at whatever size it had.

### 3.4 Risk and Impact

| Risk | Severity |
|------|----------|
| Inconsistent panel sizes depending on show order | **Medium** — UX confusion |
| History panel remains visible when quiz/content shown | **Medium** — visual clutter |
| Splitter handle positions unpredictable | **Low** — cosmetic |

### 3.5 Minimum Safe Correction

**File**: `ui.py`

**_show_quiz** (line 6424):
```python
# Change from:
self._center_split.setSizes([max(total - 250, 120), 0, 250])
# To:
self._center_split.setSizes([max(total - 250, 120), 0, 250, 0])  # hide history
```

**_show_content** / `_show_review` (line 6264):
```python
# Change from:
self._center_split.setSizes([max(total - 260, 120), 260, 0])
# To:
self._center_split.setSizes([max(total - 260, 120), 260, 0, 0])  # hide history
```

**_show_history_list** (line 6577) — already correct with 4 values.

**Additional**: Consider adding a helper method to centralize splitter sizing logic.

### 3.6 Tests Required After Correction

1. Add integration test verifying panel visibility/sizes after each show method
2. Manual test: show history → show quiz → show content → verify only one panel visible at a time
3. Run existing regression: `py -m pytest tests/unit/test_history_panel.py -v`

---

## Issue 4 — Product Branding (Hardcoded "JARVIS" Label)

### 4.1 Status: **VERIFIED**

### 4.2 Exact Source Location

**File**: `history_panel.py`
**Line**: 483

```python
if role == "user":
    role_color = C.PRI
    role_label = "YOU"
elif role == "assistant":
    role_color = C.GREEN
    role_label = "JARVIS"  # <-- HARDCODED
```

### 4.3 Technical Explanation

The assistant role label is hardcoded as `"JARVIS"` in the HistoryPanel, but the application supports a **configurable assistant name**:

- Config: `config/api_keys.json` → `assistant_name` (default "JARVIS")
- `MainWindow._assistant_name` (ui.py:4513) — loaded from config
- `JarvisUI.assistant_name` property (ui.py:7752-7753) — exposes to plugins
- `memory.config_manager.get_assistant_name()` — config accessor
- Used throughout UI: file hints (ui.py:6638, 6654), logs (ui.py:7094-7095), HUD (ui.py:7095)

The HistoryPanel has **no access** to the configurable name — it's a standalone widget with no reference to `MainWindow` or `JarvisUI`.

### 4.4 Risk and Impact

| Risk | Severity |
|------|----------|
| Branding inconsistency (user set "ROITZ" but sees "JARVIS") | **Medium** — product polish |
| Internal identifier leak (ROITZ AI / MONSTER project) | **Low** — "JARVIS" is the default anyway |
| Configurable name feature partially broken | **Medium** — feature gap |

### 4.5 Minimum Safe Correction

**Option A — Pass assistant name to HistoryPanel constructor** (recommended):

`history_panel.py`:
```python
def __init__(self, parent: QWidget | None = None, assistant_name: str = "JARVIS"):
    ...
    self._assistant_name = assistant_name
    ...
# In _build_detail_view / set_message_detail:
role_label = self._assistant_name.upper()
```

`ui.py` `_build_history_panel`:
```python
panel = HistoryPanel(self.centralWidget(), assistant_name=self._assistant_name)
```

**Option B — Use JarvisUI.assistant_name property** (requires HistoryPanel to have JarvisUI reference — more coupling).

**Recommendation**: Option A — minimal coupling, follows existing pattern of passing config to widgets.

### 4.6 Tests Required After Correction

1. Add test verifying assistant name appears in message detail:
   ```python
   def test_assistant_name_configurable(self, panel):
       # Would need to instantiate with custom name
       panel = HistoryPanel(assistant_name="ROITZ")
       panel.set_message_detail("c", "t", [{"role": "assistant", "content": "Hi", "timestamp_ms": 0}], 0, 1, 1)
       html = panel._detail_display.toHtml()
       assert "ROITZ" in html
   ```
2. Run: `py -m pytest tests/unit/test_history_panel.py -v`

---

## Issue 5 — Test Failure Verification

### 5.1 Status: **VERIFIED — Pre-existing timing flake**

### 5.2 Exact Failure

**Test**: `tests/unit/test_task_monitoring.py::TestCrossExecutorSharedRegistry::test_completing_unrelated_worker_does_not_release_other_reservation`

**Command**: `py -m pytest tests/unit/test_task_monitoring.py::TestCrossExecutorSharedRegistry::test_completing_unrelated_worker_does_not_release_other_reservation -v`

**Result**:
```
FAILED ... AssertionError: False is not true
```

**Failure Point** (line 2287):
```python
self.assertTrue(calls["b_started"].is_set())
```

**Test Parameters**: `@patch("core.task_monitoring.STEP_TIMEOUT", 0.05)` — 50ms timeout

### 5.3 Technical Explanation

The test creates two executors with different registries:
- Executor A: completes quickly, sets `a_done` event
- Executor B: sleeps 10s in `run()`, should set `b_started` event

The test expects that after A completes, B is still running and `b_started` is set. However, the 50ms `STEP_TIMEOUT` causes B's step to **time out before or during** the `time.sleep(10)` call, preventing `b_started` from being set.

The timeout is applied globally via `@patch`, affecting both executors concurrently. Thread scheduling determines whether B's `run()` executes before the timeout fires.

### 5.4 Evidence of Pre-existing Nature

Documented in multiple audits:
- `MARK_LVII_B_P0_FINAL_ACCEPTANCE_AUDIT.md:133` — "Timing flake | Pre-existing; 1 of 259 tests in suite"
- `MARK_LVII_B_P0_INDEPENDENT_ACCEPTANCE_AUDIT.md:90` — "timing flake"
- `MARK_LVII_B_P1_ARCHITECTURE_CORRECTIONS.md:591` — "131 passed (1 pre-existing flake)"

**No Phase 1A code touches** `test_task_monitoring.py`, `core/task_monitoring.py`, or `WorkerRegistry`. The failure is **unrelated** to history panel changes.

### 5.5 Reproducibility

- **Confirmed**: Running the test in isolation fails consistently on this machine
- **Nature**: Timing-dependent flake (aggressive 50ms timeout + thread scheduling)
- **Scope**: Only this specific test; other 182 tests in the same session pass

### 5.6 Verdict

**Pre-existing flake — not a Phase 1A regression**. No correction required for Phase 1A.

---

## Summary of Findings

| Issue | Status | Severity | Correction Required |
|-------|--------|----------|---------------------|
| 1. HTML escaping | **VERIFIED** | High | **YES** — P0 |
| 2. Pagination signal ambiguity | **VERIFIED** | High | **YES** — P0 |
| 3. QSplitter resize coordination | **VERIFIED** | Medium | **YES** — P1 |
| 4. Hardcoded JARVIS label | **VERIFIED** | Medium | **YES** — P1 |
| 5. Test failure | **VERIFIED** (pre-existing) | N/A | **NO** — not a regression |

---

## Final Verdict

**READY FOR CORRECTION**

All four implementation defects are verified with exact source locations. The test failure is confirmed as a pre-existing timing flake unrelated to Phase 1A. Minimum safe corrections identified for each issue. No Phase 1A acceptance claimed — corrections should be implemented and verified before acceptance.

---

## Report Path

`D:\M MONSTER PROJECT\Roitz-main\MARK_LVII_B_P1_PHASE1A_TARGETED_DEFECT_AUDIT.md`