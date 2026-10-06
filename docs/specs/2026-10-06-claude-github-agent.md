# Coding agent on GitHub: "@claude" issues → PRs

**Goal:** The founder writes a task as a GitHub issue or comment with `@claude`. A Claude Code agent then
writes the code and tests on a `claude/…` branch, pushes it, and replies with a "create PR" link plus the
test/ruff output. The founder taps the link to open the PR. CI and the reviewer check it, and the founder
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
     PR events count only for PRs **from this repo**: a "Block fork PRs" step fails the job on a fork PR.
     Otherwise the action would check out and run the fork's code with the tokens present (reviewer, 2026-10-06).
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
     - the allowed tools cover the repo's own checks (`python test_luxella_mcp.py`, `ruff check`, read-only git).
       `requirements-dev.txt` is installed in a step before the agent;
     - `--disallowedTools` blocks Edit/Write under `.github/**`;
     - a short system prompt: follow CLAUDE.md, work only on the `claude/*` branch and never push to `main`, run
       the offline test and ruff before pushing, write production code dry-run by default, never edit `.github/`,
       and keep bidding logic out.
   - **App token scope:** `additional_permissions: actions: read`, so the token is scoped to contents, PRs,
     issues and actions-read, with **no workflows permission**. The agent can't push `.github/workflows/*`.
     Any workflow on a branch would otherwise get every repo-level production secret.
   - `include_comments_by_actor` is set to the owner, so other people's comments never enter the agent's context.
   - Concurrency is set at job level, so skipped runs (strangers' or the bot's comments) can't cancel a queued
     founder request.
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
3. **Test task:** an issue says `@claude add a one-line docstring to repair_variant_stock.split_fresh`. This only
   works after `claude.yml` is on `main`, because the action validates the workflow against the default branch.
   - The agent replies on the issue with a `claude/…` branch, a create-PR link and the test/ruff output.
   - The founder opens the PR. CI runs on it and is green.
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
- **Agent edits CI or workflows to make checks pass, or to read secrets.** Repo-level production secrets
  (Supabase service key, Shopify client secret, Firecrawl, Gemini, proxies) are readable by **any** workflow on
  **any** branch, and none of the 15 prod workflows uses an `environment:`. Mitigations here:
  - the app token has no workflows scope (`additional_permissions`);
  - `--disallowedTools` blocks `.github/**`;
  - the system prompt says so;
  - the reviewer flags any `.github/` change.

  **Recommended follow-up (separate PR, founder clicks Settings → Environments):** move production secrets into
  an environment `production` limited to `main`, and add `environment: production` to the prod workflows. Then no
  branch workflow can read them at all.
- **Fork PRs.** On an `issue_comment` for a fork PR, the action checks out the fork's code. The "Block fork PRs"
  step fails first, and the PR-review events are filtered to same-repo PRs in the job `if:`.
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
