# Triad

**Triad** is a role-based, multi-AI development workflow designed to scale long-running projects without agent collision, context loss, or usage burnout.

It coordinates **three distinct AI roles**—planning, implementation, and review—so each model does what it’s best at, one at a time.

> **Plan. Build. Review.**

---

## Why Triad exists

Modern AI tools are powerful, but a single agent doing everything:
- burns usage limits quickly
- loses architectural coherence
- thrashes between planning and coding
- produces inconsistent results over time

Triad solves this by **separating responsibilities** and enforcing clean handoffs between agents.

---

## The Triad Roles

Triad is built around three cooperating roles:

### 1. Claude — Architecture & Planning
- Owns system design and reasoning
- Writes implementation plans
- Identifies edge cases and risks
- Records architectural decisions

Claude **never writes production code**.

### 2. Codex — Implementation & Execution
- Implements tasks from the plan
- Refactors code
- Runs tests locally
- Applies fixes from review feedback

Codex is the **only agent that edits source code**.

### 3. Gemini — Review & Hardening
- Reviews diffs against the plan
- Identifies bugs, edge cases, and security issues
- Suggests improvements and alternatives
- Polishes documentation

Gemini **does not apply code changes**.

---

## Core Principles

- **Single writer rule**: only one agent edits code at a time
- **Plans before code**: implementation follows an explicit plan
- **Reviews without collisions**: feedback is written, not applied
- **Durable context**: shared markdown files replace repeated prompts
- **Provider-agnostic**: works with any AI tools that can read/write files

---

## Repository Structure

```
triad/
├── AGENTS.md           # Role definitions and responsibilities
├── AGENTS_STATE.md     # Current workflow state (shared by all agents)
├── CLAUDE.md           # Claude-specific instructions
├── DECISIONS.md        # Architectural decision log
├── PLAN.md             # Current implementation plan
├── prompts/            # Agent prompt templates
├── reviews/            # Review output from Gemini
└── scripts/            # Utility scripts
    ├── init.sh                 # Initialize a new Triad project
    ├── slack_new_project.sh    # Create Slack channel for a project
    ├── slack_post.sh           # Post messages to Slack as an agent role
    └── templates/              # Project file templates
        └── .env.example        # Environment variable template
```

---

## Scripts

### `scripts/slack_post.sh`
Post messages to a project's Slack channel with agent role prefixes.

```bash
./scripts/slack_post.sh <CLAUDE|CODEX|GEMINI> "message"
```

**Required environment variables:**
- `SLACK_BOT_TOKEN` — Your Slack bot token
- `TRIAD_SLACK_CHANNEL` — Target channel name (e.g., `triad-myproject`)

### `scripts/slack_new_project.sh`
Create a new Slack channel for a Triad project and invite users.

### `scripts/init.sh`
Initialize a new project directory with Triad template files, scripts, and environment setup.

Creates:
- `triad/` — workflow state files
- `scripts/` — copies of Slack integration scripts
- `.gitignore` — ensures `.env` is not committed
- `.env.example` — template for environment variables

