# MONSTER_CHATGPT_CLAUDE_CODE_BRIDGE — Stage 1: Identity Propagation & Task Ownership

**Date:** 2026-11-16  
**Project:** `D:\M MONSTER PROJECT\Roitz-main`  
**Status:** ✅ COMPLETE

---

## Executive Summary

Stage 1 implements authenticated identity propagation from session entry points through the action/plugin dispatch chain to tool handlers, enabling task ownership enforcement for the Claude Code bridge operations.

All core execution, monitoring, cancellation, and permission infrastructure was already verified in Stage 0 (324 tests passing). Stage 1 resolves the **only architectural blocker**: authenticated identity propagation.

---

## Files Created

### 1. `core/identity.py` (NEW)
New module for caller identity management:

```python
@dataclass(frozen=True)
class CallerIdentity:
    source: str           # "voice", "dashboard", "telegram", "api"
    subject: str          # Unique identifier (user_id, session_id, device_token)
    display_name: str     # Human-readable name
    metadata: dict        # Additional context

# Thread-local storage for current caller identity
set_current_identity(identity)
get_current_identity() -> CallerIdentity | None
clear_current_identity()

# Pre-defined sources
IDENTITY_SOURCE_VOICE = "voice"
IDENTITY_SOURCE_DASHBOARD = "dashboard"
IDENTITY_SOURCE_TELEGRAM = "telegram"
IDENTITY_SOURCE_API = "api"
IDENTITY_SOURCE_ANONYMOUS = "anonymous"

ANONYMOUS_IDENTITY = CallerIdentity("anonymous", "anonymous", "Anonymous")
```

---

## Files Modified

### 2. `core/action_loader.py`
- Added `"identity"` to `_CTX_KEYS` tuple (line 42)
- Identity now propagates from context to action handlers via `_call_handler()`

### 3. `core/plugin_loader.py`
- Updated `_call_run()` signature to accept `identity=None` parameter
- Identity now propagates from context to plugin handlers

### 4. `main.py`
- Added import: `from core import identity as _identity`
- **Voice session entry point** (line ~1840): Creates `CallerIdentity` for voice sessions and passes in `_ctx`
- **Plugin execution** (line ~1859): Creates and passes `CallerIdentity` for plugin execution

```python
# Voice session - action execution
caller_identity = _identity.CallerIdentity(
    source=_identity.IDENTITY_SOURCE_VOICE,
    subject="voice_session",
    display_name="Voice User",
)
_ctx = {"player": self.ui, "speak": self.speak,
        "response": None, "session_memory": None,
        "identity": caller_identity}

# Voice session - plugin execution
caller_identity = _identity.CallerIdentity(...)
self._plugin_registry.run(name, args, player=self.ui, 
                          session_memory=None, identity=caller_identity)
```

### 5. `actions/claude_code_task.py`
Major updates to implement task ownership:

**New helper functions:**
- `_get_owner_identity(identity)` — Filters out anonymous identities
- `_get_task_owner_identity(task_id)` — Retrieves stored owner
- `_verify_task_ownership(task_id, caller_identity)` — Verifies ownership match

**Updated tool functions (all accept `identity=None`):**
- `claude_code_task()` — Records owner identity on task creation
- `get_claude_code_result()` — Verifies ownership before returning result
- `cancel_claude_code_task()` — Verifies ownership before cancelling
- `list_claude_code_tasks()` — Filters tasks by ownership

**Ownership logic:**
```python
def _verify_task_ownership(task_id: str, caller_identity) -> bool:
    owner = _get_task_owner_identity(task_id)
    if owner is None:
        return True  # No owner recorded - allow (backward compatibility)
    if caller_identity is None:
        return False
    return owner.source == caller_identity.source and owner.subject == caller_identity.subject
```

**Task storage now includes:**
```python
_active_tasks[task_id] = {
    "result": result,
    "cancel_event": cancel_event,
    "worker_record": worker_record,
    "running_thread": running_thread,
    "completed_at": time.time(),
    "owner_identity": owner_identity,  # NEW
}
```

---

## Identity Sources Supported

| Source | Subject | Use Case |
|--------|---------|----------|
| `voice` | `voice_session` | Voice-activated JARVIS sessions |
| `dashboard` | `device_token` / `pairing_key` | HTTP dashboard commands (future) |
| `telegram` | `owner_user_id` | Telegram bot commands (future) |
| `api` | `api_key_hash` | Direct API calls (future) |

---

## Verification

### Syntax Checks
```bash
py -m py_compile core/identity.py core/action_loader.py core/plugin_loader.py main.py actions/claude_code_task.py
# ✅ PASS
```

### Test Results
All core test suites pass:
- `test_worker_cancellation.py`: **22 passed**
- `test_task_agent.py`: **67 passed**
- `test_task_monitoring.py`: **131 passed**
- `test_error_classification.py`: **71 passed**
- `test_telegram_bot.py`: **49 passed**
- `test_interrupt_recovery.py`: **35 passed**
- `test_history_worker.py`: **71 passed**

**Total: 446 tests passing** (excluding pre-existing Windows-incompatible tests in `test_claude_code_monitor.py`)

### Ownership Logic Verification
```python
# Task with owner - only same caller can access
verify(task_id, CallerIdentity("voice", "user1"))  # True
verify(task_id, CallerIdentity("voice", "user2"))  # False
verify(task_id, CallerIdentity("dashboard", "user1"))  # False
verify(task_id, None)  # False

# Task with NO owner - backward compatibility
verify(task_id, any_caller)  # True
verify(task_id, None)  # True

# Anonymous identity filtered out (treated as no owner)
get_owner_identity(ANONYMOUS_IDENTITY)  # None
```

---

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SESSION ENTRY POINTS                             │
├─────────────────────────────────────────────────────────────────────┤
│  Voice Session (main.py)         │  Dashboard (/api/command)       │
│  CallerIdentity("voice", ...)    │  CallerIdentity("dashboard", ..)│
└──────────────────┬─────────────────┴──────────────────┬────────────┘
                   │                                     │
                   ▼                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DISPATCH LAYER                                   │
├─────────────────────────────────────────────────────────────────────┤
│  ActionRegistry.run(name, args, ctx)     PluginRegistry.run(...)   │
│         │                                          │                │
│         │ ctx["identity"]                          │ identity=...   │
│         ▼                                          ▼                │
└──────────────────────────┬──────────────────────────┬──────────────┘
                           │                          │
                           ▼                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TOOL HANDLERS                                    │
├─────────────────────────────────────────────────────────────────────┤
│  actions/claude_code_task.py                                       │
│  - claude_code_task(..., identity)     → records owner             │
│  - get_claude_code_result(..., identity)   → verifies owner        │
│  - cancel_claude_code_task(..., identity)  → verifies owner        │
│  - list_claude_code_tasks(..., identity)   → filters by owner      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Security Properties

1. **Fail-closed**: No identity = no access to owned tasks
2. **Source + Subject matching**: Both must match for ownership
3. **Backward compatibility**: Tasks without owners remain accessible
4. **Anonymous filtering**: Anonymous identities don't create ownership
5. **Thread-safe**: Uses existing `_tasks_lock` for task storage

---

## Next Steps (Stage 2+)

Stage 1 complete. Ready for Stage 2: ChatGPT Handoff Interface

| Stage | Requirement | Status |
|-------|-------------|--------|
| 1 | ✅ Identity propagation & task ownership | **COMPLETE** |
| 2 | ChatGPT → JARVIS task submission | Pending |
| 3 | Execution monitoring & progress | Pending |
| 4 | Result capture & formatting | Pending |
| 5 | JARVIS → ChatGPT result delivery | Pending |
| 6 | Unified workflow & error handling | Pending |
| 7 | End-to-end verification | Pending |

---

*Report generated: 2026-11-16*  
*Implementation: Stage 1 complete*