# Storefront uplift: luxury-house presentation with reseller-grade trust

**Goal:** a buyer landing on any Luxella page sees a calm, editorial store and every answer an Indian luxury
buyer needs before paying (real price, authenticity, delivery date, duties, returns, payment, a human), without
"Sale" noise.

**Why now (benchmark + audit, 2026-10-10, `/root/backups/2026-10-10/benchmark/`, `ui-audit/`):**
- Mobile Lighthouse 41–54, LCP 6.4 s (target ≥ 80 / ≤ 2.5 s, BRAND.md §7).
- **"Sale" badge and strike price on every card and PDP**: the fake 35% compare-at (founder decision (b), BRAND.md §8).
  Price shows as "Rs. 13,299.00 INR".
- **Thin PDP:** one image, no delivery estimate, no authenticity line, no details, no cross-sell, no sticky add-to-bag.
  Every Indian reseller benchmarked has at least 4 of these.
- **Broken trust content:**
  - the refund policy cites an "Authenticity Guarantee" but `/pages/authenticity` is 404;
  - the shipping page says 3–4 weeks while the FAQ says 10–18 business days;
  - the FAQ is not linked anywhere.
- **Dead nav:** Collections, Concierge, Journal and The Edit all go to `/`.
- **Collections:** Handbags has 20,653 products, including boots and dresses. The cause is the rule
  `TAG = Handbag OR TYPE = Handbags`. Sold-out items are mixed in, and there are no filters beyond the Dawn default.
- **`impeccable detect` on the live store:** 18 anti-patterns.
  - Contrast: hero text over video at 1.1:1; gold `#B8975A` on paper `#F5F1EA` at 2.45:1, which fails even large text.
  - Other: gradient-text logo, all-caps body, width-animating transitions.
- **Gold budget:** 3 or more gold elements on the first screen (the limit is 2).

## In scope
Theme work happens on a **new unpublished duplicate** of the speed draft `188910305453`, which already holds the
font, CSS and hero speed fixes. Content pages are created **unpublished**.

1. **Price and cards**
   - One price in ₹ with Indian commas (`₹13,299`). No ".00", no "INR".
   - Hide the "Sale" badge and strike price in the theme until the compare-at (b) build gives real brand discounts.
     When that lands, show the brand discount quietly ("Was ₹x"), with no badge and no %.
   - Card: brand, name, price. Nothing else.
2. **PDP trust block**, under the price, as calm muted lines, each linking to its page:
   - landed price ("Duties and taxes included");
   - delivery date range;
   - authenticity line linking to "How we authenticate";
   - returns line;
   - payment line (UPI, cards, EMI);
   - "Can't find your size? We'll source it", which opens WhatsApp concierge (an ink icon, not the green bubble).
   - **The wording of every line is a founder decision (below).** Until it is approved, the block ships with placeholders
     on the draft only.
3. **PDP layout**
   - Gallery shows every product image at 4:5 with zoom.
   - Details accordion: description, style code (SKU), material/colour if present, shipping and returns, packaging.
   - Sticky add-to-bag on mobile.
   - "You may also like" using Shopify native recommendations (same brand or type).
   - Sold-out sizes are disabled and a size guide link is shown.
4. **Navigation and search**
   - Header: Bags, Shoes, Clothing, Accessories, Brands, New In, plus a persistent search field.
   - The new menu `main-menu-v2` is used only by the draft theme. The live menu is untouched.
   - The footer links FAQ, Shipping and duties, Returns, How we authenticate, About, Contact.
   - Concierge, Journal and The Edit are removed until they have real pages (no link to `/`).
5. **Collection pages**
   - Filters: brand, product type, size, price, availability (Shopify Search & Discovery native filters).
   - Sort by newest and by price.
   - "Available now" is the default view; sold-out items are reachable through the filter.
6. **Visual fixes from the audit**
   - Gold at most 2 per screen; the logo uses a solid colour (no gradient text).
   - Hero text gets an overlay to reach ≥ 4.5:1.
   - Gold text is never used on paper; the light-section accent becomes ink, with gold only on dark.
   - No all-caps body text; transitions use opacity/transform only.
   - Sans font per DESIGN.md: Inter with a system fallback, replacing Jost.
7. **Content pages (unpublished drafts)**
   - "How we authenticate" (fixes the 404).
   - "Shipping and duties", aligned to one delivery range.
   - Returns and FAQ, updated to match.
   - Copy is written with luxury-voice and passed through a de-slop pass.

## Out of scope (separate specs)
- **Compare-at (b) data build:** scrapers capture the brand's original price, then push and sync it. Next spec.
- **Handbags rule fix and product-type/tag cleanup** (boots in Handbags). This is a catalog data change; its own spec
  with dry-run.
- Reviews or ratings app, EMI provider, COD, a custom domain, Chatwoot go-live.
- Publishing the theme. **The founder publishes**; the MCP blocks theme publish anyway.
- Journal/editorial content, lookbooks, video shoots.

## Founder decisions — ANSWERED 2026-10-10
- **Delivery:** up to 4 weeks (align shipping page + FAQ).
- **Authenticity:** guaranteed via CheckCheck; full refund if an item is fake.
- **Duties:** included in the price ("customs duties and taxes included").
- **Returns:** keep current (refund only if not authentic/damaged; cancel within 12 h).
- **Payments:** standard Shopify checkout; the trust line shows only methods actually enabled — verify in checkout before it goes live.

### Original open questions
1. **Delivery range** shown everywhere. The shipping page says 3–4 weeks and the FAQ says 10–18 business days. Which is true?
2. **Authenticity promise:** the wording, and what happens if an item fails (full refund?).
3. **Returns:** today it is "only if not authentic or damaged; cancel within 12 h". Keep that?
4. **Payments:** which are actually on (UPI, cards, EMI, COD)?
5. **Duties:** are prices truly landed, including customs? The site already claims "Duties incl.".

## Acceptance checks
1. `impeccable detect <draft preview URL> --viewport 390x844` and at 1280: 0 gradient-text, 0 all-caps-body, 0
   layout-transition, 0 low-contrast on hero and price text. Paste the output.
2. `antislop-human/contrast-check.py` passes AA for every text/background token pair used.
3. Lighthouse mobile on the draft (home, collection, PDP): performance ≥ the speed-draft baseline and ≥ 80 on PDP,
   LCP ≤ 2.5 s, CLS ≤ 0.1. If 80 is not reached, report the number and the cause; don't claim done.
4. **Rendered HTML of 5 PDPs and 2 collections on the draft:**
   - no "Sale" text and no `<s>`/compare-at markup;
   - prices match `₹\d{1,3}(,\d{2})*,\d{3}` with no ".00 INR".
5. Every header and footer link on the draft returns 200 and none points to `/`.
6. PDP on the draft at 390px has:
   - the trust block (6 lines);
   - the details accordion;
   - sticky add-to-bag visible after scroll;
   - "You may also like" with ≥ 4 items;
   - all product images in the gallery.
   Screenshots at 390, 768 and 1280.
7. The Handbags collection on the draft shows "Available now" by default and its filters work. Measure: count shown
   vs total.
8. Live theme unchanged: `themes` shows MAIN = `156769255597` with the same `updatedAt` before and after.
9. `replica-diff` layout diff of the draft PDP vs the Balenciaga and Culture Circle PDP screenshots, as a report only.

## Writes to production
- **New unpublished theme** (a duplicate of `188910305453`). Undo: delete the theme.
- **New menu `main-menu-v2`.** Only the draft uses it. Undo: delete the menu.
- **Search & Discovery filters.** **This is a store-wide change, so the live theme's collection filters change too**
  (it adds filters; it removes nothing). It needs a separate "haan" before it is applied. Undo: remove the filters.
  Backup of the current filter list: `/root/backups/<date>/filters_before.json`.
- **New unpublished pages.** Undo: delete them.
- **No product, price or inventory writes.**

## Risks
- **Theme speed drop from the new PDP blocks.** Lighthouse is checked after every slice; a slice that drops it more
  than 5 points is reverted.
- **Hiding compare-at in the theme also hides real brand discounts** until the (b) build. Acceptable: today none are
  real.
- **The draft drifts from the live theme** if the live theme is edited meanwhile. Check `updatedAt` before publish.
- **Filter limits:** Search & Discovery caps the number of filter values. Brand has 40+ vendors, which is within limits;
  verify.
- **Placeholder trust copy shipped by mistake.** Placeholders are wrapped in a visible `[DRAFT]` marker, and a publish
  check greps for it.

## Rollout
1. The founder approves this spec and answers the 5 decisions (the build can start before the answers).
2. The planner writes slices, in order:
   1. duplicate theme plus price/card cleanup plus visual fixes;
   2. PDP layout plus trust block (placeholders);
   3. nav/footer/search plus menu v2;
   4. collection filters (separate OK);
   5. content pages plus final copy.
3. After each slice: impeccable, contrast, Lighthouse, screenshots, then the reviewer.
4. The founder previews the draft link on his phone and publishes it himself.
