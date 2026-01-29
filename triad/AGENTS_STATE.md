# AGENTS STATE — CryptoTrader

> Shared state file for Triad workflow coordination.

---

## Goal
Build an AI-powered cryptocurrency trading platform with 230 features across 11 phases. Multi-agent architecture with Market Analyst, Strategy Optimizer, Sentiment/News, Risk Monitor, Trade Executor, and Orchestrator agents.

## Constraints
- Follow PLAN.md exactly
- No changes outside specified files without approval
- Flag blockers immediately
- Dark theme UI, TailwindCSS styling
- Async Python with type hints
- React functional components with hooks

## Next
- **Claude**: Address review findings from `REVIEW_PHASE1.md`. High priority: lack of tests.
- **Codex**: Continue implementing Phase 2, but be prepared to pause to address review findings.

---

## In Progress
- **Codex**: Implementing Phase 2 (Tasks 2.1-2.7) - Exchange Integration

## Completed
- [x] Project analysis (2026-01-29)
- [x] PLAN.md populated with 11 phases, 50+ tasks
- [x] Phase 1: Foundation & Infrastructure (20 tasks) - 2026-01-29
- [x] Phase 1 Code Review (Gemini) - 2026-01-29

## How to Run

**Backend:**
```bash
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm start  # Runs on port 3000
```

**Full Stack (via init.sh):**
```bash
./init.sh
```

---

## Known Issues
- **High**: No automated tests for backend or frontend.
- **Medium**: Password reset service uses in-memory storage.
- **Low**: Hardcoded CORS origin, mismatched frontend/backend validation.
- See `REVIEW_PHASE1.md` for full details.

---

## Section Ownership

| Section | Owner |
|---------|-------|
| Goal, Constraints, Next | Claude |
| In Progress, Completed, How to Run | Codex |
| Known Issues | Gemini |

---

## Current State Summary

### What Exists
- Database models: 15 tables defined in `backend/db/models.py`
- FastAPI entry point with health check endpoint
- React app with routing skeleton (7 placeholder pages)
- TailwindCSS configured
- Project structure with empty directories

### What's Needed Next (Phase 1)
1. API router structure and authentication endpoints
2. React auth context, login/register pages
3. Protected route wrapper
4. Main app layout (sidebar, header, content area)
5. API client service with auth interceptors
6. Celery/Redis setup for background tasks
7. Base agent class and message queue interface
