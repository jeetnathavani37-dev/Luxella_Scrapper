# Push: stop "statement timeout" on the pending-products query

**Goal:** The scheduled "Push Products to Shopify" runs succeed again, so the products that are ready reach the
store every few hours, not just a trickle through Auto Pilot.

**Why now (read-only data, 2026-10-07):**
- **The scheduled push has not succeeded since 2026-10-05 21:41 UTC.**
  - The last 2 runs (37550709621 at 00:12, 37600320629 at 09:23 UTC) failed after about 20 s. The traceback is in
    `fetch_pending_products` (`shopify_push.py:97`): `APIError 57014 canceling statement due to statement
    timeout`.
  - The 2 runs before those were cancelled at the 30-minute job timeout.
- **7,241 products are eligible and waiting:** not pushed, not duplicate, price > 0, have a name and an INR
  price. Only **351 were pushed in the last 24 h**, by Auto Pilot. In the 72 h window it was 5,472.
- **Timing loop:** the same filter query was run read-only from the server (`order("id").range(...)`):

  | Query | Cache | Time |
  |---|---|---|
  | id column only | cold | **6.2 s** |
  | 1,000 rows with all columns (~1.5 MB) | cold | 2.3 s |
  | the same query again | warm | 0.5–1.1 s |

  The cost is the **filter scan**, not the payload: there is no index for `pushed_to_shopify = false AND
  is_duplicate IS NULL`, so Postgres walks the `id` index across all 59k rows checking each one. When a scrape or
  sync is writing at the same time, the scan goes past the API statement timeout.
- **A second bug:** the workflow asks for `BATCH_SIZE=2000`, but PostgREST returns at most 1,000 rows. The run
  silently gets half.

## In scope
1. **A partial index in Supabase.** It is a schema change, so the founder runs it in the Supabase dashboard SQL
   editor. The Supabase MCP has no access to this project.

   ```sql
   -- check first (read-only):
   select indexname, indexdef from pg_indexes where tablename = 'products';
   -- then (no table lock, no data change):
   create index concurrently if not exists products_push_pending_idx
     on products (id) where pushed_to_shopify = false and is_duplicate is null;
   ```

   The remaining filters (price > 0, name, `selling_price_inr`) are checked on the few thousand rows the index
   returns.
2. **`shopify_push.fetch_pending_products`:**
   - **Retry:** on APIError code `57014` (statement timeout) or a 5xx/connection error, retry up to 3 tries with
     backoff (10 s, 30 s). Any other error still fails at once.
   - **Batch cap:** the batch is capped at 1,000 rows (the PostgREST maximum). The workflow default
     `BATCH_SIZE` becomes `1000`, so the number the log shows is the number it really gets.
   - The query itself (filters, `order("id")`) is unchanged, so the MCP preview and apply still see the same
     rows.
3. **Offline tests in `test_luxella_mcp.py`:**
   - a fake client that times out once and then returns rows: the retry works;
   - a non-timeout error is not retried;
   - a limit of 2,000 is sent as `range(0, 999)`.
4. A `docs/DECISIONS.md` line recording the index: why it exists and how to drop it.

## Out of scope
- Making the push loop itself faster: about 1 s per product plus the inventory calls, the 30-minute job timeout,
  and the per-run fingerprint lookup. The 30-minute cancellations don't lose work, because each product is
  marked pushed one at a time. Change it later if the scheduled runs still fall behind once the query is fast.
- Auto Pilot and the other workflows' schedules.
- Pushing the backlog faster or by hand. The next scheduled runs pick it up at 1,000 per run, 4 runs a day, plus
  Auto Pilot.
- `shopify_bg_removal.fetch_pending_products`, which is a different query.

## Acceptance checks
1. `ruff` and `test_luxella_mcp.py` pass, CI is green, and the reviewer's verdict is OK.
2. **After the founder creates the index:**
   - `select indexname from pg_indexes where indexname = 'products_push_pending_idx'` returns 1 row;
   - the read-only timing loop (`id`-only, cold range) goes from about 6 s to **under 1 s**.
3. **The next scheduled push run** (or one `workflow_dispatch` with the default batch, after the founder says
   OK) gets past `fetch_pending_products`. The log shows "1000 products check/push kar rahe hain" and `[OK]`
   lines.
4. **The daily report** (`daily_report.py`) shows no "FAILED Push Products to Shopify" the next morning, and the
   eligible-pending count goes down day by day (from 7,241 today).

## Writes to production
- **Supabase schema:** 1 partial index, created by the founder in the SQL editor.
  - It changes no data and takes no table lock (`concurrently`).
  - Size is small: only unpushed, non-duplicate rows, about 9.6k entries.
  - **Undo:** `drop index concurrently products_push_pending_idx;`
- **Code:** read path only (retry + cap). Push writes to Shopify and Supabase as before. This PR adds no new
  write path.

## Risks
- **The index doesn't help** because the planner ignores it. Check 2 measures it right away; then
  `analyze products;` (read-only stats).
- **Writes slow down a little** (index upkeep on insert/update of `pushed_to_shopify`). This is negligible at
  this size.
- **A retry hides a real outage.** After 3 tries it still raises, so the daily report shows FAILED as before.
- **`create index concurrently` fails half-way** (for example the dashboard times out). That leaves an INVALID
  index. Drop it and re-run. The check query shows it.

## Rollout
1. The founder approves the spec.
2. The founder runs the check + create SQL. I verify check 2 read-only.
3. PR: code (retry + cap + workflow default + tests). Then reviewer, CI, and the founder's merge.
4. Watch the next scheduled push run (check 3) and the next morning's daily report (check 4).
