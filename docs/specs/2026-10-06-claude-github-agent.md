# Coding agent on GitHub: "@claude" issues → PRs

**Goal:** The founder writes a task as a GitHub issue or comment with `@claude`. A Claude Code agent then
creates a branch, writes the code and tests, and opens a PR. CI and the reviewer check it, and the founder
merges from the phone. No terminal session is needed for routine code work.

**Why now:**
- CI is live (#29) and runs ruff, the offline test and gitleaks on every PR.
- The server can push with a repo-scoped token, and the repo has a reviewer agent plus CLAUDE.md rules.
- Today every code change needs a live Claude Code session on the server. In this session alone, 6 PRs (#25–#30)
  were opened by hand. The routine part of that (write code, run tests, open PR) can run on GitHub instead.

## In scope
1. **`.github/workflows/claude.yml`** using the official `anthropics/claude-code-action@v1`. No download is
   needed; GitHub runs it.
   - **Triggers:** `@claude` in a new issue (title or body), an issue comment, a PR review comment or a PR review.
   - **Who can trigger:** only users with write access to the repo, i.e. the founder. This is the action's default.
     `allowed_non_write_users` and `allowed_bots` are **never** set, because the repo is **public** and anyone can
     open issues.
   - **Auth:** `CLAUDE_CODE_OAUTH_TOKEN` from the founder's Claude subscription (`claude setup-token`), so there's
     no API bill.
   - **Permissions:** `contents: write`, `pull-requests: write`, `issues: write`, `id-token: write` (for the Claude
     GitHub app), `actions: read` (so it can read CI results).
   - **Secrets the job can see:** only `CLAUDE_CODE_OAUTH_TOKEN`. **No** Supabase, Shopify or Firecrawl secrets
     are passed. The agent has no way to write to production.
   - `claude_args`:
     - `--max-turns` capped at 30, plus a job `timeout-minutes` of 30;
     - the allowed tools cover the repo's own checks (`python test_luxella_mcp.py`, `ruff check`, `pip install -r
       requirements-dev.txt`);
     - a short system prompt: follow CLAUDE.md, open a PR and never push to `main`, run the offline test before
       the PR, write production code dry-run by default, and keep bidding logic out.
2. **Claude GitHub app** installed on `Luxella_Scrapper` only (https://github.com/apps/claude). The founder does
   this in the browser.
3. **Branch protection on `main`.** The founder clicks this in Settings → Branches:
   - require a pull request;
   - require the status check `checks (ruff, offline test, gitleaks)` to pass;
   - block force pushes and deletion.

   Then neither the agent nor a mistake can put code on `main` without a PR and green CI.
4. **Issue template "Agent task"** (`.github/ISSUE_TEMPLATE/agent-task.md`) with goal, files, acceptance checks
   and "production writes: none". This gives the agent a spec-shaped task.

## Out of scope (later, separate approval)
- **Scheduled agents** (weekly dependency PRs, daily stock-sync health issues). They come in phase 2, after a
  week of the manual `@claude` flow.
- **Auto-merge** of any kind. The founder always merges.
- Giving the agent any production secret, or letting it run repair, push or sync workflows.
- Running agents on the server (cron `claude -p`). GitHub runners are isolated, and the server holds keys.

## Acceptance checks
1. `actionlint` reports 0 errors for `claude.yml`. CI is green on the PR that adds it.
2. Branch protection is on. A direct `git push origin main` from the server is **rejected**.
3. **Test task:** an issue says `@claude add a one-line docstring to repair_variant_stock.split_fresh and open a PR`.
   - The agent replies on the issue.
   - A PR appears from a `claude/…` branch.
   - CI runs on it and is green.
   - The diff touches only that function.
4. A comment `@claude …` from a non-collaborator account (a second test account, or the founder's check of the
   action log) is **ignored**.
5. The workflow log shows no secret values. The job's env has no `SUPABASE_*` or `SHOPIFY_*`.
6. The `reviewer` agent verdict on the `claude.yml` PR is `OK to merge`.

## Writes to production
None. The workflow only creates branches, PRs and comments in this repo. Undo: delete `claude.yml` and uninstall
the app.

## Risks
- **Prompt injection from public issues.** Someone writes instructions into an issue the founder later tags.
  Mitigations:
  - only write-access users trigger the agent;
  - it has no production secrets;
  - every change is a PR behind CI, the reviewer and the founder's merge.
  - The founder should tag `@claude` only on issues they wrote or read.
- **Subscription usage.** Each run uses the founder's Claude plan limits. The caps are max-turns 30 and a
  30-minute timeout. The founder tags tasks one at a time.
- **Agent edits CI or workflows to make checks pass.** Workflow files need the `workflows` permission, which the
  Claude app has, so the reviewer must flag any `.github/` change in an agent PR. The system prompt says not to
  touch `.github/` unless the task says so.
- **The repo is public.** All scraper and business code is visible to anyone. That's a separate decision for
  the founder: making it private costs nothing extra, but Actions then gets 2,000 free minutes a month instead
  of unlimited. Not changed in this spec.

## Rollout
1. Founder: install the Claude GitHub app on this repo, run `claude setup-token` in an SSH terminal, and add
   repo secret `CLAUDE_CODE_OAUTH_TOKEN` (Settings → Secrets → Actions). The token is never pasted in chat.
2. A PR adds `claude.yml` plus the issue template. Reviewer, CI, then the founder merges.
3. Founder: enable branch protection (acceptance check 2).
4. The test task (check 3). Then one real small task from the pending list.
5. After a week of use, a phase-2 spec for scheduled agents.
