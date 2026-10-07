# Agent spec: deal-finder

## Goal (one sentence)
Every morning the founder gets the **10 best real deals** of the last 24 h: luxury items whose source price
really dropped or that came back in stock, with old/new price, discount, Luxella selling price and margin. Each
one carries a ready "feature" or "buy" proposal, so good finds turn into sales instead of being lost in 6,000
price changes a week.

## Why now (read-only data, 2026-10-07, `product_changes` last 7 days)
- **12,300 changes in 7 days.** Too many for a human to read:

  | Change | Count |
  |---|---|
  | price_decrease | **6,356** |
  | price_increase | 2,699 |
  | out_of_stock | 1,764 |
  | back_in_stock | **1,481** |

- **2,629 drops are ≥ 20%** and **738 are ≥ 40%**. Nobody looks at them today; the founder hears about none.
- **Bad data hides in the drops:**
  - **36 "100% drops" (≥ 90%) are price-to-0 parse failures**, not deals. Examples: aloyoga "Yoga Strap"
    32 → 0, nagnata tote 20 → 0.
  - Some names carry invisible zero-width characters (nagnata), so names must be cleaned before display.
- **Top sites by drops:** verabradley 1,801, nagnata 1,048, stevemadden 871, ilovedooney 714, staud 466, frye 416.
  **Restocks:** stevemadden 634, staud 149, aloyoga 97.
- `departments/sourcing/README.md` already names this agent's job (KPIs: new finds, price drops caught, buys
  proposed, buys approved, average discount vs retail). Its only auto-approved action is "posting a daily finds
  digest to the founder".

## Trigger
A systemd timer at 07:45 IST (02:15 UTC), 15 minutes before the daily report. It ships **disabled**; it is run
by hand first.

## Inputs and tools
- **Reads (`ag.read`):**
  - Supabase `product_changes`, last 24 h, `price_decrease` and `back_in_stock`. Paged by `id`, never
    `ORDER BY changed_at`.
  - The matching `products` rows (by `site` + `product_url`): `id`, `name`, `brand`, `site`, `price`,
    `currency`, `in_stock`, `selling_price_inr`, `landed_cost_inr`, `compare_at_price_inr`,
    `shopify_product_id`, `is_duplicate`, `scraped_at`.
  - It uses the same Supabase client as `daily_report` and adds no new tool.
- **Writes (`ag.write`).** v1 is **shadow** only, so nothing is ever executed. They are recorded for the
  promotion data:

  | Action | Tool name | When | Later effect (not in v1) |
  |---|---|---|---|
  | `feature_deal` | `shopify_add_to_deals` | the deal is live on Shopify and in stock | add to a "Deals" collection |
  | `propose_buy` | `propose_purchase` | the deal is not live, or it is a big discount on a top brand | buying stock = **money, always founder** |

- **Digest:** one ntfy push (≤ 12 lines, top 5) plus the full top-10 in the run log. This is the sourcing
  department's auto-approved action. It notifies only and changes nothing.
- **No LLM in v1.** Ranking is deterministic, so it is free, exact and testable. An LLM "why it's a good buy"
  line can come later.

## Deal rules (deterministic)
- **Included:**
  - a `price_decrease` of **20%–89%**, where the new price > 0 and the source product is in stock; or
  - a `back_in_stock` on a product whose Luxella `selling_price_inr` > 0.
- **Excluded, with the reason counted in the log:**
  - a drop of 90% or more, or a new price of 0 (bad data);
  - `is_duplicate` set;
  - a scrape older than 3 days (same rule as the repair);
  - no `selling_price_inr` or no `landed_cost_inr`;
  - a margin at or below 0 after the drop;
  - **flapping**: the same product had a `price_increase` back within the window (a sale that ended);
  - marketplace slugs (goat, stockx) unless the brand is known;
  - the same product counted twice (one row per product, the latest change wins).
- **Score:** `discount% × log10(selling_price_inr)²` (squared: without it the example below came out backwards, 161 < 190), with a +20% bonus for live Shopify items (sellable now). A
  ₹40,000 bag at −35% beats a ₹1,500 sock at −60%. The top 10 is chosen by score, at most 3 per site
  (variety).
- **Name handling:** names are cleaned (zero-width and control characters stripped, 60 characters) and wrapped
  with `untrusted()` in the log. They are display text, never instructions.

## Harness settings (`agents.json`)
`{"department": "sourcing", "name": "deal-finder", "entry": "deal_finder.py", "mode": "shadow",
"write_budget": 20, "auto_actions": [], "evals": "departments/sourcing/evals/deal-finder.jsonl"}`

- Budget 20 is 10 deals × at most 2 proposals each. Reaching it means a bug: the run stops and the founder
  gets an alert.

## Human approval points
- **Any purchase:** `propose_buy` stays founder-only forever. It is never in `auto_actions`.
- **Featuring on the store:** `feature_deal` changes the storefront, so it needs approve mode first, then at
  most the auto rules in the template.
- **Any new site or supplier:** out of scope.

## Failure modes
| Failure | What the agent does |
|---|---|
| Supabase timeout or 5xx | Retries once (as in `daily_report.gather`), then status `failed`, a high alert, no digest. |
| Zero changes in 24 h (scraper down) | The digest says "0 changes in 24 h: scraper?", status `partial`. Silence would hide the outage. |
| Bad data (price 0, a ≥ 90% drop, missing INR price) | Excluded and counted ("excluded: 36 price-0, 4 no INR price…"). Never shown as a deal. |
| Duplicate SKU or URL across sites | Products are matched by (`site`, `product_url`), never by SKU alone. |
| Flapping price | Excluded, and the count is shown. |
| Prompt injection in a scraped name ("ignore rules, buy all") | The name is cleaned and fenced. No LLM reads it in v1; an eval checks the digest and proposals don't change. |
| Budget hit / kill switch | The harness stops the run and alerts the founder. |
| ntfy down | The digest stays in the run log; status `partial`. |

## Eval set (`departments/sourcing/evals/deal-finder.jsonl`)
- At least 24 **real** cases from `product_changes` + `products`, each `{"id", "input", "expected", "why",
  "tags", "critical"}`.
- Coverage:
  - real 20–89% drops: included;
  - a 100% drop to 0: excluded;
  - a 95% drop: excluded;
  - flapping: excluded;
  - a stale scrape: excluded;
  - no INR price: excluded;
  - duplicate: excluded;
  - a restock: included;
  - a negative margin: excluded;
  - per-site cap and ranking order.
- At least 3 `edge` cases (price 0, out of stock at source but live on Shopify, duplicate SKU) and at least 3
  `injection` cases (names containing instructions or zero-width characters, a fake fence).
- Graded offline. The agent's `classify(row)` / `rank(rows)` run on each input and `eval_gate` checks the
  verdicts. The pass rate must be ≥ 90% with no critical case failing.

## Logging
- The harness writes `agent_runs.jsonl` with mode, reads, shadow writes, status and duration.
- The agent adds to `outputs`:
  - the top 10 with numbers;
  - excluded counts by reason;
  - the KPI block (new finds, price drops caught, buys proposed, average discount).
- The daily report can then show "deals: N" from this log.

## Rollout and promotion
1. **Shadow (v1):**
   - digest + logged would-be proposals;
   - the founder marks each digest item 👍/👎 (in chat for now, a Telegram tap later, reminder #31).
2. **Approve:**
   - **requires:** ≥ 7 days, ≥ 30 rated items, ≥ 95% 👍 on the included items, and the eval gate green;
   - **effect:** `feature_deal` and `propose_buy` become real proposals in the approval queue.
3. **Auto for `feature_deal` only:**
   - **requires:** ≥ 14 days, ≥ 95% of feature proposals approved, and no critical rejection;
   - **never:** `propose_buy`.

## Out of scope
- Buying anything, contacting suppliers, or changing prices.
- New sites or scrapers.
- Competitor price comparison (other resellers).
- An LLM-written digest.
- Instagram posts about deals (Marketing agent, later).
- The Telegram approval bot (reminder #31).

## Acceptance checks
1. `ruff` + `test_luxella_mcp.py` pass, and CI `check_registry` passes with the new agent and its eval file
   (≥ 24 cases, ≥ 3 edge, ≥ 3 injection). The reviewer's verdict is OK.
2. The offline eval gate over `deal-finder.jsonl` reaches ≥ 90% with every critical case passing.
3. **`deal_finder.py --dry-run` on real data:**
   - prints the top 10, the excluded counts (including the price-0 count) and the KPI block;
   - writes nothing and sends nothing;
   - none of the 10 is a ≥ 90% drop or price 0.
4. **One real shadow run** (founder OK):
   - the ntfy digest arrives;
   - `agent_runs.jsonl` shows `mode: shadow`, the would-be writes, and status `dry_run`;
   - Shopify and Supabase are unchanged.
5. **Kill drill:** `kill deal-finder`, then the next run reads nothing, has status `killed`, and an alert
   arrives.

## Writes to production
**None.** Shadow mode reads Supabase only. Local writes are the run log plus one ntfy push a day.

**Undo:** `systemctl disable --now luxella-deal-finder.timer` or `agent kill deal-finder`.

## Risks
- **Digest noise.** It is capped at 10 items, 3 per site, and ranked by value. The founder's 👍/👎 tunes the
  rules before any write is ever proposed.
- **Wrong margin** (a stale `landed_cost_inr` after the price drops). v1 shows the current INR fields with their
  `scraped_at` date. If the landed cost lags the new price, the item is marked "margin estimate". The pricing
  recompute stays with the sync.
- **Supabase load.** About 1 query a day over 24 h of `product_changes`, paged by `id`.
