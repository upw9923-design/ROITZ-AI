# ROITZ AI — Milestone 8 Implementation
## Task: Plugin System Auto-Reload

**Task ID:** ROITZ-2026-11-18-M8  
**Priority:** High  
**Approval Category:** 🟡 Yellow (Architecture & System Extensibility)  
**Status:** ✅ COMPLETED  
**Started:** 2026-11-18T16:10:00Z  
**Completed:** 2026-11-18T17:15:00Z  

---

## 1. Problem Statement

Prior to Milestone 8, ROITZ AI discovered plugins once at application startup via `discover_plugins()` during initialization of `JarvisLive`. This architecture presented several limitations:
1. **Static Discovery**: Adding new plugins, fixing bugs, or updating existing plugin logic required completely shutting down and restarting the application and voice loop.
2. **Module Cache Stagnation**: Deleting a plugin file left orphaned entries in Python's `sys.modules`, memory registries, and Gemini function declaration lists.
3. **Threading Contention**: When worker threads executed plugins while UI threads queried configurations, unsynchronized dictionary access risked race conditions.
4. **Identity Context Loss**: Plugins executing via `main.py` did not propagate the authenticated `CallerIdentity` into thread-local storage or plugin execution contexts.

---

## 2. Architecture & Design

### Dynamic Reloading & Garbage Collection
- **Filesystem Observation**: Dynamic mtime tracking monitors `plugins/*.py` (skipping helper files prefixed with `_`).
- **Dynamic Spec Loading**: Uses `importlib.util.spec_from_file_location`, `module_from_spec`, and `spec.loader.exec_module` with custom module namespaces (`plugins.<stem>`).
- **Module Purging**: When a plugin file is removed from disk, `_unload_file_locked()` removes its registration, purges declarations, and evicts `plugins.<stem>` from `sys.modules`.

### Thread-Safe Synchronization
- **`PluginRegistry._lock`**: All mutations and query iterations across `_plugins`, `_all_records`, `_file_mtimes`, and `_file_to_plugin` are synchronized using `threading.Lock()`.
- **Concurrent Execution**: Read and execution operations in `run()`, `get_tool_declarations()`, `has()`, and `list_for_ui()` safely read synchronized snapshots.

### Background Watcher Daemon
- **Dedicated Watcher**: Background thread (`name="PluginWatcher", daemon=True`) regularly polls for file addition, modification, and deletion.
- **Configurable Polling**: Default 2.0s polling interval in production with graceful shutdown via `threading.Event`.
- **Change Callbacks**: Registered listeners (`register_on_change()`) are triggered upon filesystem modifications to inform UI and service components.

### Security & CallerIdentity Propagation
- **Identity Injection**: Propagates `CallerIdentity` through `PluginRegistry.run(..., identity=...)`.
- **Thread-Local Context**: Sets thread-local context via `set_current_identity()` and guarantees cleanup inside a `finally: clear_current_identity()` block.
- **PermissionGuard Integration**: Validates operations registered in `OPERATION_SPECS` while allowing unconstrained user/custom plugins to execute safely.

---

## 3. Implementation Details

### Files Modified:
1. **[core/plugin_loader.py](core/plugin_loader.py)**:
   - Enhanced `PluginRegistry` with thread-safe lock (`self._lock = threading.Lock()`).
   - Implemented `check_for_updates()`, `_load_or_reload_file_locked()`, and `_unload_file_locked()`.
   - Added `start_watcher()`, `stop_watcher()`, and `register_on_change()`.
   - Updated `_get_operation_name()` and `run()` to support dynamic execution, permission checks, and `CallerIdentity` propagation with thread-local cleanup.
2. **[main.py](main.py)**:
   - Initialized background plugin watcher daemon at startup:
     ```python
     self._plugin_registry.start_watcher(interval_seconds=2.0)
     ```
   - Bound voice session identity when invoking plugins asynchronously in `_execute_tool()`.
3. **[tests/unit/test_plugin_auto_reload.py](tests/unit/test_plugin_auto_reload.py)**:
   - Unit test suite covering all 9 auto-reload lifecycle scenarios.

---

## 4. Verification & Test Results

The unit test suite was executed against Python 3.14 on Windows 11:
```bash
python -m pytest tests/unit/test_plugin_auto_reload.py
```

### Test Suite Execution Matrix:
| Test Method | Description | Result |
|---|---|:---:|
| `test_initial_discovery` | Baseline discovery and helper filtering (`_helper.py`) | ✅ PASSED |
| `test_plugin_addition` | Dynamic detection and load of newly created plugin file | ✅ PASSED |
| `test_plugin_modification` | Dynamic reload and update of code and schema upon file change | ✅ PASSED |
| `test_plugin_deletion` | Complete cleanup from registry, declarations, and `sys.modules` | ✅ PASSED |
| `test_syntax_and_validation_errors_isolated` | Syntax/schema error isolation without crashing host process | ✅ PASSED |
| `test_core_tool_collision_rejected` | Rejection of plugins attempting to shadow core tool names | ✅ PASSED |
| `test_on_change_callback_fires` | Notification dispatch to registered UI/event callbacks | ✅ PASSED |
| `test_watcher_thread_background_polling` | Background watcher daemon auto-detection and synchronization | ✅ PASSED |
| `test_caller_identity_propagation` | Propagation of `CallerIdentity` into thread-local storage | ✅ PASSED |

**Total:** 9 passed in 0.69s.

### Regression Verification:
- `tests/unit/test_telegram_bot.py`: 49 passed in 2.89s.
- `tests/unit/test_dashboard_security.py`: 6 passed in 3.02s.

---

## 5. AGENTS.md Concurrency & Qt Rules Compliance

- **Worker Thread Isolation**: All plugin loader routines operate purely within worker/daemon threads.
- **No Direct Qt Widget Manipulation**: As mandated by `AGENTS.md`, plugins interact with the UI solely through thread-safe `player` delegates (e.g. `write_log`, `show_content`).
- **Thread-Local Cleanliness**: Any thread-local identity assigned during execution is strictly purged via `finally` blocks to prevent leakages across thread pool workers.

---

## 6. Next Steps

- **Milestone 9**: Proactive Intelligence Wake Triggers
- Integration of scheduled, ambient, and event-driven wake prompts within `JarvisLive` loop.

---

Co-Authored-By: Claude Code <noreply@anthropic.com>
