# ROITZ AI + MONSTER — Product Requirements Document (PRD)

**Project Root:** `D:\M MONSTER PROJECT\Roitz-main`  
**Date:** 2026-11-18  
**Version:** 1.0  
**Status:** Initial Audit & Requirements Baseline

---

## 1. Executive Summary

ROITZ AI is a local-first, privacy-respecting intelligent personal computer assistant powered by the MONSTER intelligence engine. Designed primarily for Windows 11, it combines natural language understanding (Hindi, English, Hinglish), secure computer control, voice interaction, task planning and execution, conversation history storage, secure dashboard access, and robust security safeguards (PermissionGuard, owner approval, audit logging, fail-closed behavior).

---

## 2. Product Requirements Matrix

| Req ID | Capability / Feature | Priority | Dependencies | Status | Verification Method |
|--------|---------------------|----------|--------------|--------|---------------------|
| **REQ-01** | Holographic Avatar & Lip-Sync | High | PyQt6, VisemeStream | IMPLEMENTED | Visual verification & unit tests |
| **REQ-02** | Multi-lingual Voice (Hindi/English/Hinglish) | High | Whisper + Piper / ElevenLabs | IMPLEMENTED | Audio test suite & manual check |
| **REQ-03** | Push-to-Talk & Wake Word ("Hey Jarvis") | Medium | sounddevice, pvporcupine | IMPLEMENTED | Hotkey & audio test suite |
| **REQ-04** | Conversation History Storage (SQLite WAL) | Critical | SQLite3, conversation_store.py | IMPLEMENTED & ACCEPTED | 57 unit tests (100% pass) |
| **REQ-05** | Resumption Handle Persistence (Encrypted) | Critical | AES-256-GCM, conversation_store | IMPLEMENTED & ACCEPTED | Integration tests |
| **REQ-06** | Dashboard History REST Endpoints | High | FastAPI, ConversationStore | IMPLEMENTED & TESTED | 41 unit tests (100% pass) |
| **REQ-07** | PermissionGuard & Fail-Closed Security | Critical | permission_manager.py | IMPLEMENTED & TESTED | Permission test suites |
| **REQ-08** | Computer Control & Screen Observation | High | MSS, pyautogui, OpenCV | IMPLEMENTED | Screen & control test suites |
| **REQ-09** | Task Execution & Agentic Planning | High | TaskAgent, WorkerRegistry | IMPLEMENTED | Task monitor test suites |
| **REQ-10** | Plugin System (Auto-discovery) | Medium | core/plugin_loader.py | IMPLEMENTED | Plugin load tests |

---

## 3. Detailed Functional & Security Specifications

### 3.1 Conversation History & Dashboard API (Milestone 5)
- **Endpoints:**
  - `GET /api/sessions`: Paginated list of conversations (`offset`, `limit`, `order_by`, `descending`) with metadata and summaries.
  - `GET /api/sessions/{conversation_id}/messages`: Paginated messages for a specific conversation (`offset`, `limit`, ordered by sequence).
- **Security:** Bearer token authentication with 12-hour TTL and IP rate-limiting (`_Throttle`).
- **Storage:** SQLite with WAL mode, foreign keys enabled, and checkpoint truncation on close to prevent file locking on Windows.

### 3.2 Security & Permissions
- **PermissionGuard:** Fail-closed access control for sensitive actions.
- **Owner Authentication:** Argon2id / PBKDF2 credential validation.
- **Data Protection:** AES-256-GCM encryption at rest for sensitive metadata and resumption handles.

---

## 4. Verification & Acceptance Criteria
- All core unit test suites (ConversationStore, HistoryWorker, PermissionManager, TaskAgent, Dashboard History) must pass with 100% success rate.
- No security regression in permission checks or fail-closed behavior.
- Clean execution across Windows 11 runtime environment.
