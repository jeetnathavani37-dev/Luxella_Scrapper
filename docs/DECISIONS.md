# Decisions log
Format: date, decision, why, alternatives considered.

- 2026-10: Moved dev from Chromebook (2.7 GB RAM, 21 GB disk) to a Contabo VPS (8 GB RAM, 100 GB). Why: constant hangs. Alternative: resize Crostini disk (RAM still too low).
- 2026-10: Built luxella_mcp.py with 4 tools; writes only with confirm=True. Why: the founder approves anything touching production.
- 2026-10: Bid-pricing agent kept separate from the catalog MCP. Why: different risk profile and ownership.
- 2026-10: Access via SSH key + tmux session. Why: no repeated passwords, sessions survive disconnects.
- 2026-10: New cron schedules ship disabled until tested at small batch size. Why: avoid unreviewed bulk writes to the live store.
- Default agent framework: Claude Agent SDK reusing MCP tools. Why: tools already exist, no rewrite.
- 2026-10: Ruff (lint only, rules E4/E7/E9/F/B) + pre-commit (ruff check --fix on staged files, then the offline self-check) added. Why: catch real bugs before commit without a 38-file reformat diff. Alternatives: flake8/pylint (slower), ruff format now (deferred - widen one rule family per PR).
- 2026-10-06: gitleaks pre-commit hook (PR #25). Why: a leaked Shopify/Supabase key = someone else can change prices or read customers; one cheap check per commit. Alternative: GitHub secret scanning only (catches after push, not before).
- 2026-10-06: CI on GitHub Actions (`.github/workflows/ci.yml`) + `requirements-dev.txt`. Why: checks ran only on this server's pre-commit; any agent or person could open a PR that skips them. CI runs ruff, the offline self-check and gitleaks on every PR/push to main; pip-audit runs as an advisory job and weekly. `requirements-dev.txt` = `requirements.txt` + mcp, python-dotenv (needed by luxella_mcp.py/test, not by the scrapers) + ruff, pip-audit, all pinned. Alternatives: pre-commit.ci (third-party app access), installing the full server venv in CI (unpinned, 60+ packages).
