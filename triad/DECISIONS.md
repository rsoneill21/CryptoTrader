# DECISIONS — CryptoTrader

> Architecture decisions with context and rationale. Owned by Claude.

---

## Active Decisions

### DEC-001: Session-Based Authentication

**Date:** 2026-01-29
**Status:** accepted
**Context:** Need authentication system for single-user trading platform.

**Options Considered:**
1. **JWT tokens** — Stateless, scalable, but harder to revoke
2. **Session tokens in DB** — Stateful, easy revocation, simpler for single user
3. **OAuth/SSO** — Overkill for personal use app

**Decision:** Session tokens stored in database (Option 2)
**Rationale:** Single-user app doesn't need JWT scalability. DB sessions allow easy revocation, session timeout enforcement, and simpler implementation. Can migrate to JWT later if multi-user support needed.
**Consequences:** Sessions table in DB. Token validation on each request. Periodic cleanup of expired sessions needed.

---

### DEC-002: Redis for Agent Communication

**Date:** 2026-01-29
**Status:** accepted
**Context:** Multi-agent architecture needs inter-agent messaging.

**Options Considered:**
1. **Redis pub/sub** — Fast, simple, widely supported
2. **RabbitMQ** — More features, more complexity
3. **Database polling** — Simple but inefficient
4. **Direct function calls** — Tight coupling, not scalable

**Decision:** Redis pub/sub with in-memory fallback (Option 1)
**Rationale:** Redis is already needed for Celery. Pub/sub is simple and sufficient for agent communication. Fallback allows development without Redis running.
**Consequences:** Redis dependency. Need graceful handling when Redis unavailable.

---

### DEC-003: Celery for Background Tasks

**Date:** 2026-01-29
**Status:** accepted
**Context:** Need background task processing for agents and scheduled jobs.

**Options Considered:**
1. **Celery + Redis** — Mature, feature-rich, good monitoring
2. **FastAPI BackgroundTasks** — Simple but limited
3. **Dramatiq** — Simpler than Celery but less ecosystem
4. **asyncio only** — No persistence, lost on restart

**Decision:** Celery with Redis broker (Option 1)
**Rationale:** Celery provides task persistence, retries, scheduling (beat), and monitoring. Redis already needed for agent messaging. Well-documented and battle-tested.
**Consequences:** Additional worker process needed. Redis required for production.

---

### DEC-004: Dark Theme Default with Light Option

**Date:** 2026-01-29
**Status:** accepted
**Context:** User preference for UI theme.

**Options Considered:**
1. **Dark only** — Common for trading apps
2. **Light only** — Traditional
3. **Dark default + light option** — User choice
4. **System preference detection** — Automatic

**Decision:** Dark theme default with light theme toggle (Option 3)
**Rationale:** Trading apps traditionally use dark themes (easier on eyes during long sessions). User requested light option as well. Theme preference persisted in localStorage.
**Consequences:** ThemeContext for state management. CSS variables or Tailwind dark: classes for styling.

---

### DEC-005: Collapsible Sidebar Navigation

**Date:** 2026-01-29
**Status:** accepted
**Context:** Navigation UI layout for dashboard.

**Options Considered:**
1. **Fixed sidebar** — Always visible, takes space
2. **Collapsible sidebar** — Toggle between full and icon-only
3. **Top nav only** — Horizontal, limited items
4. **Hamburger menu** — Hidden by default, mobile-style

**Decision:** Collapsible sidebar + top nav bar (Option 2 + 3 hybrid)
**Rationale:** User requested "pop in/out" sidebar with nav bar. Sidebar state persisted. Works well on desktop and mobile.
**Consequences:** Sidebar state in localStorage. Responsive breakpoints needed.

---

### DEC-006: Kraken as Primary Exchange

**Date:** 2026-01-29
**Status:** accepted
**Context:** Need to choose initial exchange integration.

**Options Considered:**
1. **Kraken** — Good API, reliable, user's preference
2. **Binance** — Largest volume, complex API
3. **Coinbase** — US-friendly, simpler API
4. **Multi-exchange from start** — More work upfront

**Decision:** Kraken first, architecture supports adding others (Option 1)
**Rationale:** User specified Kraken. Good documentation and API. Architecture will use abstraction layer to allow adding Binance/Coinbase later.
**Consequences:** krakenex library for API. Exchange abstraction layer needed for future exchanges.

---

## Decision Template

When adding a decision, use this format:

### DEC-XXX: _Title_

**Date:** YYYY-MM-DD
**Status:** proposed | accepted | deprecated | superseded
**Context:** _What situation prompted this decision?_

**Options Considered:**
1. _Option A_ — pros/cons
2. _Option B_ — pros/cons
3. _Option C_ — pros/cons

**Decision:** _Which option was chosen?_
**Rationale:** _Why this option over others?_
**Consequences:** _What are the implications? Any follow-up work needed?_

---

## Superseded Decisions

_Decisions that have been replaced by newer ones._
