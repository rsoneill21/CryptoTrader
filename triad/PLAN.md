# PLAN — Triad Agent Setup (Codex + Gemini)

## Objective
Set up Codex CLI and Gemini CLI as operational agents in the Triad workflow, with local testing first, then full CI/CD automation via GitHub Actions.

## Non-goals
- Building a custom orchestration framework
- Replacing manual human-in-the-loop control
- Auto-merging PRs without human approval

## Assumptions
- Codex CLI (`codex`) is installed or installable via npm/pip
- Gemini CLI (`gemini`) is installed or installable
- User has OpenAI account with Codex access
- User has Google AI API key for Gemini
- GitHub repo: `git@github.com:rsoneill21/triad.git`

---

## Phase 1: Local Setup & Validation

### 1.1 Environment Configuration
- [ ] Create `.env` file in repo root (gitignored)
- [ ] Add `.env` to `.gitignore` if not present
- [ ] Define required variables:
  ```
  OPENAI_API_KEY=<your-openai-key>
  GEMINI_API_KEY=<your-gemini-key>
  GITHUB_TOKEN=<your-github-pat>
  ```

### 1.2 Codex CLI Setup
- [ ] Install Codex CLI: `npm install -g @openai/codex` (or applicable method)
- [ ] Verify installation: `codex --version`
- [ ] Authenticate: `codex auth` or configure via env var
- [ ] Test basic prompt: `codex "explain what PLAN.md contains"`
- [ ] Document install steps in `docs/CODEX_SETUP.md`

### 1.3 Gemini CLI Setup
- [ ] Install Gemini CLI: `npm install -g @google/gemini-cli` (or applicable method)
- [ ] Verify installation: `gemini --version`
- [ ] Authenticate via API key or `gcloud` if using Vertex
- [ ] Test basic prompt: `gemini "summarize this text: hello world"`
- [ ] Document install steps in `docs/GEMINI_SETUP.md`

### 1.4 Wrapper Scripts (Local Automation)
- [ ] Create `scripts/` directory
- [ ] Create `scripts/feed-codex.sh`:
  - Reads current task from PLAN.md (parses `- [ ]` items)
  - Sends task context + relevant files to Codex
  - Outputs Codex response to stdout
- [ ] Create `scripts/review-diff.sh`:
  - Runs `git diff main..HEAD` (or specified branches)
  - Sends diff + PLAN.md + DECISIONS.md context to Gemini
  - Outputs review to `reviews/<branch>-review.md`
- [ ] Make scripts executable: `chmod +x scripts/*.sh`

### 1.5 Local Validation
- [ ] Run `feed-codex.sh` with a sample task — verify Codex responds appropriately
- [ ] Run `review-diff.sh` with a sample diff — verify Gemini produces punch list
- [ ] Manually verify outputs make sense before proceeding to Phase 2

---

## Phase 2: CI/CD Automation (GitHub Actions)

### 2.1 GitHub Secrets Configuration
- [ ] Add repository secrets in GitHub:
  - `OPENAI_API_KEY`
  - `GEMINI_API_KEY`
- [ ] Verify `GITHUB_TOKEN` is available (auto-provided by Actions)

### 2.2 Gemini Review Workflow
- [ ] Create `.github/workflows/gemini-review.yml`
- [ ] Trigger: `pull_request` opened/synchronize against `main`
- [ ] Steps:
  1. Checkout repo
  2. Install Gemini CLI
  3. Fetch PR diff via `gh pr diff ${{ github.event.pull_request.number }}`
  4. Run Gemini review with diff + PLAN.md context
  5. Post review as PR comment via `gh pr comment`
- [ ] Test with a sample PR

### 2.3 Review Output Format
- [ ] Gemini prompt should produce structured output:
  ```
  ## Review: PR #<number>

  ### Alignment with PLAN.md
  - [ ] Task X: Implemented / Partial / Missing

  ### Issues Found
  - **Severity**: High/Medium/Low
  - **Description**: ...
  - **Suggestion**: ...

  ### Security Concerns
  - ...

  ### Suggested Improvements
  - ...
  ```

### 2.4 Codex Task Runner (Future)
- [ ] Create `.github/workflows/codex-implement.yml` (manual trigger)
- [ ] Input: Task ID or description from PLAN.md
- [ ] Steps:
  1. Checkout feature branch
  2. Run Codex with task context
  3. Commit changes to branch
  4. Open PR or push to existing branch
- [ ] Requires careful guardrails — human approval before merge

### 2.5 Workflow Documentation
- [ ] Document CI/CD setup in `docs/CI_CD.md`
- [ ] Add troubleshooting section for common failures
- [ ] Document how to manually trigger workflows

---

## Phase 3: Refinement & Guardrails

### 3.1 Prompt Engineering
- [ ] Create `prompts/codex-task.txt` — template for Codex task prompts
- [ ] Create `prompts/gemini-review.txt` — template for Gemini review prompts
- [ ] Include repo context (file structure, conventions) in prompts

### 3.2 Guardrails
- [ ] Add validation that Codex only modifies files listed in PLAN.md
- [ ] Add check that no secrets are committed (use `gitleaks` or similar)
- [ ] Require human approval for any PR opened by automation

### 3.3 State Sync
- [ ] Script to update AGENTS_STATE.md after Codex completes a task
- [ ] Script to update Known Issues after Gemini review

---

## Acceptance Criteria

### Phase 1 Complete When:
- [ ] Both CLIs installed and authenticated locally
- [ ] `feed-codex.sh` successfully sends task and receives response
- [ ] `review-diff.sh` successfully reviews diff and outputs punch list
- [ ] Setup documented in `docs/`

### Phase 2 Complete When:
- [ ] PR triggers Gemini review automatically
- [ ] Review posts as PR comment with structured format
- [ ] Codex workflow exists (even if manual trigger only)
- [ ] GitHub secrets configured and working

### Phase 3 Complete When:
- [ ] Prompt templates refined based on real usage
- [ ] Guardrails prevent unauthorized file changes
- [ ] State files update automatically

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Codex modifies files outside PLAN.md scope | Script validates changed files; flags violation |
| Gemini API rate limited | Retry with backoff; fail gracefully with message |
| PR has no meaningful diff | Skip review; post "No changes to review" |
| Credentials missing in CI | Workflow fails fast with clear error message |
| Codex produces invalid code | Gemini catches in review; Codex fixes |

---

## Test Plan

### Local Tests
1. Run `feed-codex.sh` with empty task — should handle gracefully
2. Run `review-diff.sh` with no changes — should report "nothing to review"
3. Run both scripts with invalid API keys — should fail with clear error

### CI Tests
1. Open PR with trivial change — verify Gemini comments
2. Open PR with deviation from PLAN.md — verify Gemini flags it
3. Manually trigger Codex workflow — verify it creates correct changes

---

## Dependencies

```
Phase 1 ─────► Phase 2 ─────► Phase 3
(local)       (CI/CD)        (refinement)
```

Phase 2 blocked by Phase 1 completion.
Phase 3 can begin once Phase 2 is functional.

---

## Open Questions
1. Exact Codex CLI installation command (verify latest docs)
2. Exact Gemini CLI installation command (verify latest docs)
3. Preferred PR comment format (threaded vs single comment)
