# Phase 5 Batch 5 Part 2 - WorkerRegistry Cross-Tool Resource Coordination Audit Report

**Status:** READ-ONLY audit complete — no implementation performed  
**Date:** 2026-11-14  
**Scope:** 14 files across core, actions, plugins, and tests  
**Objective:** Identify which tools/execution paths lack proper WorkerRegistry coordination

---

## Executive Summary

**Part 1 (Completed):** WorkerRegistry integration for `open_app`, `computer_settings`, and 8 inline tools in `main.py` is **complete and verified**.

**Part 2 (This Audit):** Found **6 major execution paths** lacking WorkerRegistry admission and lifecycle tracking, creating resource coordination gaps that allow concurrent conflicting operations on shared physical resources (display, input, application management, network).

### Critical Findings at a Glance

| Tool/Module | WorkerRegistry Admission | Lifecycle Tracking | Resource Keys Defined | Status |
|-------------|-------------------------|-------------------|----------------------|--------|
| `open_app.py` | ✅ Lines 306-318 | ✅ Lines 384-399 | ✅ `app:{name}` | **COMPLETE** |
| `computer_settings.py` | ✅ Lines 869-882 | ✅ Throughout | ✅ `global:input`, `global:display`, `app:manage` | **COMPLETE** |
| `main.py` inline (8 tools) | ✅ Via `_run_with_worker_registry()` | ✅ Via pattern | ✅ Various | **COMPLETE** |
| `autonomous_agent.py` Executor | ✅ Full integration | ✅ Full integration | ✅ All tools | **COMPLETE** |
| **file_controller.py** (13 actions) | ❌ **NONE** | ❌ **NONE** | ✅ Defined in registry | **MISSING** |
| **computer_control.py** (25+ actions) | ❌ Only `_record_start` | ❌ Only recording | ✅ Defined in registry | **MISSING** |
| **browser_control.py** (session-based) | ❌ **NONE** | ❌ Own session lifecycle | ✅ `browser:{url}` | **MISSING** |
| **send_message.py** | ❌ **NONE** | ❌ **NONE** | ⚠️ Uses `global:input` | **MISSING** |
| **dev_agent.py** | ❌ **NONE** | ❌ **NONE** | ⚠️ Uses `global:input` + subprocess | **MISSING** |
| **telegram_bot.py** | ❌ **NONE** | ❌ Own polling lifecycle | ⚠️ Uses `net:egress` + `messaging:send` | **MISSING** |

---

## 1. Tool Integration Inventory

### 1.1 Fully Integrated (Part 1 Complete)

#### `actions/open_app.py` — Lines 293-405
- **Admission:** Lines 306-318 — `create_worker_record()` + `registry.admit_worker()`
- **Resource key:** `app:{launcher_name}` (extracted via `extract_resource_keys()`)
- **Scope:** `LOCAL_SYSTEM`
- **Lifecycle:** `mark_running()` at line 399, `mark_completed()` in `_wrapped_launch_and_verify()` (line 383), `release_resources()` at lines 365, 384
- **Thread-start failure fix:** Lines 391-398 — wraps `thread.start()` in try/except, calls `mark_failed()` → `mark_terminated()` → `release_resources()` on failure
- **Outcome contract:** Returns `started` immediately, background thread reports `done`/`unverified`/`failed`

#### `actions/computer_settings.py` — Lines 841-1083
- **Admission:** Lines 869-882 — per-action worker record with `operation_name="computer_settings:{action}"`
- **Resource keys:** Mapped in `worker_registry.py:554-576` — 30+ actions now use shared `global:input` (fixed in Part 1), volume/brightness use `global:display` where applicable
- **Scope:** `LOCAL_SYSTEM`
- **Lifecycle:** `mark_completed()` at every return path (lines 914, 934, 939, 953, 956, 966, 974, 979, 986, 992, 1016, 1033, 1076, 1081)
- **Special handling:** Irreversible actions (`restart`, `shutdown`, `toggle_wifi`) use `confirm.request()` with `mark_completed("confirmation requested")` at line 914

#### `main.py` Inline Tools (8 tools) — Lines 1356-1788
- **Pattern:** `_run_with_worker_registry()` reusable helper (lines 1356-1438)
- **Tools covered:** `save_memory`, `recall_memory`, `undo`, `screen_process`, `close_camera`, `system_status`, `manage_monitor`, `shutdown_jarvis`
- **Each tool:** Permission check → `create_worker_record()` → `admit_worker()` → execute handler → `mark_completed()`/`mark_failed()` → `release_resources()`
- **Sync + async support:** `is_async` parameter handles both handler types

#### `core/autonomous_agent.py` Executor — Full Integration
- **Admission:** `_execute_step()` lines 720-760 — creates worker, admits before execution
- **Lifecycle:** `mark_running()` at line 756, `mark_completed()`/`mark_failed()`/`mark_timed_out()`/`mark_unresolved()` throughout
- **Cross-step conflict detection:** `_check_cross_step_conflicts()` at lines 680-710
- **Retry safety:** Waits for previous worker (`join()`) before retry, blocks if still alive (Correction A)
- **Unresolved handling:** Grace period (2s) → `mark_unresolved()` → reservations retained until `mark_terminated()` + `cleanup_terminated()`

---

### 1.2 Missing Integration — Actions

#### `actions/file_controller.py` — 13 Actions, **NO WorkerRegistry Integration**
```python
# Actions (all synchronous, no admission, no lifecycle):
list, create_file, create_folder, delete, move, copy, rename, read, write, find, largest, disk_usage, organize_desktop
```
- **Resource keys DEFINED** in `worker_registry.py:437-458`:
  - `file:{path}` for read/write/delete/move/copy/rename
  - `dir:{path}` for create_folder/list
  - `global:display` for find/largest/disk_usage/organize_desktop (incorrect — should be `local_file`)
- **Scope used:** `LOCAL_FILE` (in `permission_guard.py` OPERATION_SPECS)
- **Execution:** Pure synchronous functions, no threading, no background work
- **Gap:** Can run concurrently with any other tool using `local_file` resources — no admission check, no conflict detection

#### `actions/computer_control.py` — 25+ Actions, **Partial Integration ONLY for Screen Recording**
```python
# WorkerRegistry used ONLY in _record_start() at lines 1366-1392:
action="screen_record" → creates worker, admits, tracks lifecycle

# ALL OTHER ACTIONS execute synchronously WITHOUT admission:
type, click, hotkey, scroll, screenshot, focus_window, close_app, screen_find, screen_click, swipe, drag, ...
```
- **Resource keys DEFINED** in `worker_registry.py:459-553`:
  - `global:display` — screenshot, screen_find, screen_click
  - `global:input` — type, click, hotkey, scroll, swipe, drag, screen_click
  - `app:manage` — focus_window, close_app
  - `app:{name}` — close_app (specific app)
- **Scope used:** `LOCAL_SYSTEM` (in `permission_guard.py` OPERATION_SPECS)
- **Execution:** Synchronous pyautogui/subprocess calls on worker thread
- **Gap:** All input/display/app actions can run concurrently — `type` + `click` + `screenshot` + `close_app` can all execute simultaneously

#### `actions/browser_control.py` — Session-Based Architecture, **NO WorkerRegistry Integration**
```python
# Own session management:
_BrowserSession (Playwright page + context + browser)
_SessionRegistry (session_id -> session mapping)
# Background thread runs Playwright event loop
```
- **Resource keys DEFINED** in `worker_registry.py:577-610`:
  - `browser:{url}` for navigate/screenshot/click/type/wait/evaluate
  - `network:egress` for all network operations
- **Scope used:** `LOCAL_SYSTEM` / `NETWORK_EGRESS` (in `permission_guard.py`)
- **Execution:** Async Playwright on dedicated thread, session persists across calls
- **Gap:** Browser sessions can run concurrently with OS-level display/input tools — `browser_control:screenshot` + `computer_control:screenshot` can both run (different resource keys by design, but no coordination on shared GPU/display hardware)

---

### 1.3 Missing Integration — Plugins & Tools

#### `actions/send_message.py` — **NO WorkerRegistry Integration**
```python
# Lines 347-357: threading.Thread for background sending
threading.Thread(target=_send_and_report, args=(player, platform, receiver, message_text), daemon=True, name="send-message").start()
# Returns outcome.started() immediately
```
- **Resources used:** `global:input` (pyautogui hotkeys, typing), `app:manage` (opens WhatsApp/Telegram/Discord/etc.), `network:egress` (Instagram/Messenger via browser)
- **PermissionGuard:** Used at entry (line 334 checks pyautogui)
- **Gap:** No admission — can run concurrent with `computer_control:type`, `computer_settings:type_text`, `computer_control:click`, `open_app`

#### `actions/dev_agent.py` — **NO WorkerRegistry Integration**
```python
# Line 1566: threading.Thread for background job
threading.Thread(target=work, daemon=True, name="dev_agent-job").start()
# _run_job() at line 1535 manages job lifecycle internally (_job_lock, _JOB dict)
```
- **Resources used:** `global:input` (pyautogui for VSCode launch at line 308), `local_file` (reads/writes project files), `network:egress` (pip install, git), `app:manage` (launches VSCode, runs project)
- **PermissionGuard:** NOT used at entry
- **Gap:** Long-running background jobs (minutes) with no resource coordination — can conflict with file_controller, computer_control, open_app, browser_control

#### `plugins/telegram_bot.py` — **NO WorkerRegistry Integration**
```python
# Lines 427-475: _polling_loop_func() runs on asyncio event loop
_polling_task = asyncio.create_task(_polling_loop_func(player))  # line 557
# Commands execute via handlers that call player.sleep()/wake()/on_shutdown_request()
```
- **Resources used:** `network:egress` (Telegram Bot API HTTPS), `messaging:send` (sends messages), `app:manage` (shutdown command triggers JARVIS shutdown)
- **PermissionGuard:** Used extensively (lines 310, 334, 358, 440, 508, 525, 605, 629, 667, 682, 700, 715, 747)
- **Gap:** Long-running polling task (indefinite) with no WorkerRegistry admission — can run concurrent with any tool using `network:egress` or `app:manage`

---

## 2. Resource Key Mapping

### 2.1 Defined in `worker_registry.py:extract_resource_keys()`

| Tool | Operation | Resource Keys | Scope |
|------|-----------|---------------|-------|
| `file_controller` | read/write/delete/move/copy/rename | `file:{path}` | `LOCAL_FILE` |
| `file_controller` | list/create_folder | `dir:{path}` | `LOCAL_FILE` |
| `file_controller` | find/largest/disk_usage/organize_desktop | `global:display` ⚠️ | `LOCAL_FILE` |
| `computer_control` | screenshot/screen_find/screen_click | `global:display` | `LOCAL_SYSTEM` |
| `computer_control` | type/click/hotkey/scroll/swipe/drag/screen_click | `global:input` | `LOCAL_SYSTEM` |
| `computer_control` | focus_window/close_app | `app:manage`, `app:{name}` | `LOCAL_SYSTEM` |
| `computer_settings` | volume/brightness | `global:display` | `LOCAL_SYSTEM` |
| `computer_settings` | window/browser/editing/input actions | `global:input` (30+ actions, fixed Part 1) | `LOCAL_SYSTEM` |
| `computer_settings` | dark_mode/toggle_wifi/restart/shutdown | `app:manage` | `LOCAL_SYSTEM` |
| `open_app` | launch | `app:{launcher_name}` | `LOCAL_SYSTEM` |
| `browser_control` | navigate/screenshot/click/type/wait/evaluate | `browser:{url}`, `network:egress` | `LOCAL_SYSTEM`/`NETWORK_EGRESS` |
| `send_message` | (not extracted) | `global:input`, `app:manage`, `network:egress` | `LOCAL_SYSTEM` |
| `dev_agent` | (not extracted) | `global:input`, `local_file`, `network:egress`, `app:manage` | MULTI |
| `telegram_bot` | (not extracted) | `network:egress`, `messaging:send`, `app:manage` | `NETWORK_EGRESS`/`REMOTE_SERVICE` |

### 2.2 False Isolation Cases (Resource Keys Defined But Not Enforced)

| Conflict Pair | Shared Physical Resource | Why It Matters |
|---------------|-------------------------|----------------|
| `file_controller:write` + `file_controller:delete` same path | Same file on disk | Data corruption/race |
| `computer_control:type` + `computer_control:click` | Same keyboard/mouse input stream | Keystrokes/clicks interleaved |
| `computer_control:screenshot` + `computer_control:screen_find` | Same display capture | MSS/region capture conflict |
| `computer_settings:type_text` + `computer_control:type` | Same pyautogui input | Typing interleaved |
| `send_message` + `computer_control:type` | Same pyautogui input | Message typing corrupted |
| `open_app:Notepad` + `computer_control:close_app:Notepad` | Same app process | Launch/close race |
| `browser_control:screenshot` + `computer_control:screenshot` | GPU/display hardware | Potential driver contention |

---

## 3. Confirmed Missing Integrations

### Priority 1: High-Impact User-Facing Tools

1. **`file_controller.py`** — 13 actions, core file operations, no admission
   - Every file operation can race with any other file operation
   - No protection for `organize_desktop` (moves many files) vs concurrent `delete`/`move`

2. **`computer_control.py`** — 25+ actions, core OS control, only recording integrated
   - Input actions (`type`, `click`, `hotkey`, `scroll`) can interleave
   - Display actions (`screenshot`, `screen_find`) can conflict
   - App management (`focus_window`, `close_app`) can race with `open_app`

3. **`browser_control.py`** — Session-based, persistent background thread
   - Long-running Playwright session holds browser process
   - No coordination with OS-level tools using display/input

### Priority 2: Background/Long-Running Tools

4. **`send_message.py`** — Background thread, uses pyautogui heavily
   - Types into chat apps — conflicts with any input tool
   - Opens apps — conflicts with `open_app` and `computer_control:close_app`

5. **`dev_agent.py`** — Long-running background jobs (minutes)
   - File I/O, process launching, network access
   - No PermissionGuard at entry — security gap

6. **`plugins/telegram_bot.py`** — Persistent polling (indefinite)
   - Network egress continuous
   - Shutdown command triggers `app:manage` (JARVIS shutdown)

---

## 4. Worker Lifecycle Defects

| Tool | Creates Worker | mark_running | mark_completed | mark_failed | mark_terminated | release_resources |
|------|---------------|--------------|----------------|-------------|-----------------|-------------------|
| `open_app` | ✅ | ✅ | ✅ | ✅ (thread-start fix) | ✅ | ✅ |
| `computer_settings` | ✅ | ❌ (sync) | ✅ | ✅ | ✅ | ✅ |
| `main.py` inline | ✅ | ❌ (sync) | ✅ | ✅ | ✅ | ✅ |
| `autonomous_agent` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `file_controller` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `computer_control` | ⚠️ (recording only) | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| `browser_control` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `send_message` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `dev_agent` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `telegram_bot` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Note:** Synchronous tools don't need `mark_running` (no background thread), but they DO need admission + `mark_completed`/`mark_failed` + `release_resources`.

---

## 5. Permission/Security Concerns

### 5.1 Missing PermissionGuard at Entry
- **`dev_agent.py`** — No PermissionGuard check at `dev_agent()` entry point (line 1590). Only internal calls through `player` methods have implicit checks.
- **`file_controller.py`** — No PermissionGuard at `file_controller()` entry. Relies on caller (autonomous_agent) to check.
- **`computer_control.py`** — No PermissionGuard at `computer_control()` entry for non-recording actions.

### 5.2 PermissionGuard WITHOUT WorkerRegistry
- **`telegram_bot.py`** — Uses PermissionGuard extensively (11+ checks) but NO WorkerRegistry admission. Can run concurrent with tools using same capabilities.
- **`send_message.py`** — Uses PermissionGuard (pyautogui check) but NO WorkerRegistry.

### 5.3 Capability Coverage Gaps
`permission_guard.py` OPERATION_SPECS has 200+ entries but:
- `send_message` actions not mapped to specific resource keys
- `dev_agent` actions not in OPERATION_SPECS
- `telegram_bot` polling not mapped to `net:egress` admission

---

## 6. Missing Regression Tests

### Current Coverage (from `test_task_monitoring.py` and `test_worker_registry_integration.py`)
- ✅ `TestWorkerRegistryIntegration` — 11 tests (open_app, computer_settings, inline tools, thread-start failure, _run_with_worker_registry)
- ✅ `TestComputerSettingsResourceConflicts` — 5 tests (scroll, tab, copy/paste, type/press_key, cross-tool input conflicts)
- ✅ `TestWorkerLifecycleTracking` — 10 tests (state transitions, conflicts, resource keys)
- ✅ `TestExecutorWorkerSafety` — 4 tests (retry waits, non-idempotent timeout, idempotent retry, unresolved logging)
- ✅ `TestUnresolvedWorkerHandling` — 2 tests (cross-step blocking, different scope)
- ✅ `TestCorrectionAReggressions` — 4 tests (retry blocked, cross-step conflict, different scope, cancellation semantics)
- ✅ `TestCrossExecutorSharedRegistry` — 6 tests (shared registry, resource blocking, independent resources, unresolved blocking, cleanup isolation, explicit registry isolation)

### Missing Test Coverage
| Area | Missing Tests |
|------|---------------|
| `file_controller` | Admission, lifecycle, resource key conflicts (file:{path}, dir:{path}) |
| `computer_control` (non-recording) | Admission for type/click/hotkey/scroll/screenshot/focus_window/close_app/screen_find/screen_click |
| `browser_control` | Admission, session lifecycle vs WorkerRegistry, browser:{url} conflicts |
| `send_message` | Admission, global:input conflicts with computer_control/computer_settings |
| `dev_agent` | Admission, multi-resource conflicts (local_file, network:egress, app:manage, global:input) |
| `telegram_bot` | Admission for polling, net:egress/messaging:send conflicts |
| Cross-tool | file_controller vs dev_agent (local_file), browser_control vs computer_control (display), send_message vs computer_settings (input) |

---

## 7. Exact File/Line References

### Files Requiring Changes (Priority Order)

| File | Lines | Change Type |
|------|-------|-------------|
| `actions/file_controller.py` | Entry point `file_controller()` | Add admission + lifecycle |
| `actions/computer_control.py` | Entry point `computer_control()` + each action handler | Add admission + lifecycle (except screen_record) |
| `actions/browser_control.py` | Entry point `browser_control()` + session creation | Add admission + integrate session lifecycle |
| `actions/send_message.py` | Line 318 `send_message()` + line 347 thread start | Add admission + lifecycle in `_send_and_report()` |
| `actions/dev_agent.py` | Line 1590 `dev_agent()` + line 1535 `_run_job()` | Add PermissionGuard + admission + lifecycle |
| `plugins/telegram_bot.py` | Line 541 `_start_polling()` + line 596 `run()` | Add admission for polling + command handlers |
| `core/worker_registry.py` | Lines 437-610 `extract_resource_keys()` | Add mappings for send_message, dev_agent, telegram_bot |
| `core/permission_guard.py` | OPERATION_SPECS | Add specs for missing operations |

### Test Files Needing New Test Classes
| File | New Test Classes Needed |
|------|------------------------|
| `tests/unit/test_worker_registry_integration.py` | `TestFileControllerIntegration`, `TestComputerControlIntegration`, `TestBrowserControlIntegration`, `TestSendMessageIntegration`, `TestDevAgentIntegration`, `TestTelegramBotIntegration` |

---

## 8. Prioritized Implementation Plan

### Phase A: Core Actions (Highest User Impact)
1. **`file_controller.py`** — Add `_run_with_worker_registry()` pattern or inline admission at `file_controller()` entry. Map all 13 actions to resource keys.
2. **`computer_control.py`** — Add admission at `computer_control()` entry for all actions except `screen_record`. Use existing resource key extraction.
3. **`browser_control.py`** — Add admission at session creation (`_create_session()`) and for each action. Coordinate with `SessionRegistry`.

### Phase B: Background Tools
4. **`send_message.py`** — Add admission in `send_message()` before thread start. Track lifecycle in `_send_and_report()`.
5. **`dev_agent.py`** — Add PermissionGuard at entry. Add admission in `_run_job()` for the background thread. Track job lifecycle.

### Phase C: Persistent Services
6. **`plugins/telegram_bot.py`** — Add admission in `_start_polling()` for the polling task. Add admission in command handlers for `pause`/`resume`/`stop`. Coordinate shutdown with `app:manage`.

### Phase D: Infrastructure
7. **`worker_registry.py`** — Add `extract_resource_keys` cases for `send_message`, `dev_agent`, `telegram_bot`.
8. **`permission_guard.py`** — Add OPERATION_SPECS for missing operations.
9. **Tests** — Add 6 new test classes with ~30 integration tests.

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `file_controller` concurrent write/delete corruption | HIGH | DATA LOSS | Phase A priority 1 |
| `computer_control` input interleaving | HIGH | USER FRUSTRATION | Phase A priority 2 |
| `send_message` + `computer_settings` typing collision | MEDIUM | MESSAGE CORRUPTION | Phase B |
| `dev_agent` long job blocking other tools | MEDIUM | RESOURCE STARVATION | Phase B |
| `telegram_bot` polling + shutdown race | LOW | UNCLEAN SHUTDOWN | Phase C |
| `browser_control` GPU contention | LOW | RENDER GLITCHES | Phase A priority 3 |

---

## 10. Authorization Required

**This is a READ-ONLY audit.** No implementation has been performed.

**Awaiting authorization to proceed with:**
- [ ] Phase A: Core Actions (file_controller, computer_control, browser_control)
- [ ] Phase B: Background Tools (send_message, dev_agent)
- [ ] Phase C: Persistent Services (telegram_bot)
- [ ] Phase D: Infrastructure + Tests

**Estimated effort:** ~200-300 lines of integration code across 6 files + ~30 new tests

---

## Appendix: Verification of Part 1 Completeness

All Part 1 deliverables verified complete:
- ✅ `open_app.py` WorkerRegistry admission + lifecycle + thread-start failure fix
- ✅ `computer_settings.py` WorkerRegistry admission + lifecycle for all 50+ actions
- ✅ `main.py` 8 inline tools via `_run_with_worker_registry()` pattern
- ✅ `worker_registry.py` resource key extraction for all integrated tools
- ✅ `permission_guard.py` OPERATION_SPECS for all integrated operations
- ✅ Tests: 11 integration + 5 resource conflict + 4 direct `_run_with_worker_registry` tests passing
- ✅ Pylance error fixed: `from typing import Any` added to main.py:47
- ✅ Window resource coordination fixed: 30+ computer_settings actions now use shared `global:input`