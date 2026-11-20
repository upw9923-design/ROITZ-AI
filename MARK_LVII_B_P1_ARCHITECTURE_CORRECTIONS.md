# MARK LVII-B P1 — Architecture Corrections Audit

**Auditor**: Principal Software Architect & Security Reviewer (read-only)  
**Scope**: Targeted corrections to the Conversation History UI Readiness Audit  
**Method**: Source code inspection, line-by-line verification, no modifications  
**Date**: 2026-11-15

---

## Executive Summary

The initial readiness audit correctly identified that the data layer is complete, but **four critical architectural gaps** must be resolved before implementation:

| Gap | Severity | Resolution |
|-----|----------|------------|
| **WorkerRegistry misuse** | High | History operations are read-only UI fetchers — do NOT use WorkerRegistry admission. Use `asyncio.to_thread()` pattern directly. |
| **Stale response protection** | High | Adopt existing `_generation` counter pattern (`main.py:602,1114`) for list/detail/search request IDs. |
| **Content panel replacement risk** | High | Content panel serves 4 features (search, news, code agent, review). Must add **separate history panel**, not replace. |
| **Search API gaps** | Medium | `search_messages` returns flat list — no grouping, no total count. Need `count_search_messages` and grouped results. |

**Revised Verdict**: **READY FOR IMPLEMENTATION WITH CORRECTIONS** — All blockers have documented resolutions. No fundamental architecture changes needed.

---

## 1. WorkerRegistry Integration — Corrected Approach

### 1.1 Current WorkerRegistry Purpose (Verified)

`core/worker_registry.py` is designed for **tool execution with resource conflict detection**:

- Tracks workers that **mutate state** (file writes, input simulation, network egress)
- Admission control prevents concurrent access to same resources
- Used by `_run_with_worker_registry` (`main.py:1455-1518`) for inline tools
- Resource keys: `global:input`, `global:display`, `project:...`, `network:...`, `app:manage`, etc.

### 1.2 History Operations Are Fundamentally Different

| Aspect | Tool Workers | History UI Fetchers |
|--------|--------------|---------------------|
| **Mutates state** | Yes (writes, clicks, API calls) | No (read-only SELECT queries) |
| **Resource conflicts** | Yes (exclusive access needed) | No (SQLite WAL allows concurrent readers) |
| **PermissionGuard** | Required (capabilities, approval tokens) | Read-only — like `recall_memory` (`permission_guard.py:175`) |
| **Cancellation** | Cooperative via `cancel_event` | Not needed — fast queries, user can re-request |
| **Lifecycle** | Long-running (seconds-minutes) | Short-lived (milliseconds) |

### 1.3 Correct Execution Pattern for History

**Use the existing `asyncio.to_thread()` pattern directly**, as used throughout `main.py` for memory operations:

```python
# Verified pattern from main.py:2460, 2554, 2666, 3244
memory = await asyncio.to_thread(load_memory)
summary = await asyncio.to_thread(gemini.text, prompt, tier=gemini.SMART)
```

**For history operations:**

```python
# In actions/history.py or similar
async def load_history_list(player, offset=0, limit=50, generation=0):
    def _worker():
        try:
            store = get_store()  # Thread-local store (conversation_store.py:782)
            conversations = store.list_conversations(limit=limit, offset=offset)
            total = store.count_conversations()
            # Convert to serializable dicts for signal transport
            data = [dataclasses.asdict(cs) for cs in conversations]
            # CRITICAL: Include generation for stale response protection
            player.show_history_list(data, offset, total, generation)
        except Exception as e:
            player.show_history_error(str(e), generation)
    
    # Run in thread pool — no WorkerRegistry admission needed
    await asyncio.to_thread(_worker)
```

**Key differences from `_run_with_worker_registry`:**
- No `WorkerRecord` creation
- No `admit_worker()` / `release_resources()`
- No `cancel_event` (queries are fast; user action supersedes)
- No `PermissionGuard` check (read-only, like `recall_memory`)
- Generation counter passed through for stale response protection

### 1.4 Verified: No WorkerRegistry Changes Needed

The existing `WorkerRegistry` requires **zero modifications**. History operations simply don't use it — they follow the simpler `asyncio.to_thread()` pattern already established for memory operations.

---

## 2. Stale Response Protection — Generation Counter Design

### 2.1 Existing Pattern (Verified in `main.py`)

The codebase already uses a generation counter for **audio interrupt isolation**:

```python
# main.py:602-604
self._generation = 0  # Incremented on each interrupt

# main.py:1113-1115
self._generation += 1
current_generation = self._generation

# main.py:2329, 2334-2336
if chunk_gen != self._generation:
    # Discard late chunks from interrupted generation
    continue
```

### 2.2 Applied to History Operations

**Add a dedicated `_history_generation` counter to `JarvisLive` (main.py):**

```python
# In JarvisLive.__init__ (around line 668)
self._history_generation = 0
```

**Increment on each new user-initiated request:**

| Operation | When to Increment |
|-----------|-------------------|
| Open history panel (list load) | User clicks history button / hotkey |
| Conversation selection (detail load) | User clicks different conversation |
| Search query | Debounced search input (new query) |
| Pagination (next/prev page) | **Do NOT increment** — same logical request |

**Worker carries generation; UI discards stale results:**

```python
# Worker side
async def load_history_detail(player, conversation_id, offset, limit, generation):
    def _worker():
        store = get_store()
        messages = store.get_messages(conversation_id, limit=limit, offset=offset)
        total = store.get_message_count(conversation_id)
        data = [dataclasses.asdict(m) for m in messages]
        player.show_history_detail(conversation_id, data, offset, total, generation)
    await asyncio.to_thread(_worker)

# UI slot side (Qt thread)
@pyqtSlot(str, list, int, int, int)
def _on_history_detail(self, conversation_id, messages, offset, total, generation):
    if generation != self._history_generation:
        return  # STALE — discard
    # Update detail view...
```

### 2.3 Rapid Interaction Handling

| Scenario | Behavior |
|----------|----------|
| User clicks conv A → quickly clicks conv B | Gen increments on B click; A's detail result discarded |
| User types search → backspace → new query | Debounce (300ms) ensures only final query fires; gen increments per debounced fire |
| User clicks "Next page" | Same generation — result applied normally |
| Panel dismissed during load | Generation not incremented, but UI slot checks panel visibility before applying |

---

## 3. Search Result Architecture — Verified API Gaps

### 3.1 Actual `search_messages` Implementation (`conversation_store.py:575-629`)

```python
def search_messages(
    self,
    query: str,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> List[Message]:
    # Returns flat list of Message objects
    # Ordered by timestamp_ms DESC (newest first)
    # NO conversation grouping
    # NO total count
    # NO snippet/highlight
```

**Verified gaps:**
1. **No total count** — Cannot compute total pages for pagination
2. **No conversation grouping** — Results are flat, mixed across conversations
3. **No snippet** — Full message content returned; UI must truncate
4. **No highlight** — No match position info for bolding

### 3.2 Required Store Extensions (Minimal)

**Add to `ConversationStore`:**

```python
def count_search_messages(
    self,
    query: str,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
) -> int:
    """Return total matching messages for pagination."""
    if not query or not query.strip():
        return 0
    like_pattern = f"%{query.strip()}%"
    conditions = ["content LIKE ?"]
    params = [like_pattern]
    if conversation_id:
        conditions.append("conversation_id = ?")
        params.append(conversation_id)
    if role:
        conditions.append("role = ?")
        params.append(role)
    with self._lock:
        conn = self._get_connection()
        row = conn.execute(
            f"SELECT COUNT(*) FROM messages WHERE {' AND '.join(conditions)}",
            params,
        ).fetchone()
    return row[0] if row else 0

def search_messages_grouped(
    self,
    query: str,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    snippet_chars: int = 120,
) -> List[dict]:
    """
    Search messages grouped by conversation with snippets.
    Returns: [{conversation_id, conversation_title, messages: [...snippet...]}]
    """
    # Implementation: fetch flat results, group by conversation_id in Python
    # Add snippet: message.content[:snippet_chars] + "..." if longer
```

**Note**: Grouping in Python is acceptable for <10K results. For larger datasets, FTS5 with `bm25()` ranking would be needed (Phase 2).

### 3.3 Search Pagination Design

| Parameter | Value |
|-----------|-------|
| Page size | 20 results (configurable) |
| Total pages | `ceil(count_search_messages / page_size)` |
| Grouping | By conversation, newest conversation first |
| Within conversation | Newest messages first (timestamp DESC) |

---

## 4. Existing UI Compatibility — Content Panel Callsites

### 4.1 Verified Callsites (Read-Only Inspection)

| Feature | Location | Signal/Method | Content Type |
|---------|----------|---------------|--------------|
| **Search tool results** | `main.py:1848` | `self.ui.show_content()` | Search results text |
| **News briefing** | `main.py:2528` | `self.ui.show_content()` | News headlines |
| **Code agent progress** | `ui.py:6093` `_show_code_job` | `_codejob_sig` → slot | HTML-rendered job status |
| **Document review** | `ui.py:6185` `_show_review` | `_review_sig` → slot | HTML-rendered findings |

### 4.2 Content Panel Current Architecture

```
_content_panel (QWidget, hidden by default)
  ├── Header: title + timestamp + dismiss button
  └── _content_display (QTextEdit, read-only, HTML-capable)
```

**Shared by 4 independent features** — replacing it would break all.

### 4.3 Correct Approach: Separate History Panel

**Option A: New Panel in `_center_split` (Recommended)**

```python
# ui.py MainWindow.__init__ (around line 4718)
self._center_split = QSplitter(Qt.Orientation.Vertical)
self._center_split.addWidget(self._hud_cam_stack)      # stretch=3
self._center_split.addWidget(self._content_panel)      # stretch=1 (EXISTING)
self._center_split.addWidget(self._history_panel)      # stretch=1 (NEW)
self._center_split.addWidget(self._quiz_panel)         # stretch=1
```

- History panel independent, can be open simultaneously with content panel
- Each has own dismiss button, own splitter sizing
- No feature regression

**Option B: Tab in Right Panel (Alternative)**

Right panel (`_right_panel`) already has tabs: Log, Metrics, Controls, Remote Control. Add "History" tab.

- Pros: Doesn't consume vertical space in center splitter
- Cons: Less visible; right panel is narrower (340px vs center ~600px)

**Recommendation**: **Option A** — history deserves prominent vertical space for list+detail split view.

---

## 5. Security and Privacy — Verified Controls

### 5.1 Database Storage (`conversation_store.py:33-38`)

```python
def _get_db_path() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    db_dir = base_dir / "memory"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "conversations.sqlite3"
```

- **Location**: `memory/conversations.sqlite3` (project-local)
- **Permissions**: OS file permissions only (no encryption)
- **WAL mode**: Enabled (`PRAGMA journal_mode = WAL`)

### 5.2 Error Logging (Verified Safe)

```python
# main.py:2191, 2232, 3257, 3259
print(f"[ConversationStore] ⚠️ Failed to store user message: {e}")
```

- Only error messages logged
- **No conversation content in logs**
- No query parameters, no message text

### 5.3 Desktop UI — No Authentication Layer

**Critical finding**: Dashboard has pairing key + AES-GCM + TLS (`dashboard/server.py`), but **desktop UI has no authentication**.

- Any local user with UI access sees full history
- No per-conversation encryption
- **Mitigation**: OS user isolation; app runs in user context

### 5.4 Required History UI Protections

| Protection | Implementation |
|------------|----------------|
| **No content in logs** | Already enforced — store logs only errors |
| **Detail view cleanup** | Clear `_content_display` on panel dismiss (`ui.py:6023 dismiss.clicked.connect(w.hide)`) |
| **No global message cache** | Fetch on demand; don't store messages in panel state |
| **Export confirmation** | Add dialog before export (out of P1 scope) |
| **Search query privacy** | Local only — no network calls |

### 5.5 PermissionGuard Alignment

History operations are **read-only**, analogous to `recall_memory`:

```python
# permission_guard.py:175
"recall_memory": OperationSpec("fs.read", idempotent=True, read_only=True, resource_scope=ResourceScope.LOCAL_FILE)
```

- No capability check needed for read operations
- No approval token required
- WorkerRegistry admission not required (no resource conflicts)

---

## 6. Scope and Acceptance Criteria — Resolved Contradictions

### 6.1 Dashboard Phase 2 vs P1

**Readiness audit contradiction**: "Dashboard parity: history endpoints exist and auth'd (Phase 2)" listed as P1 criterion #9.

**Resolution**: **Dashboard endpoints are Phase 2, not P1.**

| Component | Phase |
|-----------|-------|
| Desktop history panel (list/detail/search) | **P1** |
| Dashboard `/api/history/*` endpoints | Phase 2 |
| Dashboard app.html history tab | Phase 2 |

### 6.2 Export — Explicitly Out of P1

| Feature | Scope |
|---------|-------|
| JSON/Markdown export | Phase 2 |
| PDF/HTML export | Future |
| Bulk export | Future |

**P1 only requires**: View, search, paginate — no export.

### 6.3 Revised Measurable P1 Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | History panel opens via button/hotkey | Manual + UI test |
| 2 | Conversation list loads (paginated, 50/page) | Integration test: `list_conversations` → signal → model |
| 3 | Click conversation → shows messages (paginated, 100/page) | Integration test: `get_messages` → signal → detail view |
| 4 | Search works (debounced 300ms, grouped by conversation) | Integration test: `search_messages_grouped` → signal → list |
| 5 | Pagination: prev/next/page indicator works for list & detail | UI test |
| 6 | **Stale response protection**: Rapid conv selection discards old detail | Stress test: click A→B→C rapidly; only C's detail shown |
| 7 | **Stale response protection**: Rapid search queries discard old results | Stress test: type "a"→"ab"→"abc"; only "abc" results shown |
| 8 | Error handling: store failure shows error banner, panel usable | Unit test: mock store failure → `_history_error_sig` |
| 9 | Empty states: no conversations, no messages, no search results | UI tests for each |
| 10 | Keyboard navigation: arrows, Enter, Escape, Tab | Manual test |
| 11 | **Regression**: Content panel still works for search/news/code/review | Manual + existing behavior verification |
| 12 | **Regression**: Voice interruption unchanged (82 tests pass) | `pytest tests/unit/test_voice_barge_in.py ... -v` |
| 13 | **Regression**: WorkerRegistry unchanged (131 tests pass) | `pytest tests/unit/test_task_monitoring.py -v` |
| 14 | **Regression**: PermissionGuard unchanged (76 tests pass) | `pytest tests/unit/test_inline_permissions.py -v` |
| 15 | All new tests pass | `pytest tests/unit/test_history*.py -v` → 100% |

---

## 7. Data Correctness — Verified Behaviors

### 7.1 Empty Conversation Titles

**Conversation model** (`conversation_models.py:32,43-46`):
```python
title: str = ""
def __post_init__(self):
    if self.title == "":
        self.title = f"Conversation {self.started_at}"
```

**But main.py creates with empty title** (`main.py:3018`):
```python
conv = Conversation(id=..., title="", ...)
```

**Result**: Title becomes `"Conversation <timestamp>"` (e.g., "Conversation 1731700000000").

**UI Fix**: Display fallback `"Untitled conversation"` if title looks like timestamp:

```python
# In history panel list rendering
display_title = conv.title
if display_title.startswith("Conversation ") and display_title[13:].isdigit():
    display_title = "Untitled conversation"
```

### 7.2 Stable Ordering During Pagination

| Query | Order By | Stability |
|-------|----------|-----------|
| `list_conversations` | `started_at DESC` | Stable if `started_at` unique; tie-break by PK (`id`) |
| `get_messages` | `sequence ASC` | **Guaranteed stable** — sequence is UNIQUE per conversation |
| `search_messages` | `timestamp_ms DESC` | Stable if timestamps unique; tie-break by PK (`id`) |

**Recommendation**: Add secondary `id` ordering to all queries for deterministic pagination:

```sql
ORDER BY started_at DESC, id DESC  -- conversations
ORDER BY sequence ASC              -- messages (already unique)
ORDER BY timestamp_ms DESC, id DESC  -- search
```

### 7.3 Message Ordering and Load-More

- **Default**: `get_messages` uses `sequence ASC` (oldest first) — correct for reading
- **Load-more**: Increase `offset`, keep `limit` — appends older messages at bottom
- **Detail view**: Should show newest at bottom (chat convention) — `sequence ASC` achieves this

### 7.4 Dataclass Serialization for Signals

**Qt signals require serializable types**. Dataclasses must be converted:

```python
import dataclasses

# Worker side
conversations = store.list_conversations(...)
data = [dataclasses.asdict(cs) for cs in conversations]  # → List[dict]
player.show_history_list(data, offset, total, generation)

messages = store.get_messages(...)
data = [dataclasses.asdict(m) for m in messages]
player.show_history_detail(conv_id, data, offset, total, generation)
```

**Verified**: `ConversationSummary` and `Message` are flat dataclasses with primitive fields — `asdict()` works perfectly.

---

## 8. Revised Architecture and Data Flow

### 8.1 Component Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                        MAIN THREAD (Qt)                            │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ _center_split                                               │  │
│  │   ├── HUD Stack (stretch=3)                                 │  │
│  │   ├── _content_panel (stretch=1)  ← EXISTING, UNCHANGED     │  │
│  │   ├── _history_panel (stretch=1)  ← NEW                     │  │
│  │   │     ├── ConversationList (QListView + QStandardItemModel)│  │
│  │   │     ├── MessageDetail (QTextEdit, read-only)            │  │
│  │   │     ├── SearchBar (QLineEdit + debounce timer)          │  │
│  │   │     └── PaginationToolbar (Prev/Next/Page)              │  │
│  │   └── _quiz_panel (stretch=1)                               │  │
│  └─────────────────────────────────────────────────────────────┘  │
│       ▲                    ▲                    ▲                 │
│       │ _history_sig       │ _detail_sig        │ _search_sig     │
│       │ (list, off, tot,  │ (conv_id, msgs,   │ (query, grouped │
│       │  gen)             │  off, tot, gen)   │  results, gen)  │
│       │                   │                   │                 │
└───────│───────────────────│───────────────────│─────────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌────────────────────────────────────────────────────────────────────┐
│                    WORKER THREADS (asyncio.to_thread)              │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ HistoryWorker                                               │  │
│  │ - get_store() → thread-local ConversationStore              │  │
│  │ - list_conversations(limit, offset) + count_conversations() │  │
│  │ - get_messages(conv_id, limit, offset) + get_message_count()│  │
│  │ - search_messages_grouped(query, ...) + count_search_msgs() │  │
│  │ - Emits signals with generation counter                     │  │
│  │ - Try/except → _history_error_sig(generation)               │  │
│  └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

### 8.2 Signal Definitions (Add to `MainWindow`)

```python
# ui.py ~line 4489
_history_sig      = pyqtSignal(list, int, int, int)      # (conversations, offset, total, generation)
_detail_sig       = pyqtSignal(str, list, int, int, int)  # (conv_id, messages, offset, total, generation)
_search_sig       = pyqtSignal(str, list, int, int, int)  # (query, grouped_results, offset, total, generation)
_history_error_sig = pyqtSignal(str, int)                 # (error_message, generation)
```

### 8.3 JarvisUI Exposure

```python
# ui.py ~line 7541
def show_history_list(self, conversations: list, offset: int, total: int, generation: int):
    self._win._history_sig.emit(conversations, offset, total, generation)

def show_history_detail(self, conversation_id: str, messages: list, offset: int, total: int, generation: int):
    self._win._detail_sig.emit(conversation_id, messages, offset, total, generation)

def show_history_search(self, query: str, grouped_results: list, offset: int, total: int, generation: int):
    self._win._search_sig.emit(query, grouped_results, offset, total, generation)

def show_history_error(self, error: str, generation: int):
    self._win._history_error_sig.emit(error, generation)
```

---

## 9. Exact Files Expected to Change During Implementation

### 9.1 New Files

| File | Purpose |
|------|---------|
| `ui/history_panel.py` | `HistoryPanel` widget: split list/detail, search bar, pagination |
| `ui/history_model.py` | `QStandardItemModel` subclasses for conversation list & message detail |
| `actions/history.py` | Action plugin: `load_history_list`, `load_history_detail`, `search_history` workers |
| `memory/conversation_store.py` | **Add**: `count_search_messages()`, `search_messages_grouped()` |

### 9.2 Modified Files

| File | Changes |
|------|---------|
| `ui.py` | Add 4 signals to `MainWindow`; add 4 `show_history_*` to `JarvisUI`; integrate `HistoryPanel` into `_center_split` |
| `main.py` | Add `_history_generation` counter; register history action commands ("show history", "search conversations") |
| `memory/conversation_models.py` | No changes (dataclasses already correct) |

### 9.3 Test Files

| File | Coverage |
|------|----------|
| `tests/unit/test_history_panel.py` | Widget rendering, model population, signal handling, generation discard |
| `tests/unit/test_history_actions.py` | Worker functions: list, detail, search, pagination, error handling |
| `tests/unit/test_history_integration.py` | End-to-end: store → worker → signal → UI model; stale response protection |
| `tests/unit/test_conversation_store.py` | **Extend**: Add tests for `count_search_messages`, `search_messages_grouped` |

---

## 10. Remaining Blockers

| Blocker | Status | Resolution |
|---------|--------|------------|
| `count_search_messages` missing from store | **Must fix before P1** | Add method (5 lines SQL) |
| `search_messages_grouped` missing from store | **Must fix before P1** | Add method (Python grouping) |
| Secondary `id` ordering for stable pagination | Recommended | Add to store queries |
| Empty title fallback in UI | UI concern | Handle in `HistoryPanel` rendering |
| Debounce timer for search | UI concern | `QTimer.singleShot(300, ...)` in panel |

**No architectural blockers remain.** All are implementation tasks with clear solutions.

---

## 11. Regression Test Matrix (Must Pass Before P1 Complete)

| Suite | Command | Expected |
|-------|---------|----------|
| Voice interruption | `pytest tests/unit/test_voice_barge_in.py tests/unit/test_interrupt_recovery.py tests/unit/test_gemini_live_interrupt.py -v` | 82 passed |
| WorkerRegistry | `pytest tests/unit/test_task_monitoring.py -v` | 131 passed (1 pre-existing flake) |
| PermissionGuard | `pytest tests/unit/test_inline_permissions.py -v` | 76 passed |
| Conversation store | `pytest tests/unit/test_conversation_store.py -v` | 42 passed |
| Conversation integration | `pytest tests/unit/test_conversation_integration.py -v` | 6 passed |
| **New history tests** | `pytest tests/unit/test_history*.py -v` | **100% pass** |

---

## 12. Final Verdict

### ✅ READY FOR IMPLEMENTATION WITH CORRECTIONS

**Summary of corrections applied:**

1. **WorkerRegistry**: NOT used for history — use `asyncio.to_thread()` directly (read-only, no conflicts)
2. **Stale responses**: Use `_history_generation` counter (pattern from `main.py:602,1114`)
3. **Content panel**: ADD separate `_history_panel` in `_center_split` — do NOT replace existing
4. **Search API**: Add `count_search_messages()` and `search_messages_grouped()` to store
5. **Dashboard**: Phase 2 — not P1
6. **Export**: Phase 2 — not P1
7. **Dataclass serialization**: Use `dataclasses.asdict()` before signal emission
8. **Empty titles**: Handle in UI with "Untitled conversation" fallback
9. **Stable ordering**: Add secondary `id` ordering to store queries

**All regressions covered** by existing test suites (774+ tests). New history tests will add ~20 tests.

**Estimated effort unchanged**: 2-3 weeks for core P1.

---

*Audit completed read-only. No source modifications made.*