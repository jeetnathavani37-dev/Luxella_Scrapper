# Daily Luxella report: the first agent (read-only)

**Goal:** Every morning at 08:00 IST the founder's phone gets one short Luxella health report (catalog numbers,
failed jobs, what to fix today). He no longer has to open GitHub, Supabase or Shopify to know whether the store is
healthy.

**Why now (read-only data, 2026-10-07 ~10:25 UTC):**
- **Supabase `products`:**
  - 59,103 rows. **49,518** pushed to Shopify: 31,306 in stock and **18,212** not in stock.
  - **237** pushed products have price 0 or null. PR #15/#16 guard new pushes, but these are already live data.
  - **9,875** pushed products were not re-scraped in the last 3 days (the stale-scrape gap).
  - 46,025 rows were scraped in the last 24 h.
  - 1,638 `product_changes` rows in the last 24 h.
- **GitHub Actions, last 24 h (32 runs):**
  - "Push Products to Shopify" failed 2× and was cancelled 1×.
  - "Auto Pilot" was cancelled 3× and "Backfill Product Images" 3×.
  - The repair failed 1× (Shopify 500, fixed in PR #33).
  - Nobody was told about any of these. The founder finds out only when he asks.
- **The building blocks already exist:**
  - `kpi-report` format and the catalog department's 5 KPIs in `departments/catalog/README.md`;
  - `packages/core/runs.log_run` and `approvals.list_pending`;
  - the ntfy push in `packages/core/approvals.py`;
  - the `luxella-freshness` systemd timer pattern.
- ROADMAP lists "Daily catalog health report" as an open item.
- This is the first agent on the "AI-led Luxella" path: read-only, free and safe. Later agents reuse its schedule,
  log and alert plumbing.

## In scope
1. **`daily_report.py`** (new, repo root). It is **deterministic, with no LLM**: every number comes from a query
   in the same run, as `kpi-report` requires.
   - **Supabase, exact counts** (`select id, count=exact, limit 1`; no `ORDER BY scraped_at/changed_at`):
     - pushed;
     - pushed and in stock (= products live);
     - pushed and out of stock;
     - pushed with price 0 or null;
     - pushed and stale for more than 3 days;
     - scraped in the last 24 h;
     - `product_changes` in the last 24 h.
   - **Shopify, one read call each:**
     - `productsCount(query: "status:active")`;
     - `productsCount(query: "status:active inventory_total:<=0")` = **OOS-but-live**.

     It uses `shopify_sync.get_access_token()` and only `query` operations.
   - **GitHub Actions**, read with the existing repo token file: runs in the last 24 h grouped by workflow, then
     failed / cancelled / succeeded. It lists the failed ones by name with a run link.
   - **Pending approvals:** count plus top 3 from `packages.core.approvals.list_pending()`.
   - **Catalog KPI block** in the `kpi-report` format:

     | KPI | Source | Target |
     |---|---|---|
     | products live | Supabase | `-` |
     | OOS-but-live | Shopify | `-` (founder 2026-10-07: sold-out listings stay live for SEO, so it is info and not an alert. 16,689 active products at 0 stock) |
     | synced today | `product_changes` 24 h | `-` |
     | failed syncs | failed Actions runs (cancelled = info line, not counted: Auto Pilot and Backfill cancel daily; reviewer PR #34) | ≤ 0 |
     | photo quality score | `n/a (source missing)` | – |

     Plus 2 extra lines under Highlights:
     - "price 0 live: 237 (target 0)";
     - "stale > 3 d: 9,875".
   - **7-day average:** from its own snapshots in `/root/luxella-ops/daily_report.jsonl`. It shows `-` until 7
     days exist.
   - **Status** follows the `kpi-report` rules (ok / watch / bad). Bad items go first.
   - **Missing source:** if a source fails (Supabase down, Shopify 5xx after retries, GitHub API error), that line
     says `n/a (source missing)` and the report is **still sent**. A partial report beats silence.
   - **Output:**
     1. it prints the full report;
     2. it appends a snapshot to `daily_report.jsonl`;
     3. it calls `log_run("catalog", "daily-report", status=ok|partial|failed, ...)`;
     4. it sends a **short** ntfy message (≤ 12 lines, the bad items first, priority high if anything is bad) to
        the existing topic. The full report goes in the log.
   - **Flags:**
     - `--dry-run` prints only: no ntfy, no snapshot.
     - `--no-push` writes the snapshot but sends no ntfy.
2. **systemd** `luxella-daily-report.service` + `.timer`:
   - runs at 02:30 UTC (= 08:00 IST), `Persistent=true` so a missed run catches up after a reboot;
   - env loaded like `luxella-freshness` (sourced, never printed);
   - the timer ships **disabled** (safe-writes: new schedules start off) and is enabled after the founder sees one
     report.
3. **Offline tests** in `test_luxella_mcp.py` with fake sources:
   - status rules (ok/watch/bad, `-` for no target);
   - a missing source gives `n/a`, the report is still built, and status is `partial`;
   - bad items come first;
   - the ntfy message is ≤ 12 lines;
   - the 7-day average ignores days that have no data;
   - `--dry-run` sends nothing and writes nothing.
4. **Docs:** a line in `departments/catalog/README.md` (lead agent: daily-report) and the ROADMAP item ticked.

## Out of scope
- **Any write** to Shopify, Supabase or GitHub, or any automatic fix. The report only says what to fix.
- **An LLM summary** ("Claude writes the highlights"). It could come later as v2 through headless Claude Code.
  v1 stays free and exact.
- Other departments' KPIs: finance, sales, marketing and so on. Their data sources don't exist yet.
- Photo quality score: no source yet.
- Telegram / WhatsApp / email delivery: ntfy only.
- Per-size stock drift. The repair and the relist own that; the report only shows their headline numbers.

## Acceptance checks
1. `ruff check .` and `python test_luxella_mcp.py` pass, CI is green, and the reviewer's verdict is OK.
2. **`daily_report.py --dry-run` on real data:**
   - prints all 5 catalog KPIs, the Actions summary and the approvals count;
   - the numbers match an independent query: pushed total within ±50 of the Supabase count above, which drifts
     with scrapes;
   - nothing is sent and nothing is written (`daily_report.jsonl` is unchanged).
3. **Missing-source check:** with `GITHUB_TOKEN_FILE` pointed at a missing file, the report prints
   `n/a (source missing)` for Actions, still completes, and `log_run` status is `partial`.
4. **One real push:** run `daily_report.py` (not dry-run) once by hand.
   - The founder confirms on his phone that the ntfy message arrived and is readable.
   - `agent_runs.jsonl` gets one `catalog/daily-report` line.
5. **Timer:** the founder says OK, then `systemctl enable --now luxella-daily-report.timer`, and
   `systemctl list-timers` shows the next run at 02:30 UTC. The next morning's run arrives without anyone
   touching it.
6. **Cost:**
   - Shopify uses 2 `productsCount` calls and Supabase about 9 count queries;
   - GitHub uses 1–2 API calls;
   - **0 LLM calls**.

## Writes to production
**None.** It reads Supabase, Shopify and GitHub. It writes only local files on the server
(`/root/luxella-ops/daily_report.jsonl`, `agent_runs.jsonl`) and sends one ntfy message a day.

**Undo:** `systemctl disable --now luxella-daily-report.timer`.

## Risks
- **ntfy.sh is public:** anyone who knows the topic name can read the messages.
  - The report has **business numbers only**: no customer data, no prices per customer, no secrets, no tokens, no
    URLs with keys.
  - The topic name is already a long random string, the same one approvals use. The founder can move to a
    self-hosted ntfy later.
- **Wrong numbers mislead the founder.** Every line names its source and the time. The acceptance check
  compares them to independent queries. Shopify `inventory_total` counts only tracked inventory; that is fine,
  because pushes set `tracked: true`.
- **Supabase or Shopify slowness at 02:30 UTC:** count queries are light. Shopify reads retry on 5xx in the same
  way as PR #33, and a failure gives `n/a` rather than no report.
- **Alert fatigue.** The message is ≤ 12 lines with bad items first. If everything is ok it is a 3-line "all
  good" plus the numbers.
- **Server down at 02:30 UTC:** `Persistent=true` runs it on boot. Uptime Kuma already alerts when the server is
  down.

## Rollout
1. Spec approved, then the planner writes slices, then the builder builds them (code + tests + units, timer
   disabled). Then reviewer, CI, PR and the founder's merge.
2. `--dry-run` on the server. The founder sees the printed report in chat (check 2 and check 3).
3. One real run, so the ntfy message reaches the phone (check 4).
4. The founder says OK, so the timer is enabled (check 5). Watch 3 mornings.
5. Later, with a separate spec: v2 with LLM highlights, and other departments as their data sources appear.
