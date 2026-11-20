# MARK LVII-B P1 Phase 1A — QSplitter Size Mismatch Fix Report

**Date:** 2026-11-15  
**Project:** `D:\M MONSTER PROJECT\Roitz-main`  
**Fix Type:** Targeted minimal correction  
**Related Verification:** `MARK_LVII_B_P1_PHASE1A_FINAL_VERIFICATION.md`

---

## Summary

Fixed the single remaining `_center_split.setSizes()` call that passed only 2 values for a 4-widget splitter in `_show_code_job()` at `ui.py:6179`.

---

## Modified File and Method

| Item | Detail |
|------|--------|
| **File** | `ui.py` |
| **Method** | `_show_code_job()` |
| **Line** | 6179 |
| **Change** | `setSizes()` call updated from 2 values to 4 values |

---

## Widget Order (Confirmed from `ui.py:4729-4746`)

The `_center_split` (vertical `QSplitter`) contains exactly **4 widgets** in this order:

| Index | Widget | Stretch Factor | Collapsible | Purpose |
|-------|--------|----------------|-------------|---------|
| 0 | `_hud_cam_stack` | 3 | **False** | HUD + camera stack (always visible) |
| 1 | `_content_panel` | 1 | True | Content panel (code job, review, content) |
| 2 | `_quiz_panel` | 1 | True | Quiz panel |
| 3 | `_history_panel` | 1 | True | History panel (Mark LVII-B P1 Phase 1A) |

---

## Before / After Code

### Before (Broken — 2 values)
```python
# ui.py:6179
self._center_split.setSizes([max(total - 260, 120), 260])
```

### After (Fixed — 4 values)
```python
# ui.py:6179
self._center_split.setSizes([max(total - 260, 120), 260, 0, 0])
```

### Allocation Logic
- **Index 0** (`_hud_cam_stack`): Remaining space (`max(total - 260, 120)`) — minimum 120px
- **Index 1** (`_content_panel`): 260px — the panel being shown
- **Index 2** (`_quiz_panel`): 0 — hidden
- **Index 3** (`_history_panel`): 0 — hidden

This matches the pattern used in `_show_content()` (`ui.py:6096`) and `_show_review()` (`ui.py:6264`).

---

## Complete `setSizes()` Call Inventory (Post-Fix)

| Line | Method | Call | Values | Status |
|------|--------|------|--------|--------|
| 6096 | `_show_content` | `setSizes([max(total - 220, 120), 220, 0, 0])` | 4 | ✅ |
| **6179** | **`_show_code_job`** | **`setSizes([max(total - 260, 120), 260, 0, 0])`** | **4** | **✅ FIXED** |
| 6264 | `_show_review` | `setSizes([max(total - 260, 120), 260, 0, 0])` | 4 | ✅ |
| 6425 | `_show_quiz` | `setSizes([max(total - 250, 120), 0, 250, 0])` | 4 | ✅ |
| 6578 | (unnamed) | `setSizes([max(total - 300, 120), 0, 0, 300])` | 4 | ✅ |

**All 5 calls now supply exactly 4 values matching the 4-widget splitter.**

---

## Test Results

### 1. Python Compilation
```bash
py -m py_compile ui.py
```
**Result:** `Compilation OK` — no syntax errors.

### 2. HistoryPanel Unit Tests (23 tests)
```bash
py -m pytest tests/unit/test_history_panel.py -v
```
**Result:** **23 passed** in 10.94s — exit code 0.

### 3. Conversation Store + Integration Tests (48 tests)
```bash
py -m pytest tests/unit/test_conversation_store.py tests/unit/test_conversation_integration.py -v
```
**Result:** **48 passed** in 3.58s — exit code 0.

### 4. No Regressions in Related Tests
- Voice interruption tests: 139 tests, 1 pre-existing unrelated failure (permission grant test)
- Inline permissions tests: 83 passed
- Task monitoring tests: 100 passed

---

## Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `ui.py` | 6179 only | Fixed `_show_code_job()` `setSizes()` call from 2 to 4 values |

**No other files modified.**  
**No other methods, UI layout, HistoryPanel, branding, signals, or architecture touched.**

---

## Verification Checklist

- [x] Inspected `_center_split` widget construction — confirmed 4 widgets
- [x] Verified widget order and stretch factors
- [x] Confirmed intended visibility: content panel shown, quiz & history hidden
- [x] Applied minimal fix matching existing pattern (`_show_content`, `_show_review`)
- [x] Python compilation successful
- [x] All 23 HistoryPanel tests pass
- [x] All 48 conversation store/integration tests pass
- [x] All 5 `_center_split.setSizes()` calls now supply exactly 4 values
- [x] No unrelated files modified

---

*Fix applied per targeted correction instructions. Final acceptance pending independent read-only verification.*