# GEMINI — Review Instructions for {{PROJECT_NAME}}

> Instructions for Gemini when reviewing code changes.

---

## Review Scope

When reviewing PRs or diffs for this project, check:

### 1. Plan Alignment
- [ ] Changes match tasks in PLAN.md
- [ ] Only files listed in PLAN.md are modified
- [ ] Acceptance criteria are met

### 2. Code Quality
- [ ] Code is readable and follows project conventions
- [ ] No obvious bugs or logic errors
- [ ] Error handling is appropriate
- [ ] No hardcoded secrets or credentials

### 3. Security
- [ ] No injection vulnerabilities (SQL, XSS, command)
- [ ] Input validation where needed
- [ ] Authentication/authorization checks present
- [ ] Sensitive data handled appropriately

### 4. Testing
- [ ] Tests added/updated for new functionality
- [ ] Existing tests still pass
- [ ] Edge cases considered

### 5. Architecture
- [ ] Changes align with DECISIONS.md
- [ ] No unnecessary complexity added
- [ ] Dependencies are justified

---

## Review Output Format

```markdown
## Review: [PR/Commit Description]

### Plan Alignment
- Task X.X: [Implemented | Partial | Missing | Deviation]

### Issues Found
- **[High|Medium|Low]**: Description
  - File: path/to/file.ext:line
  - Suggestion: How to fix

### Security Concerns
- [None found | List concerns]

### Recommendations
- [Optional improvements, not blockers]

### Verdict
- [ ] Approve
- [ ] Request changes (list required fixes)
- [ ] Needs discussion (escalate to Claude)
```

---

## Project-Specific Rules

_Add project-specific review rules here after analysis._

---

## Escalation

Flag these to Claude (do not auto-approve):
- Architectural changes not in DECISIONS.md
- New dependencies added
- Changes to authentication/authorization
- Database schema changes
- API contract changes
