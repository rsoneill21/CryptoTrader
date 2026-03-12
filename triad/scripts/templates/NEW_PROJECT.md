# NEW PROJECT — {{PROJECT_NAME}}

> This file indicates a new project awaiting definition.
> Claude will run the Triad new project Q&A to populate the project spec.

---

## Status

**Project State:** Not yet defined

**Next Step:** Run the Triad new project Q&A with Claude

---

## Instructions for Claude

When you see this file, the user wants to create a new project from scratch.

Run the Q&A process defined in `/projects/triad/prompts/new-project-qa.md` to:
1. Understand what the user wants to build
2. Define the tech stack
3. Identify core features and MVP scope
4. Document constraints and requirements

After Q&A is complete:
1. Create `triad/PROJECT_SPEC.md` with the full specification
2. Create `triad/PLAN.md` with Phase 1 tasks
3. Create `triad/DECISIONS.md` with tech stack decisions
4. Update `triad/AGENTS_STATE.md` with the project goal
5. Delete this file (NEW_PROJECT.md)
6. Optionally scaffold the basic project structure

---

## For the User

Tell Claude one of these to get started:
- "This is a new project. Let's define it."
- "Run the Triad new project Q&A."
- "I want to build [brief description]."

Claude will ask questions to understand your project, then create the plan.
