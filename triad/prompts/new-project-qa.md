# Triad New Project Q&A

> Use this prompt to guide the conversation when defining a new project.

---

## Phase 1: Project Overview

Ask these questions (adapt based on user responses):

1. **What are you building?**
   - Get a 1-2 sentence description
   - Clarify if it's a web app, CLI tool, API, mobile app, etc.

2. **Who is it for?**
   - Target users (developers, consumers, internal team, etc.)
   - Single user or multi-user?

3. **What problem does it solve?**
   - Why build this? What's the motivation?

---

## Phase 2: Core Features

4. **What are the must-have features for v1?**
   - List 3-5 core features
   - Push back on scope creep — what's truly essential?

5. **What's explicitly out of scope for now?**
   - Nice-to-haves that can wait
   - Prevents feature creep during implementation

---

## Phase 3: Technical Requirements

6. **Any tech stack preferences or constraints?**
   - Languages, frameworks, databases
   - Hosting requirements
   - If no preference, Claude recommends based on use case

7. **Any integrations needed?**
   - Third-party APIs
   - Authentication providers
   - Payment systems

8. **Any constraints?**
   - Budget (free tier only, etc.)
   - Timeline
   - Must work offline?
   - Performance requirements

---

## Phase 4: Existing Assets

9. **Do you have any existing work?**
   - Designs, mockups, specs
   - Existing code to integrate
   - Database schemas

10. **Any reference projects or inspiration?**
    - "Like X but for Y"
    - Specific features from other products

---

## After Q&A: Generate Outputs

Based on responses, create:

### 1. PROJECT_SPEC.md
```markdown
# Project Specification — [Name]

## Overview
[1-2 paragraph description]

## Target Users
[Who uses this]

## Problem Statement
[What problem it solves]

## Core Features (MVP)
1. [Feature]
2. [Feature]
...

## Out of Scope (v1)
- [Deferred feature]
...

## Tech Stack
- Frontend: [choice + rationale]
- Backend: [choice + rationale]
- Database: [choice + rationale]
- Hosting: [choice + rationale]

## Integrations
- [Integration + purpose]

## Constraints
- [Constraint]

## References
- [Links or descriptions]
```

### 2. PLAN.md
- Phase 1: Project Setup (scaffolding, dependencies, basic structure)
- Phase 2: Core Feature 1
- Phase 3: Core Feature 2
- etc.

### 3. DECISIONS.md
- DEC-001: Tech stack selection

### 4. AGENTS_STATE.md
- Goal: Build [project] MVP
- Constraints: From Q&A
- Next: Phase 1 tasks

---

## Tips for Claude

- Don't ask all questions at once — conversational flow
- If user gives a detailed initial description, skip redundant questions
- Suggest tech stack if user has no preference
- Keep MVP small — can always add more later
- Confirm understanding before generating outputs
