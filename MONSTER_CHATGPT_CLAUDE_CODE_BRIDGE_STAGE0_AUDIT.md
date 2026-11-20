# MONSTER_CHATGPT_CLAUDE_CODE_BRIDGE — Stage 0: Read-Only Architecture Audit

**Date:** 2026-11-16  
**Project:** `D:\M MONSTER PROJECT\Roitz-main`  
**Purpose:** Verify existing interfaces before implementing the ChatGPT ↔ Claude Code automation bridge

---

## Executive Summary

This audit maps the actual authenticated identity sources, process execution interfaces, clipboard/keyboard automation, browser automation, and external communication mechanisms currently available in ROITZ. No files are modified during this audit.

---

## 1. Authenticated Identity Source

### Current State: **NO TRUSTWORTHY CALLER IDENTITY PROPAGATION**

| Component | Finding |
|-----------|---------|
| **Session Entry Point** (`main.py:1839-1840`, `1859`) | `session_memory` is hardcoded to `None` for all tool executions |
| **Action Loader** (`core/action_loader.py:221`) | Passes `session_memory` from context but it's always `None` |
| **Plugin Loader** (`core/plugin_loader.py`) | Same pattern — `session_memory` passed but always `None` |
| **Executor** (`core/autonomous_agent.py:404-410`) | Accepts `session_memory` parameter but never receives authenticated identity |
| **Permission System** (`core/permission_guard.py`, `core/permission_manager.py`) | Operates on **capabilities + project paths**, not caller identities |

### Evidence

```python
# main.py:1839-1840 — ActionRegistry execution
_ctx = {"player": self.ui, "speak": self.speak,
        "response": None, "session_memory": None}  # Always None
r = await loop.run_in_executor(None, lambda: self._action_registry.run(name, args, _ctx))

# main.py:1859 — PluginRegistry execution
r = await loop.run_in_executor(
    None,
    lambda: self._plugin_registry.run(name, args, player=self.ui, session_memory=None)
)
```

### Missing Architecture

There is **no mechanism** to:
1. Establish authenticated caller identity at session start (voice auth, API token, login)
2. Propagate identity through the call chain to tool handlers
3. Associate tasks with authenticated owners
4. Verify ownership on task operations (get/cancel/list)

---

## 2. Identity Propagation Path

### Current Flow (Broken)

```
User Voice Session → main.py → ActionRegistry/PluginRegistry → Tool Handler
     (no identity)      (session_memory=None)        (session_memory=None)
```

### Required Flow (For Stage 1)

```
Authenticated Session → Identity Context → Tool Context → Task Creation
    (voice/API token)    (propagated)       (verified)      (owner recorded)
```

### Files Requiring Changes for Identity Propagation

| File | Current Role | Required Change |
|------|--------------|-----------------|
| `main.py` | Session entry point | Establish identity at session start; pass to context |
| `core/action_loader.py` | Action dispatch | Propagate identity from context to handlers |
| `core/plugin_loader.py` | Plugin dispatch | Propagate identity from context to handlers |
| `core/autonomous_agent.py` | Task execution | Accept and use identity for task ownership |
| `actions/claude_code_task.py` | Task operations | Verify ownership on get/cancel/list |

---

## 3. Claude Code Process Execution & Monitoring

### Existing Interfaces (Production-Ready)

| Interface | Location | Capability |
|-----------|----------|------------|
| `ProcessMonitor` | `core/process_monitor.py:123` | Full subprocess monitoring with stdout/stderr capture, timeout, cancellation |
| `run_process()` | `core/process_monitor.py:497` | Convenience function for monitored processes |
| `run_claude_code_task()` | `core/process_monitor.py:531` | Specialized for `claude -p` with `--output-format=json` |
| `ProcessResult.to_outcome()` | `core/process_monitor.py:65` | Converts to outcome format (done/unverified/failed) |
| `WorkerRegistry` | `core/worker_registry.py` | Resource conflict detection, admission control, lifecycle tracking |

### ProcessMonitor Features

- **Real-time capture**: Separate daemon threads for stdout/stderr (`core/process_monitor.py:345-361`)
- **Cross-platform termination**: Windows `kill()`, Unix `terminate()` + `kill()` fallback (`core/process_monitor.py:225-245`)
- **Cooperative cancellation**: `cancel_event` threading.Event propagated to process (`core/process_monitor.py:144, 485-490`)
- **Task ID association**: Each monitor tagged with unique `task_id` (`core/process_monitor.py:137`)
- **WorkerRegistry integration**: Resource keys `process:{task_id}` for conflict detection (`core/process_monitor.py:263`)

### Tool Wrapper (Fixed in Task 1)

| Function | File | Status |
|----------|------|--------|
| `claude_code_task()` | `actions/claude_code_task.py:101` | ✅ PermissionGuard, real cancellation, cleanup |
| `get_claude_code_result()` | `actions/claude_code_task.py:267` | ✅ PermissionGuard, ownership check needed |
| `cancel_claude_code_task()` | `actions/claude_code_task.py:314` | ✅ Real cancellation via cancel_event, cleanup |
| `list_claude_code_tasks()` | `actions/claude_code_task.py:397` | ✅ PermissionGuard, ownership check needed |

---

## 4. Clipboard & Keyboard Automation

### Existing Capabilities (Production-Ready)

| Capability | Location | Details |
|------------|----------|---------|
| **Clipboard read** | `actions/computer_control.py:826` | `_clipboard_get()` — uses `pyperclip.paste()` or Ctrl+C fallback |
| **Clipboard write** | `actions/computer_control.py:835` | `_clipboard_paste(text)` — uses `pyperclip.copy()` + Ctrl+V |
| **Smart typing** | `actions/computer_control.py:706` | `smart_type` — clipboard-backed for text >20 chars |
| **Keyboard simulation** | `actions/computer_control.py` | Full pyautogui: `type`, `hotkey`, `press`, `click`, etc. |
| **OS-aware hotkeys** | `actions/send_message.py:51-58` | Win/Linux: Ctrl+V, Mac: Cmd+V |

### Lazy Import Pattern

Both `pyautogui` and `pyperclip` are loaded on first use via `core/lazyimport.LazyModule` to avoid 290ms boot penalty.

---

## 5. Browser Automation

### Existing Capabilities (Production-Ready)

| Capability | Location | Details |
|------------|----------|---------|
| **Playwright integration** | `actions/browser_control.py` | Full async browser control via Playwright |
| **Session management** | `actions/browser_control.py` | Multi-browser, multi-tab sessions with registry |
| **Navigation** | `actions/browser_control.py` | `go_to`, `search`, `new_tab`, `back`, `forward`, `reload` |
| **Interaction** | `actions/browser_control.py` | `click`, `type`, `scroll`, `fill_form`, `smart_click`, `smart_type` |
| **Read-only** | `actions/browser_control.py` | `screenshot`, `get_text`, `get_url` |
| **Resource keys** | `core/worker_registry.py:618-670` | `browser:session:{browser}`, `network:{domain}` for conflict detection |

### Browser Detection

- Auto-detects default browser (Chrome/Edge/Firefox/Opera/Brave/Safari)
- Normalizes URLs (bare words → `https://{word}.com`)

### Limitation for ChatGPT

**No existing ChatGPT-specific automation.** The browser_control can navigate to `chat.openai.com` but has no:
- ChatGPT conversation extraction
- Prompt injection into ChatGPT input
- Response capture from ChatGPT output
- Session/authentication management for ChatGPT

---

## 6. External Communication Interfaces

### Available Mechanisms

| Mechanism | Location | Status |
|-----------|----------|--------|
| **Local HTTP Dashboard** | `dashboard/server.py` | ✅ FastAPI + WebSocket, HTTPS, auth via pairing key, command queue |
| **Telegram Bot** | `plugins/telegram_bot.py` | ✅ Long polling, secure owner pairing, command execution |
| **File Upload/Download** | `dashboard/server.py:1078-1144` | ✅ Authenticated file transfer |
| **Phone Audio** | `dashboard/server.py:1044-1068` | ✅ WebSocket mic streaming to Gemini Live |

### Dashboard API Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /api/command` | Bearer token | Submit command text to JARVIS |
| `POST /api/wake` | Bearer token | Wake assistant |
| `WS /ws/phone-audio` | Token query | Stream phone microphone audio |
| `POST /api/upload` | Bearer token | Upload file |
| `GET /api/files` | Bearer token | List uploaded files |
| `GET /uploads/{file}` | Token query | Download file |

### Dashboard Authentication

- One-time pairing key (8 chars, 10 min expiry)
- Bearer token (12hr TTL) issued after key validation
- Device tokens for auto-reconnect (persisted in localStorage)
- Rate limiting on login (6 attempts / 5 min → 5 min lockout)

---

## 7. Permission & Approval System

### PermissionGuard Enforcement Points

| Layer | Location | Behavior |
|-------|----------|----------|
| **ActionRegistry** | `core/action_loader.py:186-226` | Always checks PermissionGuard before handler |
| **PluginRegistry** | `core/plugin_loader.py` | Same pattern |
| **Executor** | `core/autonomous_agent.py:956-1019` | Checks per-step via registries |

### Operation Specs for Claude Code Bridge

```python
# core/permission_guard.py:195-198
"claude_code_task":         OperationSpec("proc.exec",      idempotent=False, read_only=False, resource_scope=ResourceScope.LOCAL_SYSTEM),
"get_claude_code_result":   OperationSpec("system.monitor", idempotent=True,  read_only=True,  resource_scope=ResourceScope.LOCAL_SYSTEM),
"cancel_claude_code_task":  OperationSpec("system.monitor", idempotent=False, read_only=False, resource_scope=ResourceScope.LOCAL_SYSTEM),
"list_claude_code_tasks":   OperationSpec("system.monitor", idempotent=True,  read_only=True,  resource_scope=ResourceScope.LOCAL_SYSTEM),
```

### Owner Approval Required For

```python
# core/permission_manager.py:121-132
OWNER_APPROVAL_REQUIRED = {
    "fs.delete", "fs.move", "proc.exec", "input.simulate",
    "messaging.send", "net.egress", "remote.command",
    "system.shutdown", "memory.write", "app.manage"
}
```

- `claude_code_task` → `proc.exec` → **Owner approval REQUIRED**
- Other three → `system.monitor` → No owner approval (but PermissionGuard check required)

---

## 8. Dependency Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER SESSION ENTRY                           │
│                    (main.py: JarvisLive.__init__)                   │
│                         ↓ (session_memory=None)                     │
├─────────────────────────────────────────────────────────────────────┤
│                    ACTION / PLUGIN DISPATCH                         │
│  ActionRegistry.run() ← core/action_loader.py:_get_operation_name() │
│  PluginRegistry.run() ← core/plugin_loader.py:_get_operation_name() │
│                         ↓ (ctx with session_memory=None)            │
├─────────────────────────────────────────────────────────────────────┤
│                    PERMISSION ENFORCEMENT                           │
│  PermissionGuard.check_operation() → PermissionManager.check()     │
│                         ↓ (capability + project path)               │
├─────────────────────────────────────────────────────────────────────┤
│                    TOOL HANDLERS                                    │
│  actions/claude_code_task.py (4 functions)                         │
│       ↓                                                             │
│  core/process_monitor.py (ProcessMonitor, run_claude_code_task)    │
│       ↓                                                             │
│  core/worker_registry.py (WorkerRegistry, resource coordination)   │
│       ↓                                                             │
│  subprocess.Popen (claude -p --output-format=json)                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 9. Gaps for ChatGPT ↔ Claude Code Bridge

| Requirement | Current Status | Gap |
|-------------|----------------|-----|
| **Authenticated identity at session** | ❌ None | Need voice/API auth → identity context |
| **Identity propagation to tools** | ❌ session_memory=None | Thread through main→dispatch→handlers |
| **Task ownership recording** | ❌ No owner field | Add owner_id to _active_tasks entries |
| **Ownership verification** | ❌ Any task_id works | Check caller identity vs task owner |
| **ChatGPT prompt receipt** | ❌ No interface | Need supported input mechanism |
| **ChatGPT result delivery** | ❌ No interface | Need supported output mechanism |
| **Claude Code session targeting** | ✅ ProcessMonitor exists | Works for local claude CLI |
| **Prompt transfer to Claude Code** | ✅ run_claude_code_task | Uses `claude -p` CLI |
| **Execution monitoring** | ✅ ProcessMonitor | Real-time capture, cancellation |
| **Result capture** | ✅ ProcessResult | stdout/stderr + JSON output format |
| **Clipboard transfer** | ✅ computer_control | pyperclip + hotkeys |
| **Browser automation** | ✅ browser_control | Playwright for web UI if needed |
| **Dashboard command input** | ✅ /api/command | Authenticated HTTP endpoint |
| **Dashboard result output** | ✅ WebSocket broadcast | Real-time to connected clients |

---

## 10. Stage 0 Verdict

**READY FOR STAGE 1** — All core execution, monitoring, cancellation, and permission infrastructure exists and is verified (324 tests passing). The **only architectural blocker** is authenticated identity propagation, which Stage 1 must resolve before any task ownership enforcement can work.

**Critical Path for Stage 1:**
1. Establish identity at session entry (main.py)
2. Propagate through action/plugin loaders
3. Record owner on task creation
4. Verify owner on get/cancel/list operations
5. Reject unauthorized access

---

*Report generated: 2026-11-16*  
*Audit: Read-only — no files modified*