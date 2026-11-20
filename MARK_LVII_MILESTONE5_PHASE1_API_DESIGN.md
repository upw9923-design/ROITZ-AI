# MARK LVII — Milestone 5 PHASE 1 API Design Document  
**Dashboard History Endpoints — Specification**

---
**Date:** 2026-11-18  
**Project:** `D:\M MONSTER PROJECT\Roitz-main`  
**Milestone:** 5 — Dashboard History Endpoints  
**Phase:** 1 — API Design and Acceptance Criteria  
**Status:** ✅ **DESIGN COMPLETE**

---

## 1. Executive Summary

**Design Pattern:** Single-Owner Model (all authenticated users = owner)  
**Security Model:** Token-based auth + owner-only PermissionGuard checks  
**API Scope:** 2 endpoints (list conversations, get messages)  
**Pagination:** Support for offset/limit in both endpoints  
**Sorting:** Default sort by `started_at` descending (newest first)

### Design Principles
1. **SIMPLICITY FIRST** — Minimal endpoints, no search (out of scope)
2. **FAIL-FAST** — Clear error codes for unauthorized, not found, bad requests
3. **SURGICAL CHANGES** — Extend existing auth pattern, reuse ConversationStore
4. **GOAL-DRIVEN** — Satisfy Milestone 5 requirements only

---

## 2. API Endpoints

### 2.1 `GET /api/sessions` — List Conversations

**Purpose:** Retrieve paginated list of conversations with summaries

**Authentication:** Bearer token required (existing pattern)

**Request:**
```http
GET /api/sessions?offset=0&limit=50&order_by=started_at&descending=true
Authorization: Bearer <token>
```

**Query Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `offset` | `0` | Number of records to skip |
| `limit` | `50` | Maximum records to return (max 200) |
| `order_by` | `started_at` | Sort field (`started_at`, `title`, `turn_count`) |
| `descending` | `true` | Sort order (`true` = desc, `false` = asc) |

**Success Response (200 OK):**
```json
{
  "ok": true,
  "sessions": [
    {
      "id": "abc123...",
      "title": "Project discussion",
      "started_at": 1731926400000,
      "ended_at": 1731926700000,
      "turn_count": 12,
      "summary": "-discussed API design...",
      "language": "en",
      "engine": "gemini_live",
      "created_at": 1731926400000,
      "updated_at": 1731926700000
    }
  ],
  "pagination": {
    "offset": 0,
    "limit": 50,
    "total": 42,
    "has_more": false
  }
}
```

**Error Responses:**
| Status | Code | Description |
|--------|------|-------------|
| 401 | `unauthorized` | Missing or invalid token |
| 400 | `invalid_parameter` | Invalid offset/limit values |
| 500 | `storage_error` | Database query failure |

---

### 2.2 `GET /api/sessions/{conversation_id}/messages` — Get Conversation Messages

**Purpose:** Retrieve all messages for a specific conversation

**Authentication:** Bearer token required

**Request:**
```http
GET /api/sessions/abc123/messages?offset=0&limit=100
Authorization: Bearer <token>
```

**Query Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `offset` | `0` | Number of messages to skip |
| `limit` | `100` | Maximum messages to return (max 500) |

**Success Response (200 OK):**
```json
{
  "ok": true,
  "conversation_id": "abc123...",
  "messages": [
    {
      "id": "msg1...",
      "conversation_id": "abc123...",
      "role": "user",
      "content": "Hello, what is ROITZ?",
      "content_type": "text",
      "sequence": 1,
      "timestamp_ms": 1731926400000,
      "meta_json": "{}",
      "created_at": 1731926400000
    },
    {
      "id": "msg2...",
      "conversation_id": "abc123...",
      "role": "assistant",
      "content": "ROITZ is an AI assistant...",
      "content_type": "text",
      "sequence": 2,
      "timestamp_ms": 1731926401000,
      "meta_json": "{}",
      "created_at": 1731926401000
    }
  ],
  "pagination": {
    "offset": 0,
    "limit": 100,
    "total": 42,
    "has_more": false
  }
}
```

**Error Responses:**
| Status | Code | Description |
|--------|------|-------------|
| 401 | `unauthorized` | Missing or invalid token |
| 404 | `conversation_not_found` | Conversation ID not found |
| 400 | `invalid_parameter` | Invalid offset/limit values |
| 500 | `storage_error` | Database query failure |

---

## 3. Data Models

### 3.1 SessionSummary (for list response)
```python
{
    "id": "uuid-hex",
    "title": "string (user-editable)",
    "started_at": 1731926400000,      # milliseconds
    "ended_at": 1731926700000 | null, # milliseconds or null if active
    "turn_count": 12,                 # user+assistant pairs
    "summary": "string | null",       # optional 1-2 sentence summary
    "language": "en | null",          # dominant language detected
    "engine": "gemini_live",          # conversation engine used
    "created_at": 1731926400000,      # record creation
    "updated_at": 1731926700000       # last modification
}
```

### 3.2 Message (for messages response)
```python
{
    "id": "uuid-hex",
    "conversation_id": "uuid-hex",
    "role": "user|assistant|system",
    "content": "message text content",
    "content_type": "text|tool_call|tool_result|vision",
    "sequence": 1,                    # 1-based, unique per conversation
    "timestamp_ms": 1731926400000,    # when message received
    "meta_json": "{}",                # extensible JSON
    "created_at": 1731926400000       # record creation
}
```

### 3.3 Pagination Object
```python
{
    "offset": 0,
    "limit": 50,
    "total": 42,          # total matching records (ignoring pagination)
    "has_more": false     # true if more records available
}
```

---

## 4. Authentication & Authorization

### 4.1 Authentication (Existing Pattern)
```python
def _auth(req: Request) -> bool:
    """Validate bearer token exists and is not expired."""
    return _valid(req.headers.get("authorization", "").removeprefix("Bearer ").strip())
```

**Token Properties:**
- Issued via `/login` (PIN key) or `/auto-login` (QR code)
- TTL: 12 hours (`_TOKEN_TTL_SECONDS = 12 * 3600`)
- Revocable via `/api/revoke-devices`

### 4.2 Authorization (New - Single-Owner Model)
```python
def _require_owner(req: Request) -> PermissionResult:
    """Owner-only authorization for history operations."""
    if not _auth(req):
        return PermissionResult(False, "unauthorized")
    # All authenticated users are owners (single-owner model)
    # No user isolation required for v1
    return PermissionResult(True, "owner")
```

**Implementation:** Owner checks added to each history endpoint handler

---

## 5. Error Handling

### 5.1 Standard Error Response Format
```json
{
  "error": "unauthorized",
  "message": "Authentication required or token expired"
}
```

### 5.2 Error Codes
| Code | HTTP | Description |
|------|------|-------------|
| `unauthorized` | 401 | Missing/invalid token |
| `conversation_not_found` | 404 | Conversation ID doesn't exist |
| `invalid_parameter` | 400 | Query parameter validation failed |
| `storage_error` | 500 | Database query failed |

---

## 6. Pagination Implementation

### 6.1 Offset/Limit Validation
- `offset`: Must be `>= 0`, default `0`
- `limit`: Must be `1-500`, default `50` (sessions), `100` (messages)
- Max limits enforced: sessions `200`, messages `500`

### 6.2 Total Count Calculation
- Query count separately before fetching data
- Store `total` in pagination object
- Set `has_more = offset + limit < total`

---

## 7. Implementation Checklist

### 7.1 Code Changes Required

| File | Change | Priority |
|------|--------|----------|
| `dashboard/server.py` | Add two new endpoint routes | P0 |
| `dashboard/server.py` | Add `_require_owner()` helper | P0 |
| `tests/unit/test_dashboard_history.py` | Create test suite | P1 |
| `docs/dashboard_api.md` | Add API documentation | P2 |

### 7.2 Testing Requirements

| Test Type | Cases | Priority |
|-----------|-------|----------|
| Authentication | Valid token, expired, missing, invalid | P0 |
| Authorization | Owner-only access | P0 |
| Pagination | Offset/limit validation, has_more | P0 |
| Error Handling | 401, 404, 400, 500 scenarios | P0 |
| Data Integrity | Conversation exists, messages belong to it | P0 |

---

## 8. Acceptance Criteria

### 8.1 Functional Acceptance

| # | Criterion | Pass Condition |
|---|-----------|----------------|
| AC1 | `GET /api/sessions` returns paginated list | 200 OK with sessions array and pagination |
| AC2 | `GET /api/sessions/{id}/messages` returns messages | 200 OK with messages array |
| AC3 | Token validation | 401 for missing/expired token |
| AC4 | Conversation existence check | 404 for non-existent ID |
| AC5 | Pagination parameters | Validates offset/limit, returns has_more |
| AC6 | Empty result handling | Returns empty arrays with pagination |

### 8.2 Non-Functional Acceptance

| # | Criterion | Pass Condition |
|---|-----------|----------------|
| NFA1 | Response time | < 500ms for typical query |
| NFA2 | Concurrent requests | Handles 10+ simultaneous connections |
| NFA3 | Thread safety | No race conditions in database access |
| NFA4 | Token expiry | Expired tokens immediately rejected |

---

## 9. Design Decisions

### 9.1 What's IN Scope
1. ✅ List conversations (paginated)
2. ✅ Get messages for a conversation (paginated)
3. ✅ Basic pagination (offset/limit)
4. ✅ Owner-only authorization

### 9.2 What's OUT OF Scope (Future)
1. ❌ Search conversations/messages (requires PermissionGuard integration)
2. ❌ Filter by date range (requires schema changes)
3. ❌ Filter by role (user/assistant/system)
4. ❌ Conversation deletion (requires owner approval)
5. ❌ Export functionality (JSON/CSV)

### 9.3 Rationale

**Why pagination only (no search in v1)?**
- Milestone 5 scope: "Basic conversation history access"
- Search requires PermissionGuard integration (blocked)
- Search is "nice to have" but not "must have"

**Why single-owner model?**
- Matches current dashboard assumptions
- Lowest complexity implementation
- Can be extended later if multi-user needed

**Why no date range filters?**
- Requires schema changes (add date columns)
- Out of scope for Milestone 5
- Can be added via search in future

---

## 10. Migration Path

### 10.1 Phase 1 (This Milestone)
- Add 2 endpoints
- Basic pagination
- Owner-only auth

### 10.2 Phase 2 (Future)
- PermissionGuard integration
- Search functionality
- User isolation
- Filter options

### 10.3 Backward Compatibility
- No existing endpoints modified
- New endpoints added only
- Safe to deploy alongside existing routes

---

## 11. Files to Create/Modify

### 11.1 Modified Files
| File | Lines Added | Description |
|------|-------------|-------------|
| `dashboard/server.py` | ~80 | Two new endpoints + helper |

### 11.2 New Files
| File | Lines | Description |
|------|-------|-------------|
| `tests/unit/test_dashboard_history.py` | ~200 | Test suite |
| `docs/dashboard_api.md` | ~150 | API documentation |
| `MARK_LVII_MILESTONE5_PHASE1_ACCEPTANCE.md` | ~100 | Acceptance report (future) |

---

## 12. Design Review Checklist

| Item | Status | Notes |
|------|--------|-------|
| Follows project patterns | ✅ | Matches existing auth pattern |
| Minimal changes | ✅ | Only 2 endpoints, no refactoring |
| Error handling | ✅ | Standard 401/404/400/500 |
| Pagination | ✅ | Offset/limit with has_more |
| Auth model | ✅ | Single-owner (current assumption) |
| Data models | ✅ | Reuse existing ConversationStore models |
| Testability | ✅ | Clear endpoints, predictable output |
| Performance | ✅ | Direct DB queries, no N+1 |

---

## 13. Final Approval

**Design Approved:** ✅ YES  
**Ready for Implementation:** ✅ YES  
**Security Review Required:** ✅ YES (owner-only model acceptable)  
**Documentation Required:** ⏳ Deferred to Phase 6

---

**Designer:** PHASE 1 Specification — MARK LVII
