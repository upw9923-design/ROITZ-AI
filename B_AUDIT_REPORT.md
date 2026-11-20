# Phase B Read-only Architecture Audit Report

**Date**: 2026-11-14  
**Mode**: STRICT READ-ONLY  
**Scope**: `send_message.py` and `dev_agent.py` WorkerRegistry Integration Planning

---

## 1. Executive Summary

This audit analyzes `actions/send_message.py` (6 messaging platforms) and `actions/dev_agent.py` (3 operational modes) for WorkerRegistry integration. Both modules currently **lack WorkerRegistry integration** despite having partial OPERATION_SPECS entries. They use background threads with immediate `outcome.started` returns, creating lifecycle tracking gaps.

**Key Finding**: 8 operations across 2 modules need full WorkerRegistry integration (permission check → admission → lifecycle management).

---

## 2. Complete Action Inventory

### 2.1 send_message.py — 6 Platform Operations

| # | Platform | Handler | Verification | Current OPERATION_SPECS | Resource Keys (extract_resource_keys) |
|---|----------|---------|--------------|------------------------|---------------------------------------|
| 1 | WhatsApp | `_send_whatsapp` | **Verified** (driver) | ✅ `send_message:whatsapp` | `messaging:whatsapp` |
| 2 | Telegram | `_send_telegram` → `_desktop_send` | Unverified (pyautogui) | ✅ `send_message:telegram` | `messaging:telegram` |
| 3 | Instagram | `_send_instagram` | Unverified (browser + pyautogui) | ❌ **MISSING** | `messaging:instagram` |
| 4 | Signal | `_send_signal` → `_desktop_send` | Unverified (pyautogui) | ❌ **MISSING** | `messaging:signal` |
| 5 | Discord | `_send_discord` → `_desktop_send` | Unverified (pyautogui) | ❌ **MISSING** | `messaging:discord` |
| 6 | Messenger | `_send_messenger` | Unverified (browser + pyautogui) | ❌ **MISSING** | `messaging:messenger` |

**Fallback handler** (line 315): Any unrecognized platform → `_desktop_send(platform.title())` — would need `messaging:{platform}` key.

**Resource Key Strategy** (worker_registry.py:638-641):
```python
elif tool_name == "send_message":
    platform = parameters.get("platform", "").lower().strip()
    if platform:
        keys.append(f"messaging:{platform}")
```

### 2.2 dev_agent.py — 3 Operational Modes

| # | Mode | Entry Point | Description | Current OPERATION_SPECS | Resource Keys |
|---|------|-------------|-------------|------------------------|---------------|
| 1 | `improve` | `_start_improve` → `_improve_folder` | Modify existing project folder (write files, run tests) | ✅ `dev_agent:improve` | `project:{resolved_folder_path}` |
| 2 | `build` | `_start_build` → `_build_project` | Create new project (write files, pip install, run, VSCode) | ✅ `dev_agent:build` | `project:{resolved_folder_path}` |
| 3 | `status` | `_status_report` | Read job state (no side effects) | ✅ `dev_agent:status` | `project:{resolved_folder_path}` |

**Resource Key Strategy** (worker_registry.py:630-636):
```python
elif tool_name == "dev_agent":
    mode = parameters.get("mode", "").lower().strip()
    folder = parameters.get("folder", ".")
    try:
        keys.append(f"project:{Path(folder).resolve()}")
    except Exception:
        keys.append(f"project:{folder}")
```

---

## 3. Resource Conflict Behavior — ANALYSIS

### 3.1 send_message Resource Conflicts

| Resource | Platforms | Conflict Behavior |
|----------|-----------|-------------------|
| `messaging:whatsapp` | WhatsApp only | **Isolated per platform** — different platforms don't conflict |
| `messaging:telegram` | Telegram only | Isolated |
| `messaging:instagram` | Instagram only | Isolated |
| `messaging:signal` | Signal only | Isolated |
| `messaging:discord` | Discord only | Isolated |
| `messaging:messenger` | Messenger only | Isolated |

**Cross-module conflicts** (via underlying mechanisms):
| Underlying Resource | send_message Actions | Conflicts With |
|---------------------|---------------------|----------------|
| `global:input` (pyautogui) | All desktop_send platforms (Telegram, Signal, Discord, WhatsApp fallback) | `computer_control:*` (click, type, hotkey, etc.), `computer_settings:*` (all input actions), `browser_control:*` (interactive) |
| `app:manage` (app launch) | All platforms via `_open_app` | `computer_control:close_app`, `computer_control:focus_window`, `open_app` |
| `network:egress` (webbrowser) | Instagram, Messenger | `browser_control:go_to/search/new_tab`, `manage_monitor:add/remove`, `dev_agent:build` (pip install) |
| `global:display` (screenshot) | None currently | `computer_control:screenshot/screen_find`, `browser_control:screenshot` |

**Critical Gap**: Current `extract_resource_keys` only returns `messaging:{platform}`. It **does not capture** the underlying `global:input`, `app:manage`, or `network:egress` resources that the desktop automation actually uses. This means:
- Two send_message operations on different platforms **won't conflict** at the messaging level
- But they **will conflict unpredictably** at the OS level (both typing via pyautogui simultaneously)

### 3.2 dev_agent Resource Conflicts

| Resource | Modes | Conflict Behavior |
|----------|-------|-------------------|
| `project:{path}` | All modes (improve, build, status) | **Mutually exclusive per project folder** — only one dev_agent job per folder |

**Cross-module conflicts**:
| Underlying Resource | dev_agent Actions | Conflicts With |
|---------------------|------------------|----------------|
| `global:input` | None directly | N/A |
| `app:manage` | VSCode launch (`_open_vscode`) | `open_app`, `computer_control:close_app` |
| `network:egress` | `pip install`, project run commands | `browser_control:go_to`, `send_message:instagram/messenger`, `manage_monitor` |
| `proc.exec` | `_run_project`, `_install_dependencies` | `dev_agent:build` (itself), any `proc.exec` capability |
| `fs.write/read` | File operations in project folder | `file_controller:*` on same paths |

**Critical Gap**: The `project:{path}` key only tracks the project folder. It **does not capture**:
- `proc.exec` for subprocess operations (pip, test runs, project execution)
- `network:egress` for pip install
- `app:manage` for VSCode launch
- `fs.write`/`fs.read` for individual file operations within the project

---

## 4. Permission Metadata — GAP ANALYSIS

### 4.1 send_message OPERATION_SPECS (permission_guard.py:142-145)

```python
# Current (INCOMPLETE - only 2 of 6 platforms)
"send_message:whatsapp":       OperationSpec("messaging.send",                          idempotent=False, read_only=False, resource_scope=ResourceScope.REMOTE_SERVICE),
"send_message:telegram":       OperationSpec("messaging.send",                          idempotent=False, read_only=False, resource_scope=ResourceScope.REMOTE_SERVICE,
                                                 additional_caps=("net.egress",)),
```

**Missing entries needed**:
| Platform | Capability | Idempotent | Read-Only | Resource Scope | Additional Caps |
|----------|------------|------------|-----------|----------------|-----------------|
| Instagram | messaging.send | ❌ | ❌ | REMOTE_SERVICE | net.egress (browser) |
| Signal | messaging.send | ❌ | ❌ | REMOTE_SERVICE | (desktop app) |
| Discord | messaging.send | ❌ | ❌ | REMOTE_SERVICE | net.egress (can be browser/desktop) |
| Messenger | messaging.send | ❌ | ❌ | REMOTE_SERVICE | net.egress (browser) |
| Fallback (generic) | messaging.send | ❌ | ❌ | REMOTE_SERVICE | varies |

**Metadata Correctness Issues**:
1. **WhatsApp**: `REMOTE_SERVICE` is correct for driver path, but desktop fallback uses `global:input` + `app:manage` (LOCAL_SYSTEM). The spec should reflect the **actual code path taken**.
2. **Telegram**: Has `net.egress` additional cap but desktop_send uses pyautogui (LOCAL_SYSTEM), not network. Only if using Telegram Web would net.egress apply.
3. **All desktop_send platforms**: Actually use `input.simulate` (pyautogui) + `app.manage` (app launch) — should be `LOCAL_SYSTEM` with `additional_caps=("input.simulate", "app.manage")`.

### 4.2 dev_agent OPERATION_SPECS (permission_guard.py:126-140)

```python
# Current (COMPLETE for 3 modes)
"dev_agent:improve": OperationSpec("fs.write",
                                    get_project=lambda p: Path(p.get("folder", ".")),
                                    idempotent=False, read_only=False, resource_scope=ResourceScope.LOCAL_FILE),
"dev_agent:build": OperationSpec("proc.exec", "pytest_project",
                                  get_project=lambda p: Path(p.get("folder", ".")),
                                  get_template_args=lambda p: {"test_path": p.get("test_path", "")},
                                  idempotent=False, read_only=False, resource_scope=ResourceScope.LOCAL_SYSTEM,
                                  additional_caps=("proc.exec", "net.egress")),
"dev_agent:status": OperationSpec("fs.read",
                                   get_project=lambda p: Path(p.get("folder", ".")),
                                   idempotent=True, read_only=True, resource_scope=ResourceScope.LOCAL_FILE),
```

**Metadata Correctness Issues**:
1. **improve**: `resource_scope=LOCAL_FILE` but actually does `fs.write` + `proc.exec` (test runs) + `net.egress` (pip install if deps missing). Should be `LOCAL_SYSTEM` with `additional_caps=("proc.exec", "net.egress")`.
2. **build**: Correctly has `proc.exec` + `net.egress`, but also does `app.manage` (VSCode launch) and `fs.write` for many files.
3. **status**: Correct — read-only, idempotent, LOCAL_FILE.

---

## 5. WorkerRegistry Lifecycle Risks

### 5.1 send_message Lifecycle (lines 318-357, 360-407)

```
send_message(parameters)
    │
    ├─► Permission check: NONE currently
    │
    ├─► Creates daemon thread: threading.Thread(target=_send_and_report, ...)
    │
    ├─► Returns immediately: outcome.started("send_message", platform, to)
    │
    └─► Background thread (_send_and_report):
            ├─► _resolve_platform(platform)(receiver, message)
            │       ├─► WhatsApp: tries driver → outcome.done / outcome.failed
            │       └─► Others: _desktop_send → outcome.unverified
            │
            ├─► Prints result to terminal
            ├─► If problem: player.write_log / player.request_say
            └─► NO WorkerRegistry admission, NO resource reservation, NO lifecycle tracking
```

**Risks**:
1. **No admission control** — Multiple send_message calls can run concurrently, all typing via pyautogui simultaneously
2. **No resource tracking** — Registry doesn't know these threads exist
3. **No cleanup on failure** — If thread crashes, no mark_failed/release_resources
4. **Unresolved workers** — Long sleeps (2.5s app launch + typing) mean threads stay alive; if parent task times out, these become orphaned
5. **Outcome contract violation** — Returns `started` but background result never goes through WorkerRegistry completion

### 5.2 dev_agent Lifecycle (lines 1509-1588)

```
dev_agent(parameters, mode="improve/build")
    │
    ├─► _job_lock.acquire(blocking=False) — single global lock
    │
    ├─► _new_job() — creates _JOB dict, publishes to UI
    │
    ├─► _run_job(lambda: _improve_folder/_build_project, ...)
    │       │
    │       ├─► threading.Thread(target=work, daemon=True, name="dev_agent-job").start()
    │       │
    │       └─► Returns "[STARTED] The coding agent... is now working..."
    │
    └─► Background thread (work()):
            ├─► _improve_folder / _build_project (10-300+ seconds)
            │       ├─► Reads project files
            │       ├─► Calls gemini (LLM) multiple times
            │       ├─► Writes files to disk
            │       ├─► Runs subprocess (pip install, pytest, project run)
            │       ├─► Opens VSCode (subprocess.Popen)
            │       └─► Updates _JOB dict via _update/_log (thread-safe)
            │
            ├─► On completion/error: _update(status, result, finished), _job_lock.release()
            ├─► If speak: speak("[DEV_AGENT_DONE] ...")
            └─► NO WorkerRegistry admission, NO resource reservation for subprocesses
```

**Risks**:
1. **Global `_job_lock` only** — Prevents concurrent dev_agent jobs but doesn't integrate with WorkerRegistry
2. **Subprocesses invisible** — `pip install`, `pytest`, project runs, VSCode launch not tracked
3. **Long-running LLM calls** — Multiple `gemini.call()` with 60-180s timeouts; if task times out, worker becomes UNRESOLVED
4. **No resource reservation for project folder** — file_controller operations on same folder could conflict
5. **VSCode launch** — `subprocess.Popen` to `code` command not tracked (app:manage)

---

## 6. Threading Model Compliance

| Module | Thread Creation | Qt Widget Access | Player Usage | Compliant? |
|--------|----------------|------------------|--------------|------------|
| send_message | `threading.Thread(daemon=True)` in `send_message()` | ❌ None | ✅ `player.write_log`, `player.request_say` (thread-safe) | ✅ Yes |
| dev_agent | `threading.Thread(daemon=True)` in `_run_job()` | ❌ None | ✅ `player.write_log`, `player.show_code_job` via `_publish()` | ✅ Yes |

**Both modules correctly avoid Qt widgets on worker threads.** They use `player` thread-safe methods for UI updates.

---

## 7. Test Coverage — CURRENT STATE

### 7.1 send_message Tests
- **Unit tests**: **ZERO** — No test file exists
- **Integration tests**: **ZERO**
- **Metadata tests**: Only 2 platforms tested in `test_operation_metadata.py:200-207`

### 7.2 dev_agent Tests
- **Unit tests**: **ZERO** — No test file exists
- **Integration tests**: **ZERO**
- **Metadata tests**: All 3 modes tested in `test_operation_metadata.py:177-198`

### 7.3 WorkerRegistry Integration Tests
- **ZERO** — No tests for send_message or dev_agent WorkerRegistry integration

---

## 8. Implementation Plan — B1, B2, B3 Sequence

### B1: send_message WorkerRegistry Integration

**Files to Modify**:
1. `actions/send_message.py` — Add permission check + WorkerRegistry admission + lifecycle
2. `core/permission_guard.py` — Add 4 missing OPERATION_SPECS entries
3. `core/worker_registry.py` — Enhance `extract_resource_keys` for underlying resources
4. `tests/unit/test_operation_metadata.py` — Add tests for all 6 platforms
5. `tests/unit/test_task_monitoring.py` — Add send_message resource conflict tests

**Implementation Pattern** (following A1/A2/A3):
```python
def send_message(parameters, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    platform = params.get("platform", "whatsapp").strip().lower()
    operation_name = f"send_message:{platform}"
    
    # 1. Permission check
    guard = get_permission_guard()
    result = guard.check_operation(operation_name, params)
    if not result.allowed:
        if result.reason == "approval_required":
            return result.instruction
        return outcome.failed(operation_name, result.reason)
    
    # 2. WorkerRegistry admission
    registry = get_global_registry()
    worker = create_worker_record(
        task_id="inline",
        step_id=operation_name,
        tool_name="send_message",
        parameters=params,
        operation_name=operation_name,
        resource_scope="REMOTE_SERVICE" if platform in ("whatsapp", "instagram", "messenger") else "LOCAL_SYSTEM",
        is_idempotent=False,
    )
    admitted, reason = registry.admit_worker(worker)
    if not admitted:
        return outcome.failed(operation_name, f"resource conflict: {reason}")
    
    # 3. Start background work with lifecycle tracking
    def _send_and_report_tracked():
        try:
            result = _resolve_platform(platform)(params.get("receiver"), params.get("message_text"))
            worker.mark_completed("done")
            registry.release_resources(worker.attempt_id)
            # ... existing reporting logic
        except Exception as e:
            worker.mark_failed(str(e))
            registry.release_resources(worker.attempt_id)
            # ... existing error reporting
    
    threading.Thread(target=_send_and_report_tracked, daemon=True, name="send-message").start()
    return outcome.started(operation_name, platform=platform, to=params.get("receiver"))
```

**Resource Key Enhancement Needed** (worker_registry.py):
```python
elif tool_name == "send_message":
    platform = parameters.get("platform", "").lower().strip()
    if platform:
        keys.append(f"messaging:{platform}")
        # ADD: underlying resources based on platform
        if platform in ("instagram", "messenger"):
            keys.append("network:egress")  # webbrowser.open
        elif platform != "whatsapp":  # WhatsApp driver doesn't use pyautogui
            keys.append("global:input")   # pyautogui typing
            keys.append("app:manage")     # _open_app
```

### B2: dev_agent WorkerRegistry Integration

**Files to Modify**:
1. `actions/dev_agent.py` — Add WorkerRegistry admission in `_run_job` / `_start_improve` / `_start_build`
2. `core/worker_registry.py` — Enhance `extract_resource_keys` for subprocess resources
3. `tests/unit/test_operation_metadata.py` — Verify metadata correctness
4. `tests/unit/test_task_monitoring.py` — Add dev_agent resource conflict tests

**Implementation Pattern**:
```python
def _run_job(job, name: str, who: str, speak=None, player=None) -> str:
    # ... existing _job_lock logic ...
    
    # WorkerRegistry admission for the entire job
    registry = get_global_registry()
    worker = create_worker_record(
        task_id="inline",
        step_id=f"dev_agent:{name}",
        tool_name="dev_agent",
        parameters={"mode": "improve" if "improve" in name else "build", "folder": folder},
        operation_name=f"dev_agent:{'improve' if 'improve' in name else 'build'}",
        resource_scope="LOCAL_SYSTEM",
        is_idempotent=False,
    )
    admitted, reason = registry.admit_worker(worker)
    if not admitted:
        _job_lock.release()
        return outcome.failed(f"dev_agent:{name}", f"resource conflict: {reason}")
    
    def work():
        try:
            result = job()
            # ... existing status logic ...
            worker.mark_completed("done")
        except Exception as e:
            worker.mark_failed(str(e))
        finally:
            registry.release_resources(worker.attempt_id)
            _job_lock.release()
    
    threading.Thread(target=work, daemon=True, name="dev_agent-job").start()
    return "[STARTED] ..."
```

**Resource Key Enhancement Needed** (worker_registry.py):
```python
elif tool_name == "dev_agent":
    mode = parameters.get("mode", "").lower().strip()
    folder = parameters.get("folder", ".")
    try:
        keys.append(f"project:{Path(folder).resolve()}")
    except Exception:
        keys.append(f"project:{folder}")
    
    # ADD: subprocess resources for build/improve
    if mode in ("build", "improve"):
        keys.append("proc:exec")      # subprocess.run for pip, pytest, project run
        keys.append("network:egress") # pip install
        keys.append("app:manage")     # VSCode launch
```

### B3: Cross-Module Coordination Tests

**New Test File**: `tests/unit/test_phase_b_cross_module.py`

**Test Scenarios**:
| Test | Conflict | Expected |
|------|----------|----------|
| `test_send_message_telegram_vs_computer_control_type` | `global:input` | Blocked |
| `test_send_message_instagram_vs_browser_control_go_to` | `network:egress` | Blocked |
| `test_send_message_whatsapp_driver_vs_computer_control_click` | No conflict (driver) | Allowed |
| `test_dev_agent_build_vs_send_message_instagram` | `network:egress` (pip vs browser) | Blocked |
| `test_dev_agent_improve_vs_file_controller_write` | `project:{path}` + `file:{path}` | Blocked |
| `test_dev_agent_vscode_launch_vs_open_app` | `app:manage` | Blocked |
| `test_two_dev_agent_jobs_different_folders` | Different `project:{path}` | Allowed |
| `test_dev_agent_status_read_only` | `project:{path}` (read_only) | Allowed with other reads |

---

## 9. Metadata Corrections Required

### 9.1 send_message OPERATION_SPECS Updates

| Operation | Capability | Idempotent | Read-Only | Resource Scope | Additional Caps |
|-----------|------------|------------|-----------|----------------|-----------------|
| `send_message:whatsapp` | messaging.send | ❌ | ❌ | REMOTE_SERVICE | (driver) / input.simulate, app.manage (fallback) |
| `send_message:telegram` | messaging.send | ❌ | ❌ | LOCAL_SYSTEM | input.simulate, app.manage |
| `send_message:instagram` | messaging.send | ❌ | ❌ | REMOTE_SERVICE | net.egress, input.simulate |
| `send_message:signal` | messaging.send | ❌ | ❌ | LOCAL_SYSTEM | input.simulate, app.manage |
| `send_message:discord` | messaging.send | ❌ | ❌ | LOCAL_SYSTEM | input.simulate, app.manage |
| `send_message:messenger` | messaging.send | ❌ | ❌ | REMOTE_SERVICE | net.egress, input.simulate |

**Note**: WhatsApp has dual path (driver + fallback). The spec should reflect the **primary verified path** (REMOTE_SERVICE). Fallback conflicts are handled by resource keys.

### 9.2 dev_agent OPERATION_SPECS Updates

| Operation | Capability | Idempotent | Read-Only | Resource Scope | Additional Caps |
|-----------|------------|------------|-----------|----------------|-----------------|
| `dev_agent:improve` | fs.write | ❌ | ❌ | LOCAL_SYSTEM | proc.exec, net.egress |
| `dev_agent:build` | proc.exec | ❌ | ❌ | LOCAL_SYSTEM | proc.exec, net.egress, app.manage |
| `dev_agent:status` | fs.read | ✅ | ✅ | LOCAL_FILE | (none) |

---

## 10. Acceptance Criteria for Phase B

### B1 (send_message) — ACCEPTED WHEN:
- [ ] All 6 platforms have OPERATION_SPECS entries with correct metadata
- [ ] Permission check before WorkerRegistry admission in `send_message()`
- [ ] WorkerRegistry admission with `create_worker_record` + `admit_worker`
- [ ] Background thread wraps work in try/except with `mark_completed`/`mark_failed` + `release_resources`
- [ ] `extract_resource_keys` returns `messaging:{platform}` + underlying resources (`global:input`, `app:manage`, `network:egress`)
- [ ] Metadata tests pass for all 6 platforms
- [ ] Resource conflict tests pass (cross-module with computer_control, browser_control)
- [ ] No regression in existing functionality

### B2 (dev_agent) — ACCEPTED WHEN:
- [ ] OPERATION_SPECS metadata corrected (improve→LOCAL_SYSTEM with proc.exec+net.egress)
- [ ] WorkerRegistry admission in `_run_job` before starting background thread
- [ ] Background thread lifecycle: `mark_completed`/`mark_failed` + `release_resources` on all paths
- [ ] `extract_resource_keys` returns `project:{path}` + `proc:exec` + `network:egress` + `app:manage` for build/improve
- [ ] Metadata tests pass with corrected values
- [ ] Resource conflict tests pass (cross-module with file_controller, send_message, open_app)
- [ ] No regression in existing functionality
- [ ] Global `_job_lock` still prevents concurrent dev_agent jobs (complementary to WorkerRegistry)

### B3 (Cross-Module) — ACCEPTED WHEN:
- [ ] All cross-module conflict tests pass
- [ ] Resource key strategy correctly isolates or conflicts as designed
- [ ] No false positives (independent operations allowed)
- [ ] No false negatives (conflicting operations blocked)

---

## 11. Risk Assessment

| Risk | Module | Severity | Mitigation |
|------|--------|----------|------------|
| WhatsApp driver vs fallback dual resource profile | send_message | HIGH | Resource keys capture both; spec reflects primary (driver) path |
| Desktop automation timing flakiness | send_message | MEDIUM | Unverified outcome contract already honest; WorkerRegistry adds admission only |
| Long-running LLM calls in dev_agent | dev_agent | HIGH | WorkerRegistry tracks as UNRESOLVED if timeout; retry logic respects idempotent=False |
| Subprocess resource invisibility | dev_agent | HIGH | Enhanced resource keys capture proc:exec, net:egress, app:manage |
| Global _job_lock vs WorkerRegistry dual admission | dev_agent | LOW | Keep both: _job_lock for dev_agent serialization, WorkerRegistry for cross-module |
| No existing tests for either module | Both | CRITICAL | Must add comprehensive tests as part of B1/B2 |

---

## 12. Comparison: A1/A2/A3 vs B1/B2 Architecture Alignment

| Aspect | A1 (computer_control) | A2 (file_controller) | A3 (browser_control) | B1 (send_message) | B2 (dev_agent) |
|--------|----------------------|---------------------|---------------------|-------------------|----------------|
| Resource key format | `global:input`, `global:display`, `app:manage` | `file:{path}` | `browser:session:{browser}` + `network:{domain}` | `messaging:{platform}` + underlying | `project:{path}` + subprocess |
| Multi-resource reservation | `screen_click` → display + input | `move`/`copy` → src + dst | Navigation → session + network | Platform + input/app/network | Project + proc/net/app |
| Background thread pattern | N/A (sync) | N/A (sync) | Persistent bg thread + asyncio | `threading.Thread` + `outcome.started` | `threading.Thread` + `outcome.started` + `_job_lock` |
| is_idempotent flag | Set per action | Set per action | Set per action (line 1100) | All False (except status) | improve/build=False, status=True |
| Permission check location | Before admission | Before admission | Before admission | **MISSING** → add before admission | **MISSING** → add in _run_job |
| Error handling | try/except mark_failed + release | try/except mark_failed + release | try/except mark_failed + release | **MISSING** → add in _send_and_report | **MISSING** → add in work() |
| Outcome contract | outcome.failed on errors | outcome.failed on errors | outcome.failed on errors | outcome.started → background reports | outcome.started → background reports |

---

## 13. Conclusion

**Phase B is ready for implementation**. Both modules have:
- Clear action inventories (6 + 3 operations)
- Existing OPERATION_SPECS (partial for send_message, complete but needs correction for dev_agent)
- WorkerRegistry resource key extraction (basic, needs enhancement for underlying resources)
- Background thread patterns compatible with WorkerRegistry lifecycle
- No Qt threading violations

**Implementation Order**: B1 (send_message) → B2 (dev_agent) → B3 (cross-module tests), following the exact patterns established in A1/A2/A3.

**Estimated Scope**: 
- B1: ~5 files, ~200 lines changed
- B2: ~4 files, ~150 lines changed  
- B3: ~1 new test file, ~15 tests