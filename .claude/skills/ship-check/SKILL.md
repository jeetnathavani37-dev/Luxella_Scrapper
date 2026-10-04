---
name: ship-check
description: Pre-merge checklist for any Luxella change - tests run, reviewer verdict, secrets scan, production-write safety, PR description and rollback. Use before saying "done", before opening a PR, and before every merge.
---

# Ship check

"Done" means every box below is checked **with output shown**. If you can't check something, say which box and why.

## Checklist
- [ ] **Scope:** the diff matches the approved spec or slice. No drive-by changes. The user's uncommitted files (e.g. `.gitignore`) are not staged.
- [ ] **Offline test:** `.venv/bin/python test_luxella_mcp.py` prints `ok`. Paste it.
- [ ] **Feature check:** every acceptance check in the spec was run with mocked or stubbed writes, or read-only real data. Results pasted (the `qa` agent).
- [ ] **Production writes:** none were run, or the full `safe-writes` procedure was followed: dry-run → approval → backup → small batch → verify.
- [ ] **Secrets:**
  - Nothing reads or prints `~/.luxella.env` or tokens.
  - `git diff --cached | grep -iE "key|token|secret|password"` shows only variable names.
- [ ] **Reviewer:** the `reviewer` agent's verdict is `OK to merge`, or its findings are fixed.
- [ ] **Commit:** one clear message for the slice, ending with the Co-Authored-By line.
- [ ] **Push:** to a branch, never `--force`, never straight to `main`.
  - No git credentials on this server: push files with the GitHub MCP `push_files`.
  - Then verify: `git fetch origin <branch> && git diff --quiet origin/<branch> HEAD -- <files> && echo IDENTICAL`.
  - The GitHub integration can't write `.github/workflows/*`. Give the YAML to the founder instead.
- [ ] **PR description:** problem (with numbers), fix, tests run with results, expected effect after merge, and how to roll back.
- [ ] **Merge only when the founder says so.** Afterwards: `git pull --ff-only`, delete the local branch, and update memory or docs if behaviour changed.

## Rollback
For anything that changes production data or the pipeline, the PR must say how to undo it:
- `git revert <merge-sha>`
- the backup file path
- or the Shopify admin steps
