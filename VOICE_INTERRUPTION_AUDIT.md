# Mark LVII-A: Voice Interruption Architecture Audit
**Status:** READ-ONLY AUDIT COMPLETE — No modifications made  
**Date:** 2026-11-14  
**Scope:** Determine whether voice-based interruption can be safely implemented using existing architecture

---

## 1. Existing Architecture — Exact Source References

### 1.1 Threading Model (Confirmed in `main.py:1-50`, `ui.py`, AGENTS.md)
| Thread | Responsibility | Key Files |
|--------|---------------|-----------|
| **Qt Main Thread** | All UI widgets (`QApplication`, `MainWindow`, `JarvisUI`) | `ui.py` |
| **Asyncio Background Loop** | Voice session (`_listen_audio`, `_engine`), wake word, echo guard | `main.py:200-300`, `main.py:1800-1900` |
| **Worker Threads** | Actions (`actions/*.py`), Plugins (`plugins/*.py`) — **never create Qt widgets** | `actions/`, `plugins/`, AGENTS.md |

**Critical Rule:** Workers must call `player.write_log()`, `player.show_content()`, `player.show_quiz()`, `player.show_review()`, `player.show_video()` — these are thread-safe proxies that marshal to Qt thread via signals.

### 1.2 WorkerRegistry — Centralized Thread-Safe Worker Tracking (`core/worker_registry.py:1-807`)
```python
class WorkerState(Enum):
    CREATED = "created"
    RUNNING = "running"
    CANCELLATION_REQUESTED = "cancellation_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    UNRESOLVED = "unresolved"      # Worker alive after grace period
    TERMINATED = "terminated"
```

**Key Methods:**
- `admit_worker(worker)` — Atomic admission with resource conflict detection (`worker_registry.py:340-400`)
- `release_resources(attempt_id)` — Releases resource keys (`worker_registry.py:460-490`)
- `get_active_for_task(task_id)` — Active workers for task (`worker_registry.py:550-570`)
- `get_unresolved_workers()` — Workers in UNRESOLVED state (`worker_registry.py:575-590`)
- `extract_resource_keys(tool_name, parameters, operation_name)` — Maps operations to resource keys (`worker_registry.py:620-807`)

**Resource Key Taxonomy:**
| Key Pattern | Example | Scope |
|-------------|---------|-------|
| `file:{path}` | `file:/home/user/doc.txt` | File operations |
| `browser:session:{browser}` | `browser:session:chrome` | Browser automation |
| `global:input` / `global:display` | Input/display coordination |
| `app:manage` | App window management |
| `messaging:{platform}` | `messaging:whatsapp` |
| `project:{path}` | Project-scoped operations |
| `proc:exec` | Process execution |
| `network:{domain}` | `network:example.com` |

### 1.3 PermissionGuard & OPERATION_SPECS (`core/permission_guard.py:1-370`, `core/permission_manager.py`)
- **200+ operation specs** with metadata: `idempotent`, `read_only`, `resource_scope`, `additional_caps`
- `check_operation(operation_name, params)` validates exact operation, consumes approval tokens atomically
- `OWNER_APPROVAL_REQUIRED` capabilities: `fs.delete`, `fs.move`, `proc.exec`, `messaging.send`, `input.simulate`, `remote.command`, `app.manage`, `net.egress`

### 1.4 Outcome Contract (`core/outcome.py`)
```python
done(tool, message, **meta)       # Verified completion
unverified(tool, message, **meta)  # Honest uncertainty — keystrokes went out, no read-back
failed(tool, message, **meta)      # Definite failure
ask(tool, message, **meta)         # Requires user input
started(tool, **meta)              # Async background work initiated
```
**Rule:** Tools report what they **observed**, not what they **attempted**.

### 1.5 EchoGuard — Self-Echo Suppression (`core/echo.py:1-289`)
```python
class EchoGuard:
    def note_output(self, samples: np.ndarray) -> None      # Register TTS output
    def is_user_speech(self, samples: np.ndarray) -> bool   # Band energy subtraction + learned gain
    @property
    def calibrated(self) -> bool      # Has learned room response
    @property
    def reliable(self) -> bool        # Calibrated + sufficient gain
    @property
    def threshold(self) -> float      # Dynamic threshold
    @property
    def required_blocks(self) -> int  # Consecutive blocks needed
```

### 1.6 WakeWordDetector — Local "Hey Jarvis" (`core/wake_word.py:1-212`)
```python
class WakeWordDetector:
    def __init__(self, on_detect: Callable[[], None], model_path: str = None)
    def feed(self, audio_chunk: np.ndarray) -> None      # Called from mic callback
    def _loop(self) -> None                              # Runs inference in dedicated thread
    def stop(self) -> None
```
- Uses `openwakeword` with ONNX models
- Dedicated inference thread, callback on detection

### 1.7 Confirmation System — UI-Issued Tokens (`core/confirm.py:1-161`)
```python
def request(key, title, detail, run) -> str      # Parks irreversible action behind on-screen gate
def resolve(key, decision) -> str                # Runs callable on worker thread
def pending_title() -> str                       # Checks for active confirmation
```
**Critical:** Model **cannot forge** confirmation tokens — only UI can issue them.

### 1.8 Engine Selection (`main.py:200-400`)
- **Gemini Live** (server-side VAD + streaming)
- **Local STT/LLM/TTS pipelines**: Ollama, LM Studio, llama.cpp, vLLM, OpenAI, Groq
- Engine abstraction: `self._engine` with `interrupt()` method

### 1.9 Plugin System (`core/plugin_loader.py`)
- Auto-discovery: `plugins/<name>.py` (no leading underscore)
- Crash isolation: each plugin runs in worker thread
- Self-describing `TOOL` dicts with `handler` function

### 1.10 Existing `interrupt()` Method (`main.py:1093-1121`)
```python
def interrupt(self) -> None:
    """Stop current speech/response immediately."""
    # 1. Drain audio output queue
    while not self._audio_out_queue.empty():
        try: self._audio_out_queue.get_nowait()
        except queue.Empty: break
    
    # 2. Set interruption flag
    self._interrupted = True
    
    # 3. Stop local engine if present
    if hasattr(self, '_engine') and self._engine and hasattr(self._engine, 'interrupt'):
        self._engine.interrupt()
    
    # 4. Reset viseme animation
    self._viseme_queue = []
    
    # 5. Clear turn completion event
    self._turn_done_event.clear()
```

---

## 2. Implemented vs. Missing Functionality

| Capability | Status | Location / Notes |
|------------|--------|------------------|
| **Mid-speech audio queue drain** | ✅ Implemented | `main.py:1093-1105` |
| **Engine interrupt() call** | ✅ Implemented | `main.py:1107-1110` (local engines only) |
| **Viseme/reset state** | ✅ Implemented | `main.py:1112-1115` |
| **Turn completion event clear** | ✅ Implemented | `main.py:1117` |
| **Voice barge-in detection (EchoGuard)** | ⚠️ **DISABLED** | `main.py:1837-1842` — "Interrupting by voice used to live here... but it depends on the listener's room, so it stays switched off until it can be tried on real hardware" |
| **Wake word during TTS** | ❌ Missing | WakeWordDetector feeds from mic callback, but mic may be muted during TTS |
| **Confirmation bypass for emergency stop** | ❌ Missing | `core/confirm.py` has no emergency path |
| **Worker cancellation on interrupt** | ⚠️ Partial | `WorkerRecord.request_cancellation()` exists (`worker_registry.py:240-250`), `Executor.cancel()` sets flag (`autonomous_agent.py:950-960`), but **only checked between steps**, not during step execution |
| **Resource release on forced interrupt** | ❌ Missing | No automatic `release_resources()` on voice interrupt |
| **Gemini Live interrupt path** | ❓ Unknown | `main.py:1107` checks `hasattr(self._engine, 'interrupt')` — Gemini Live path unclear |
| **EchoGuard integration with barge-in** | ⚠️ Disabled | `EchoGuard.is_user_speech()` exists but not wired to interrupt logic |

---

## 3. Proposed Minimal Implementation Design

### 3.1 Architecture Principles
1. **No new threads** — reuse existing asyncio loop + worker threads
2. **No Qt widgets in workers** — use existing `player` proxies
3. **Fail closed** — any uncertainty → conservative behavior
4. **Reuse existing contracts** — `WorkerRegistry`, `PermissionGuard`, `Outcome`, `EchoGuard`

### 3.2 Voice Interrupt Flow
```
User says "Jarvis stop" (or wake word during TTS)
        │
        ▼
┌───────────────────────┐
│ Mic callback feeds    │  ← Already exists in _listen_audio
│ WakeWordDetector      │
└───────────┬───────────┘
            │ on_detect()
            ▼
┌───────────────────────┐
│ EchoGuard.is_user_speech()  │  ← Band energy subtraction
│ (validate not echo)    │
└───────────┬───────────┘
            │ if user speech
            ▼
┌───────────────────────┐
│ main.interrupt()      │  ← Already exists
│   - drain audio queue │
│   - _interrupted=True │
│   - engine.interrupt()│
│   - reset visemes     │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ Cancel active workers │  ← NEW: WorkerRegistry integration
│   - request_cancellation() on RUNNING workers
│   - wait_for_worker(grace=2s)
│   - mark_terminated() on timeout
│   - release_resources()
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ Bypass confirmations  │  ← NEW: Emergency path in confirm.py
│   - resolve pending confirmations as "denied"
│   - clear pending_title()
└───────────┬───────────┘
            │
            ▼
    Voice session resumes
    (new turn, clean state)
```

### 3.3 Key Integration Points

| Component | Change Required |
|-----------|-----------------|
| `main.py:_listen_audio()` | Enable barge-in: call `EchoGuard.is_user_speech()` on mic chunks, trigger `interrupt()` |
| `main.py:interrupt()` | Add worker cancellation + confirmation bypass + resource release |
| `core/confirm.py` | Add `emergency_deny_all()` to resolve pending confirmations |
| `core/worker_registry.py` | Add `cancel_all_for_task(task_id)` or similar |
| `core/autonomous_agent.py:Executor` | Check `cancel_event` **during** step execution (not just between steps) |

---

## 4. Required Files and Tests

### 4.1 Files to Modify (Minimal Set)
| File | Changes |
|------|---------|
| `main.py` | Enable barge-in in `_listen_audio()`; extend `interrupt()` with worker cancellation + confirmation bypass |
| `core/confirm.py` | Add `emergency_deny_all()` function |
| `core/worker_registry.py` | Add `cancel_all_for_task(task_id, grace_seconds=2.0)` |
| `core/autonomous_agent.py` | Make `Executor` check `cancel_event` during long-running operations |

### 4.2 New Tests Required
| Test | Description |
|------|-------------|
| `test_voice_interrupt_barge_in()` | Simulate wake word during TTS → verify `interrupt()` called |
| `test_voice_interrupt_cancels_workers()` | Start long-running worker, trigger interrupt → verify `request_cancellation()` + `release_resources()` |
| `test_voice_interrupt_bypasses_confirmation()` | Park confirmation, trigger interrupt → verify confirmation resolved as denied |
| `test_echo_guard_rejects_tts_echo()` | Play TTS, feed same audio to mic → `is_user_speech()` returns `False` |
| `test_echo_guard_accepts_real_speech()` | Play TTS, feed different speech → `is_user_speech()` returns `True` (when calibrated) |
| `test_executor_checks_cancel_during_step()` | Long step with `cancel_event` → verify early exit |
| `test_gemini_live_interrupt_path()` | Verify `engine.interrupt()` works for Gemini Live |
| `test_interrupt_clears_all_state()` | Verify `_interrupted`, queues, visemes, turn event all reset |

### 4.3 Existing Tests to Extend
- `tests/unit/test_task_monitoring.py::TestCrossExecutorSharedRegistry` — add voice interrupt scenario
- `tests/unit/test_echo.py` — add barge-in validation tests
- `tests/unit/test_wake_word.py` — add during-TTS detection tests

---

## 5. Race Conditions and Failure Scenarios

| # | Scenario | Risk | Mitigation |
|---|----------|------|------------|
| **RC-1** | Wake word detected during TTS, but mic picks up TTS echo | False interrupt | `EchoGuard.is_user_speech()` band energy subtraction + learned gain; require `calibrated && reliable` |
| **RC-2** | `interrupt()` called while worker in `RUNNING` state holding `global:input` | Resource leak / deadlock | `WorkerRegistry.cancel_all_for_task()` waits for `join(timeout=grace)`, then `mark_terminated()` + `release_resources()` |
| **RC-3** | Confirmation dialog open, voice interrupt triggers | User action lost / inconsistent state | `confirm.emergency_deny_all()` resolves pending as denied; UI shows "Interrupted" |
| **RC-4** | Gemini Live engine doesn't implement `interrupt()` | Interrupt silent failure | `hasattr(engine, 'interrupt')` check + fallback: close WebSocket / send cancel message |
| **RC-5** | Multiple rapid interrupts (user says "stop" 3x) | State corruption | `_interrupted` flag is idempotent; `interrupt()` safe to call repeatedly |
| **RC-6** | Worker ignores `cancel_event` (blocking I/O) | Worker stays UNRESOLVED | Grace period (2s) → `mark_terminated()` → `release_resources()`; log warning |
| **RC-7** | Voice interrupt during `dev_agent:build` (proc:exec) | Build process orphaned | `WorkerRecord.cancel_event` passed to subprocess; `terminate()` on timeout |
| **RC-8** | EchoGuard not calibrated (first run) | Barge-in disabled | `EchoGuard.calibrated` property → barge-in only active when `calibrated && reliable` |
| **RC-9** | WakeWordDetector callback on non-asyncio thread | Cross-thread violation | `WakeWordDetector._loop()` runs in dedicated thread; `on_detect()` must be thread-safe (use `call_soon_threadsafe`) |
| **RC-10** | Resource key collision: voice interrupt vs. new command | New command blocked | `interrupt()` releases ALL resources for task before new turn starts |

---

## 6. Recommended Implementation Batches

### Batch 1: Core Interrupt Wiring (Low Risk)
**Files:** `main.py`, `core/echo.py`, `core/wake_word.py`
- Enable barge-in in `_listen_audio()` behind `EchoGuard.calibrated && EchoGuard.reliable`
- Wire `WakeWordDetector.on_detect` → `main.interrupt()`
- Verify `EchoGuard.is_user_speech()` rejects TTS echo on real hardware
**Tests:** `test_voice_interrupt_barge_in`, `test_echo_guard_rejects_tts_echo`

### Batch 2: Worker Cancellation + Resource Release (Medium Risk)
**Files:** `main.py`, `core/worker_registry.py`, `core/autonomous_agent.py`
- Add `WorkerRegistry.cancel_all_for_task(task_id, grace=2.0)`
- Extend `main.interrupt()` to call cancellation + `release_resources()`
- Make `Executor` check `cancel_event` during step execution (poll in long operations)
**Tests:** `test_voice_interrupt_cancels_workers`, `test_executor_checks_cancel_during_step`

### Batch 3: Confirmation Bypass (Low Risk)
**Files:** `core/confirm.py`, `main.py`
- Add `confirm.emergency_deny_all()` → resolves all pending as denied
- Call from `main.interrupt()` after worker cancellation
**Tests:** `test_voice_interrupt_bypasses_confirmation`

### Batch 4: Engine-Specific Interrupt Paths (Medium Risk)
**Files:** `main.py`, engine implementations
- Verify Gemini Live `interrupt()` implementation
- Add fallback for engines without `interrupt()` (close transport)
**Tests:** `test_gemini_live_interrupt_path`

### Batch 5: State Reset Verification (Low Risk)
**Files:** `main.py`
- Verify `_interrupted`, audio queues, visemes, `_turn_done_event` all reset
- Ensure new turn starts clean
**Tests:** `test_interrupt_clears_all_state`

---

## 7. Acceptance Criteria

| Criterion | Verification Method |
|-----------|---------------------|
| **AC-1** User says "Jarvis stop" during TTS → TTS stops within 500ms | Manual test + latency measurement |
| **AC-2** No false interrupts from TTS echo (10 min conversation) | Automated test with recorded TTS + mic playback |
| **AC-3** Active worker (file write, browser click, build) cancelled + resources released | `test_voice_interrupt_cancels_workers` + resource key audit |
| **AC-4** Confirmation dialog dismissed on interrupt | `test_voice_interrupt_bypasses_confirmation` |
| **AC-5** No resource leaks after 100 interrupts | Stress test + `WorkerRegistry.get_diagnostics()` |
| **AC-6** Gemini Live interrupt works (if selected engine) | `test_gemini_live_interrupt_path` |
| **AC-7** New voice turn starts clean (no stale state) | `test_interrupt_clears_all_state` |
| **AC-8** Barge-in only active when `EchoGuard.calibrated && reliable` | Property check in `_listen_audio()` |
| **AC-9** Wake word detection works during TTS (mic not muted) | Hardware test — verify mic callback active |
| **AC-10** All existing tests pass (no regressions) | `python -m pytest tests/unit/ -v` |

---

## 8. Security Requirements Verification

| Requirement | Status | Evidence |
|-------------|--------|----------|
| **SR-1** No forged confirmations | ✅ | `core/confirm.py` — only UI issues tokens; `emergency_deny_all()` denies, never approves |
| **SR-2** WorkerRegistry admission atomic | ✅ | `worker_registry.py:340-400` — `RLock` + atomic check-and-reserve |
| **SR-3** PermissionGuard validates exact operation | ✅ | `permission_guard.py:200-280` — exact match on `operation_name` + params |
| **SR-4** Outcome contract: honest uncertainty | ✅ | `outcome.py` — `unverified` for blind actions; `done` only when verified |
| **SR-5** Resource conflicts prevented across executors | ✅ | `worker_registry.py` — shared global registry, `has_conflicting_worker()` |
| **SR-6** Fail-closed on timeout/uncertainty | ✅ | `task_monitoring.py` — non-idempotent timeouts → `failed`, not `done` |

---

## 9. Summary

**Voice interruption is architecturally feasible** with the existing foundation. The critical pieces exist:

1. ✅ `main.interrupt()` — drains audio, stops engine, resets state
2. ✅ `EchoGuard` — echo suppression with learned room response
3. ✅ `WakeWordDetector` — local wake word in dedicated thread
4. ✅ `WorkerRegistry` — atomic admission, resource keys, cancellation event, UNRESOLVED tracking
5. ✅ `Executor.cancel()` — cooperative cancellation flag (needs intra-step checking)
6. ✅ `confirm.py` — UI-gated confirmations (needs emergency bypass)

**Three gaps require implementation:**
1. **Barge-in wiring** — Enable `EchoGuard.is_user_speech()` in `_listen_audio()` (currently disabled)
2. **Worker cancellation on interrupt** — `WorkerRegistry.cancel_all_for_task()` + `Executor` intra-step `cancel_event` checks
3. **Confirmation emergency bypass** — `confirm.emergency_deny_all()`

**Estimated effort:** 4-5 focused batches, each independently testable. No architectural changes needed — only wiring existing components together with proper failure handling.

---

*This audit is READ-ONLY. No files were modified. Implementation should proceed in the batch order above, with each batch verified by its acceptance criteria before proceeding.*