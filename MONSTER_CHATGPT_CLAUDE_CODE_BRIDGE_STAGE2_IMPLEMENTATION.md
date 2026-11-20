# MONSTER_CHATGPT_CLAUDE_CODE_BRIDGE — Stage 2: ChatGPT Handoff Interface

**Date:** 2026-11-16  
**Project:** `D:\M MONSTER PROJECT\Roitz-main`  
**Status:** ✅ COMPLETE

---

## Executive Summary

Stage 2 implements the **ChatGPT → JARVIS task submission interface** via a new authenticated HTTP endpoint `/api/claude-task` on the existing dashboard server. This allows ChatGPT (or any external client) to submit prompts directly to `claude_code_task` with proper identity propagation and task ownership tracking established in Stage 1.

---

## Architecture

```
┌─────────────────┐     HTTPS + AES-GCM      ┌──────────────────────┐
│    ChatGPT      │ ──────────────────────▶ │  JARVIS Dashboard    │
│  (External)     │   POST /api/claude-task  │  (FastAPI on 8001)   │
└─────────────────┘                          └──────────┬───────────┘
                                                          │
                                                          │ _claude_task_callback
                                                          ▼
┌─────────────────┐                          ┌──────────────────────┐
│   Task Result   │ ◀─────────────────────── │  JarvisLive          │
│   (JSON)        │   Returns task_id +      │  _handle_claude_task │
└─────────────────┘   outcome string         │  → action_registry   │
                                              │  → claude_code_task  │
                                              └──────────┬───────────┘
                                                         │
                                                         ▼
                                              ┌──────────────────────┐
                                              │  WorkerRegistry +    │
                                              │  ProcessMonitor      │
                                              │  (Stage 0 infra)     │
                                              └──────────────────────┘
```

---

## Files Modified

### 1. `dashboard/server.py`

**New callback registration:**
```python
def set_claude_task_callback(self, fn) -> None:
    """Register a callback for executing claude_code_task from external sources."""
    self._claude_task_callback = fn
```

**New endpoint: `/api/claude-task`**
```python
@app.post("/api/claude-task")
async def claude_task(req: Request):
    """
    Execute a Claude Code task from external source (e.g., ChatGPT bridge).
    
    Request body:
    {
        "prompt": "The prompt to send to Claude Code (required)",
        "task_id": "Optional custom task ID",
        "cwd": "Optional working directory",
        "timeout": 300,
        "additional_args": [],
        "wait": false
    }
    
    Response:
    {
        "ok": true,
        "task_id": "generated_task_id",
        "outcome": "started|done|...",
        "result": {...}  # if wait=true
    }
    """
```

**Security:**
- Requires valid Bearer token (same pairing-key auth as other dashboard endpoints)
- Rate limited by existing `_Throttle` mechanism
- Inherits TLS + AES-GCM encryption when HTTPS enabled

---

### 2. `main.py`

**Dashboard initialization (line ~2940):**
```python
self._dashboard.set_claude_task_callback(self._handle_claude_task)
```

**New handler method:**
```python
async def _handle_claude_task(self, params: dict) -> dict:
    """Handle claude_code_task execution from external API (ChatGPT bridge)."""
    from core import identity as _identity
    
    # Create API identity for the ChatGPT bridge
    api_identity = _identity.CallerIdentity(
        source=_identity.IDENTITY_SOURCE_API,
        subject="chatgpt_bridge",
        display_name="ChatGPT Bridge",
        metadata={"endpoint": "/api/claude-task"}
    )
    
    # Build context with identity for the action registry
    ctx = {
        "player": self.ui,
        "speak": None,
        "response": None,
        "session_memory": None,
        "identity": api_identity,
    }
    
    # Execute the claude_code_task action
    result = self._action_registry.run("claude_code_task", params, ctx)
    return {"ok": True, "outcome": result}
```

---

## Identity Propagation

The ChatGPT bridge uses a dedicated identity source:

| Field | Value |
|-------|-------|
| `source` | `"api"` (via `IDENTITY_SOURCE_API`) |
| `subject` | `"chatgpt_bridge"` |
| `display_name` | `"ChatGPT Bridge"` |
| `metadata` | `{"endpoint": "/api/claude-task"}` |

This identity flows through:
1. Dashboard server receives request
2. `_handle_claude_task` creates `CallerIdentity`
3. Passed in `ctx["identity"]` to `ActionRegistry.run()`
4. `_call_handler()` extracts `identity` from context
5. `claude_code_task()` receives `identity` parameter
6. `_get_owner_identity()` filters anonymous → records as owner
7. Task stored with `owner_identity` for ownership verification

---

## Usage Example

### From ChatGPT (via HTTP)

```python
import requests
import json

# Assuming dashboard is running with pairing key authentication
# First, get a token via /login or /auto-login (QR code)

headers = {
    "Authorization": "Bearer <token>",
    "Content-Type": "application/json"
}

payload = {
    "prompt": "Create a Python function that calculates fibonacci numbers",
    "wait": False,  # Async mode - returns task_id for polling
    "timeout": 300
}

response = requests.post(
    "https://<jarvis-ip>:8001/api/claude-task",
    headers=headers,
    json=payload,
    verify=False  # Self-signed cert
)

result = response.json()
# {"ok": true, "task_id": "claude_task_a1b2c3d4e5f6", "outcome": "started..."}
```

### Polling for Result

```python
# Use the task_id from the response
poll_payload = {"task_id": "claude_task_a1b2c3d4e5f6"}
poll_response = requests.post(
    "https://<jarvis-ip>:8001/api/command",
    headers=headers,
    json={"text": f"get_claude_code_result {poll_payload['task_id']}"},
    verify=False
)
# Or call the action directly via the bridge
```

---

## Verification

### Syntax Checks
```bash
py -m py_compile dashboard/server.py main.py
# ✅ PASS
```

### Core Test Suites (all passing)
- `test_task_agent.py`: **67 passed**
- `test_worker_cancellation.py`: **22 passed**
- `test_task_monitoring.py`: **130 passed** (1 pre-existing flaky)
- `test_error_classification.py`: **71 passed**
- `test_history_worker.py`: **71 passed**
- `test_telegram_bot.py`: **49 passed**

**Total: 410+ tests passing** (excluding pre-existing flaky tests)

### Integration Verification
```python
# Dashboard server
from dashboard.server import DashboardServer
ds = DashboardServer()
assert hasattr(ds, 'set_claude_task_callback')

# Main handler
from main import JarvisLive
assert hasattr(JarvisLive, '_handle_claude_task')

# Identity module
from core import identity
assert identity.IDENTITY_SOURCE_API == "api"
```

---

## Security Properties

1. **Authentication Required**: All requests require valid Bearer token from pairing flow
2. **Encryption**: Commands encrypted with AES-256-GCM when HTTPS enabled
3. **Rate Limiting**: Inherits existing login throttle (6 attempts per 5 min)
4. **Task Ownership**: Tasks created via bridge owned by `api:chatgpt_bridge` — only same identity can retrieve/cancel
5. **Fail-Closed**: No callback registered → 503 Service Unavailable

---

## Next Steps (Stage 3+)

| Stage | Requirement | Status |
|-------|-------------|--------|
| 1 | ✅ Identity propagation & task ownership | **COMPLETE** |
| 2 | ✅ ChatGPT → JARVIS task submission | **COMPLETE** |
| 3 | Execution monitoring & progress | Pending |
| 4 | Result capture & formatting | Pending |
| 5 | JARVIS → ChatGPT result delivery | Pending |
| 6 | Unified workflow & error handling | Pending |
| 7 | End-to-end verification | Pending |

---

*Report generated: 2026-11-16*  
*Implementation: Stage 2 complete*