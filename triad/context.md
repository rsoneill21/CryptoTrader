# context.md — Triad Project Context

## Purpose
This document captures the rationale, decisions, and workflow agreed upon in prior discussion so a planning/architecture agent (Claude) can be brought up to speed quickly without rehashing background.

---

## Project Name
**Triad**

Tagline:
> Plan. Build. Review.

Triad is a role-based, multi-AI development workflow designed to spread workload across different AI tools, avoid usage limits, and prevent agent collision.

---

## Core Problem Being Solved
Using a single AI agent for planning, implementation, testing, and review:
- burns usage limits quickly
- causes architectural drift
- leads to agent thrash
- does not scale well for long-running projects

Triad intentionally separates responsibilities so each AI focuses on what it does best.

---

## Agreed Roles (Non-Negotiable)

### Claude — Architecture & Planning
- Owns reasoning, system design, and planning
- Writes/updates:
  - PLAN.md
  - DECISIONS.md
- Identifies edge cases, risks, acceptance criteria, and test strategy
- Does NOT write production code or modify implementation files

### Codex — Implementation & Execution
- Implements tasks defined in PLAN.md
- Refactors code as required
- Runs tests locally
- Applies fixes based on review feedback
- The ONLY agent allowed to edit source code

### Gemini — Review & Hardening
- Reviews diffs against PLAN.md and DECISIONS.md
- Produces punch lists (correctness, security, edge cases, docs)
- Suggests improvements and alternatives
- Does NOT apply code changes

---

## Workflow Summary

1. Claude writes or updates PLAN.md
2. Codex implements PLAN.md on a feature branch
3. Gemini reviews and writes a punch list (no code edits)
4. Codex applies fixes and finalizes changes

Golden rule:
> Only one agent holds the pen on code at any moment.

---

## Key Files and Their Purpose

- AGENTS.md  
  Master workflow contract for all agents

- CLAUDE.md  
  Claude’s operating constitution (role, constraints, output rules)

- PLAN.md  
  Explicit task breakdown and acceptance criteria (Claude-owned)

- AGENTS_STATE.md  
  Shared state capsule to prevent re-explaining context

- DECISIONS.md  
  Architectural decisions with tradeoffs and rationale

- reviews/  
  Gemini-only review artifacts (no code changes)

---

## Design Principles
- Plans before code
- Review without collision
- Durable markdown over repeated prompts
- Provider-agnostic (Claude, Codex, Gemini are interchangeable by role)
- Human-in-the-loop control

---

## What Triad Is Not
- Not an autonomous agent swarm
- Not a framework or library
- Not an orchestration engine
- Not model-specific

Triad is a lightweight operating model for using AI tools effectively over time.

---

## Instruction to Claude
When operating in this repository:
- Follow CLAUDE.md strictly
- Do not write production code
- Be explicit and implementation-oriented in plans
- Assume Codex will implement exactly what is written
