# MARK LVII-B P1 — Conversation History UI Readiness Audit

**Auditor**: Independent read-only audit per instructions.  
**Scope**: Assess current UI architecture for conversation history feature readiness.  
**Method**: Source code inspection, line-by-line verification, no modifications.  
**Date**: 2026-11-15

---

## Executive Summary

The JARVIS codebase now has a **complete SQLite conversation storage foundation** (Mark LVII-B P0: `ConversationStore`, `conversation_models`, 42 unit tests, 6 integration tests — all passing). However, **no UI exists to expose this history to users**. The current UI architecture supports only:

- **Activity log** (`LogWidget`): In-memory, capped at 600 lines, real-time display only
- **Content panel** (`_content_panel`): Single-purpose panel for briefings/news/code jobs
- **Dashboard feed** (`dashboard/server.py:_history`): In-memory, capped at 300 messages, WebSocket broadcast only

**Verdict**: **READY FOR IMPLEMENTATION** — The data layer is complete and tested. The UI layer has the necessary threading primitives (signals/slots), navigation patterns (stacked widgets, splitters), and display components (QTextEdit, QListView-ready architecture) to build a conversation history UI. No architectural blockers exist.

---

## 1. Current UI Architecture Analysis

### 1.1 Main Window Structure (`ui.py:MainWindow`)

| Component | Location | Purpose | Thread Safety |
|-----------|----------|---------|---------------|
| **HUD** (`HudCanvas`) | `ui.py:4713` | Animated avatar, waveforms, camera, video | Main thread only |
| **Content Panel** (`_content_panel`) | `ui.py:5972-6060` | Collapsible panel below HUD for briefings/news | Main thread via `_content_sig` |
| **Quiz Panel** (`_quiz_panel`) | Built in `__init__` | Interactive quizzes | Main thread via `_quiz_sig` |
| **Right Panel** (`_right_panel`) | `ui.py:4736` | Log, metrics, controls, remote control | Main thread |
| **Center Splitter** | `ui.py:4718-4734` | Vertical split: HUD stack / Content / Quiz | Main thread |

**Key Layout** (`ui.py:4718-4734`):
```python
self._center_split = QSplitter(Qt.Orientation.Vertical)
self._center_split.addWidget(self._hud_cam_stack)   # stretch=3
self._center_split.addWidget(self._content_panel)   # stretch=1
self._center_split.addWidget(self._quiz_panel)      # stretch=1
```

### 1.2 Thread-Safe UI Update Pattern (Signals/Slots)

The app uses a **signal-based cross-thread communication** pattern established in `ui.py:4470-4482`:

```python
# Signals defined on MainWindow (Qt thread)
_log_sig          = pyqtSignal(str)                    # Activity log
_state_sig        = pyqtSignal(str)                    # State badge
_content_sig      = pyqtSignal(str, str)               # (title, text) — content panel
_codejob_sig      = pyqtSignal(dict)                   # Coding agent progress
_review_sig       = pyqtSignal(str, str, list)         # Structured review
_quiz_sig         = pyqtSignal(str, list, object)      # Quiz
# ... more signals
```

**Thread-safe exposure via `JarvisUI`** (`ui.py:7520-7540`):
```python
def write_log(self, text: str):
    self._win._log_sig.emit(text)

def show_content(self, title: str, text: str):
    self._win._content_sig.emit(title[:48], text[:4000])

def show_quiz(self, topic: str, questions: list, grade=None):
    self._win._quiz_sig.emit(topic, questions, grade)

def show_review(self, title: str, summary: str, findings: list):
    self._win._review_sig.emit(title, summary, findings)
```

**This pattern is the mandated way** for worker threads (actions/plugins) to update UI — **never create Qt widgets off the main thread** (per `AGENTS.md`).

### 1.3 Content Panel — Current Implementation (`ui.py:5972-6079`)

```python
def _build_content_panel(self) -> QWidget:
    w = QWidget()
    w.hide()  # Hidden by default
    lay = QVBoxLayout(w)
    # Header: title + timestamp + dismiss button
    # Separator
    # QTextEdit (read-only, monospace, dark theme)
    return w

def _show_content(self, title: str, text: str):  # Slot on Qt thread
    self.hud.glance(0.0, -0.85, hold=1.3)  # Avatar looks down
    self._content_title_lbl.setText(title.upper()[:48])
    self._content_ts_lbl.setText(time.strftime("%H:%M:%S"))
    self._content_display.setPlainText(text)
    self._content_panel.show()
    # Resize splitter to show panel
```

**Limitations for history use**:
- Single panel, single content view
- No list/navigation component
- No search/filter UI
- No pagination controls
- Designed for **one-off content display**, not browsing

### 1.4 Activity Log Widget (`ui.py:1004-1100`)

```python
class LogWidget(QTextEdit):
    def __init__(self):
        self.document().setMaximumBlockCount(600)  # Hard cap
        # Color-coded by speaker: You/JARVIS/SYS/ERR/FILE
        # Typewriter animation for new lines
```

**Limitations**:
- In-memory only (Qt document model)
- No persistence
- No session boundaries
- No search, filter, export
- Append-only, no navigation

### 1.5 Right Panel — Log Section (`ui.py:_build_right_panel`)

The right panel contains a **Log tab** with the `LogWidget`, plus Metrics, Controls, and Remote Control tabs. This is the only current "history-like" UI.

---

## 2. Conversation Data Layer — Ready APIs

### 2.1 `ConversationStore` Query APIs (`memory/conversation_store.py`)

| Method | Signature | Purpose | Pagination |
|--------|-----------|---------|------------|
| `list_conversations` | `(limit=50, offset=0, order_by="started_at", descending=True)` → `List[ConversationSummary]` | Conversation list for UI | ✅ limit/offset |
| `count_conversations` | `()` → `int` | Total count for pagination UI | ✅ |
| `get_conversation` | `(conversation_id)` → `Conversation` | Full conversation metadata | — |
| `get_messages` | `(conversation_id, limit=None, offset=0, order_by="sequence", descending=False)` → `List[Message]` | Messages with pagination | ✅ limit/offset |
| `get_message_count` | `(conversation_id)` → `int` | Message count for a conversation | — |
| `search_messages` | `(query, conversation_id=None, role=None, limit=20, offset=0)` → `List[Message]` | Full-text search (LIKE) | ✅ limit/offset |

### 2.2 Data Models (`memory/conversation_models.py`)

```python
@dataclass
class ConversationSummary:
    id: str
    title: str
    started_at: int           # Unix ms
    ended_at: Optional[int]   # None = active
    turn_count: int
    summary: Optional[str]
    language: Optional[str]
    engine: str
    # from_conversation() classmethod for conversion

@dataclass
class Message:
    id: str
    conversation_id: str
    role: str                 # 'user' | 'assistant' | 'system'
    content: str
    content_type: str         # 'text' | 'tool_call' | 'tool_result' | 'vision'
    sequence: int             # 1-based within conversation
    timestamp_ms: int
    meta_json: str
```

**All models are JSON-serializable, thread-safe, and storage-agnostic.**

---

## 3. Proposed UI Layout for Conversation History

### 3.1 Recommended Approach: Repurpose Content Panel as History Browser

The **Content Panel** (`_content_panel`) is the ideal anchor for history UI because:
- Already a collapsible panel below HUD (familiar location)
- Already uses thread-safe `_content_sig` for updates
- Already has splitter resize logic for show/hide
- QTextEdit can be replaced with a **split view: List + Detail**

### 3.2 Proposed Layout (Within Existing `_center_split`)

```
┌─────────────────────────────────────────────┐
│ HUD / Camera / Video Stack                  │ ← stretch=3 (unchanged)
├─────────────────────────────────────────────┤
│ HISTORY PANEL (replaces _content_panel)     │ ← stretch=1 (repurposed)
│ ┌──────────────┬──────────────────────────┐ │
│ │ Conversation │    Message Detail        │ │
│ │ List         │    (read-only)           │ │
│ │ (QListView)  │    (QTextEdit)           │ │
│ │              │                          │ │
│ │ [Search 🔍]  │    [← Back] [Export]     │ │
│ │              │                          │ │
│ └──────────────┴──────────────────────────┘ │
├─────────────────────────────────────────────┤
│ Quiz Panel (unchanged)                      │ ← stretch=1
└─────────────────────────────────────────────┘
```

### 3.3 Component Breakdown

| Component | Qt Class | Role |
|-----------|----------|------|
| **Conversation List** | `QListView` + `QStandardItemModel` | Virtualized list, supports 1000s of items |
| **Message Detail** | `QTextEdit` (read-only) | Rich text display, syntax highlighting for tool calls |
| **Search Bar** | `QLineEdit` + debounced timer | Triggers `search_messages` |
| **Pagination** | `QToolBar` or custom widget | Prev/Next, page size selector |
| **Filter Tabs** | `QTabBar` or segmented control | All / Active / Ended / By Engine |

---

## 4. Conversation List & Detail Data Flow

### 4.1 Threading Model

```
┌─────────────────────────────────────────────────────────────────┐
│                        MAIN THREAD (Qt)                         │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ History List    │◄───│ _history_sig    │                    │
│  │ (QListView)     │    │ (list, offset)  │                    │
│  └────────┬────────┘    └────────┬────────┘                    │
│           │                      │                             │
│           │ Selection            │                             │
│           ▼                      │                             │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ Message Detail  │◄───│ _detail_sig     │                    │
│  │ (QTextEdit)     │    │ (messages)      │                    │
│  └─────────────────┘    └────────┬────────┘                    │
└──────────────────────────────────│──────────────────────────────┘
                                   │ Signal (thread-safe)
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      WORKER THREAD (asyncio)                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ HistoryWorker (or inline in action)                     │   │
│  │ - Calls ConversationStore.list_conversations()          │   │
│  │ - Calls ConversationStore.get_messages()                │   │
│  │ - Calls ConversationStore.search_messages()             │   │
│  │ - Emits _history_sig / _detail_sig on completion        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Signal Definitions Needed (Add to `MainWindow`)

```python
# Add to ui.py MainWindow signals section (~line 4473)
_history_sig     = pyqtSignal(list, int, int)      # (conversations, offset, total)
_detail_sig      = pyqtSignal(str, list)           # (conversation_id, messages)
_search_sig      = pyqtSignal(str, list)           # (query, matching_messages)
_history_error_sig = pyqtSignal(str)               # Error message
```

### 4.3 Thread-Safe Exposure via `JarvisUI`

```python
# Add to JarvisUI class (~line 7533)
def show_history_list(self, conversations: list, offset: int, total: int):
    self._win._history_sig.emit(conversations, offset, total)

def show_history_detail(self, conversation_id: str, messages: list):
    self._win._detail_sig.emit(conversation_id, messages)

def show_history_search(self, query: str, messages: list):
    self._win._search_sig.emit(query, messages)

def show_history_error(self, error: str):
    self._win._history_error_sig.emit(error)
```

### 4.4 Data Loading Sequence

**List Load** (user opens history panel):
1. UI emits request (via new signal or direct call to action)
2. Worker thread: `store.list_conversations(limit=50, offset=0)` + `store.count_conversations()`
3. Worker emits `_history_sig(conversations, 0, total_count)`
4. Qt slot: Populate `QStandardItemModel`, update pagination UI

**Detail Load** (user clicks conversation):
1. UI emits request with `conversation_id`
2. Worker thread: `store.get_messages(conversation_id, limit=100, offset=0)` + `store.get_message_count()`
3. Worker emits `_detail_sig(conversation_id, messages)`
4. Qt slot: Render messages in detail view, update pagination

**Search** (user types in search bar):
1. Debounced (300ms) search query
2. Worker thread: `store.search_messages(query, limit=50, offset=0)`
3. Worker emits `_search_sig(query, messages)`
4. Qt slot: Show results in list view (with conversation grouping)

---

## 5. Search and Pagination Design

### 5.1 Search Architecture

| Layer | Implementation |
|-------|----------------|
| **Backend** | `ConversationStore.search_messages(query, conversation_id, role, limit, offset)` — SQLite `LIKE` with parameterized query |
| **Frontend** | `QLineEdit` with `textChanged` → debounced timer (300ms) → worker thread |
| **Results** | Grouped by conversation, showing snippet + timestamp |
| **Scope** | Global (all conversations) or scoped to selected conversation |

**Performance note**: Current `search_messages` uses `LIKE %query%` — adequate for <100K messages. For larger datasets, FTS5 virtual table recommended (out of scope for P1).

### 5.2 Pagination Strategy

| View | Page Size | Navigation |
|------|-----------|------------|
| Conversation List | 50 (configurable) | Prev/Next buttons + page indicator (1 of N) |
| Message Detail | 100 (configurable) | Prev/Next + "Load more" at bottom |
| Search Results | 50 | Prev/Next + conversation filter tabs |

**Implementation**: Use `offset`/`limit` on store methods. Store `count_conversations()` and `get_message_count()` for total pages.

---

## 6. Threading/Async Safety Analysis

### 6.1 Current Safety Guarantees

| Aspect | Status | Evidence |
|--------|--------|----------|
| **Store thread-safety** | ✅ | `ConversationStore` uses `threading.Lock` + `threading.local()` connections |
| **UI thread isolation** | ✅ | All widget access via signals/slots; `AGENTS.md` enforces this |
| **Asyncio integration** | ✅ | Worker threads run asyncio loop; `asyncio.to_thread()` for sync calls |
| **Connection lifecycle** | ✅ | Per-thread connections, context-managed transactions |
| **No cross-thread widget access** | ✅ | Verified: no `QWidget` creation in actions/plugins |

### 6.2 Required Discipline for History Feature

| Rule | Enforcement |
|------|-------------|
| **Never call `ConversationStore` directly from Qt thread** | Use worker thread / `asyncio.to_thread()` |
| **Never pass `ConversationStore` instance across threads** | Each thread gets its own connection via `threading.local()` |
| **Always emit results via signals** | Follow existing `_content_sig` / `_log_sig` pattern |
| **Handle store errors gracefully** | Try/except in worker, emit `_history_error_sig` |

### 6.3 Recommended Worker Pattern

```python
# In an action/plugin or dedicated history module
def load_history_list(player, offset=0, limit=50):
    def _worker():
        try:
            store = get_store()  # Thread-local store
            conversations = store.list_conversations(limit=limit, offset=offset)
            total = store.count_conversations()
            # Convert to serializable dicts for signal
            data = [cs.__dict__ for cs in conversations]  # or custom serialization
            player.show_history_list(data, offset, total)
        except Exception as e:
            player.show_history_error(str(e))
    
    threading.Thread(target=_worker, daemon=True, name="history-list").start()
```

---

## 7. Security and Privacy Considerations

### 7.1 Data Sensitivity

| Data | Sensitivity | Current Protection |
|------|-------------|-------------------|
| Conversation content | HIGH | SQLite file permissions (OS-level) |
| Resumption handles | HIGH | Not persisted (P0 gap) |
| User facts (long_term.json) | HIGH | File permissions only |
| Search queries | MEDIUM | In-memory only |

### 7.2 Required Protections for History UI

| Protection | Implementation |
|------------|----------------|
| **No conversation content in logs** | Already enforced: `ConversationStore` logs only errors, not content |
| **Search query privacy** | Search runs locally; no network calls |
| **Export control** | Add confirmation dialog before export; sanitize meta_json |
| **Dashboard access** | Dashboard already has pairing key + AES-GCM + TLS; add history endpoints with same auth |
| **Memory cleanup** | Clear detail view on panel dismiss; don't cache messages globally |

### 7.3 Dashboard Integration (Future)

The dashboard (`dashboard/server.py`) would need new endpoints:
- `GET /api/history/conversations?limit=&offset=` → paginated `ConversationSummary`
- `GET /api/history/conversations/{id}/messages?limit=&offset=` → paginated `Message`
- `GET /api/history/search?q=&limit=&offset=` → search results

All protected by existing `_auth()` + token + AES-GCM layer.

---

## 8. Required Files and Tests

### 8.1 New Files to Create

| File | Purpose |
|------|---------|
| `ui/history_panel.py` | `HistoryPanel` widget: List + Detail split view, search, pagination |
| `ui/history_model.py` | `QStandardItemModel` subclasses for conversation list & message detail |
| `actions/history.py` | Action plugin: `load_history_list`, `load_history_detail`, `search_history` |
| `memory/history_export.py` | Export conversation to JSON/Markdown/HTML (sanitized) |

### 8.2 Modified Files

| File | Changes |
|------|---------|
| `ui.py` | Add `_history_sig`, `_detail_sig`, `_search_sig`, `_history_error_sig` to `MainWindow`; add `show_history_*` to `JarvisUI`; integrate `HistoryPanel` into `_center_split` |
| `main.py` | Register history action commands (e.g., "show history", "search conversations") |

### 8.3 Required Tests

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_history_panel.py` | Widget rendering, model population, signal handling |
| `tests/unit/test_history_actions.py` | Action plugins: list, detail, search, pagination |
| `tests/unit/test_history_integration.py` | End-to-end: store → worker → signal → UI model |
| `tests/unit/test_history_export.py` | Export formats, sanitization, large conversations |

**Minimum test scenarios**:
- List loads first page, pagination works
- Click conversation → detail loads messages
- Search returns grouped results
- Empty state handling (no conversations)
- Error handling (store failure → error signal)
- Thread safety: rapid clicks, concurrent loads
- Large dataset performance (1000+ conversations)

---

## 9. Risks and Acceptance Criteria

### 9.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **UI blocking on large conversations** | Medium | High | Virtualized `QListView`; lazy-load message detail; limit initial detail to 100 messages |
| **Search performance on large DB** | Medium | Medium | Debounce (300ms); limit results to 50; add FTS5 in Phase 2 |
| **Thread-signal race conditions** | Low | High | Follow existing signal pattern; use `QueuedConnection` (default) |
| **Memory bloat from cached messages** | Low | Medium | Don't cache; fetch on demand; clear detail on panel hide |
| **Schema migration breaking history** | Low | High | `ConversationStore` has migration runner; test migration path |

### 9.2 Acceptance Criteria for P1

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | **History panel opens from UI** (button/hotkey) | Manual + UI test |
| 2 | **Conversation list loads** (paginated, 50 per page) | Integration test: `list_conversations` → signal → model |
| 3 | **Click conversation → shows messages** (paginated) | Integration test: `get_messages` → signal → detail view |
| 4 | **Search works** (debounced, grouped by conversation) | Integration test: `search_messages` → signal → list |
| 5 | **Thread safety**: no UI freezes during load | Stress test: rapid navigation, concurrent loads |
| 6 | **Error handling**: store failure shows error banner | Unit test: mock store failure → `_history_error_sig` |
| 7 | **Empty states**: no conversations, no messages, no search results | UI tests for each empty state |
| 8 | **Keyboard navigation**: arrows, Enter, Escape | Manual + UI test |
| 9 | **Dashboard parity**: history endpoints exist and auth'd | Dashboard test (Phase 2) |
| 10 | **All new tests pass** | `pytest tests/unit/test_history*.py -v` → 100% pass |

---

## 10. Explicit Out-of-Scope Items (Not P1)

| Item | Reason | Target |
|------|--------|--------|
| **FTS5 full-text search** | Current LIKE sufficient for <100K msgs | Phase 2 |
| **Conversation title generation** | Requires LLM call; deferred | Phase 2 |
| **Resumption handle persistence** | P0 gap; separate milestone | Mark LVII-B P0 follow-up |
| **Dashboard history endpoints** | Requires dashboard API expansion | Phase 2 |
| **Export to PDF/HTML** | Nice-to-have; JSON/MD first | Phase 2 |
| **Conversation tagging/folders** | New schema fields needed | Phase 2 |
| **Cross-device sync** | Major architecture change | Future |
| **Voice command "show history"** | Requires intent recognition | Phase 2 |

---

## 11. Implementation Sequence (Recommended)

### Phase 1A — Core Panel (Week 1)
1. Create `HistoryPanel` widget with split view
2. Add signals to `MainWindow` + `JarvisUI` exposure
3. Integrate into `_center_split` (replace `_content_panel` or add as tab)
4. Basic list model + detail view (static data)

### Phase 1B — Data Wiring (Week 1-2)
5. Create `actions/history.py` with worker functions
6. Wire list load → `list_conversations` → signal → model
7. Wire detail load → `get_messages` → signal → detail view
8. Add pagination controls + logic

### Phase 1C — Search & Polish (Week 2)
9. Add search bar + debounced worker → `search_messages`
10. Empty states, error handling, loading indicators
11. Keyboard navigation, accessibility
12. Write unit/integration tests

### Phase 1D — Dashboard Parity (Week 2-3, optional)
13. Add history endpoints to `dashboard/server.py`
14. Update dashboard `app.html` for history tab

---

## 12. Conclusion

**The JARVIS codebase is READY for Conversation History UI implementation.**

### ✅ What Exists (Solid Foundation)
- **Complete data layer**: `ConversationStore` with WAL, FK CASCADE, thread-local connections
- **Complete query APIs**: `list_conversations`, `get_messages`, `search_messages` — all paginated
- **Complete data models**: `ConversationSummary`, `Message` — serializable, typed
- **Proven threading pattern**: Signals/slots for cross-thread UI updates
- **Existing UI primitives**: Content panel, splitter, QTextEdit, signal infrastructure
- **Test coverage**: 42 store tests + 6 integration tests passing

### 🔧 What Needs Building (P1 Scope)
- **History Panel widget**: Split list/detail view with pagination
- **Action plugins**: Worker-thread data loading with signal emission
- **Search integration**: Debounced search using `search_messages`
- **Tests**: Unit + integration for all new components

### 📋 No Architectural Blockers
- Threading model supports the pattern
- Data layer is complete and tested
- UI architecture has extension points (signals, splitter, panel pattern)
- Security model extends naturally (dashboard auth, no secrets in logs)

**Estimated effort**: 2-3 weeks for core P1 (panel + list + detail + search + tests).  
**Recommended start**: Phase 1A — build the panel widget and signal plumbing first.

---

*Audit completed read-only. No source modifications made.*