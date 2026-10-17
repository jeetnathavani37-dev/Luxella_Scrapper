# Gender showcase homepage section (Culture Circle-style)

**Goal:** a mobile-first homepage block with a MEN/WOMEN switch, a brand-circle scroller, category tabs and
swipeable product cards (wishlist and quick add). It uses real Shopify products and the Luxella palette.

**Why now:** the founder supplied a standalone prototype (Tailwind CDN, hardcoded products) as the visual
reference and asked for a production Liquid version (2026-10-17). The audit found:
- no gender data (`tag:men` = 0, `tag:women` = 0, no category or metafield);
- women-heavy collections;
- men stock only reachable by vendor (Supreme 8, Casio 6, Jordan 5, Nike 4 in stock);
- no wishlist app installed.

## In scope
- `sections/luxella-gender-showcase.liquid` contains:
  - search (reuses Dawn `predictive-search`);
  - the gender switch;
  - the hero (Blackletter or Cormorant italic);
  - brand circles;
  - category tabs;
  - the product rail.
- The switch is configured with blocks in the theme editor:
  - `gender` (max 2);
  - `brand` (a collection or a vendor);
  - `tab` (a collection or a vendor).
  - A vendor uses Shopify's built-in `/collections/vendors?q=` page, so no store write is needed.
- `sections/luxella-showcase-rail.liquid` renders a tab's products lazily through the Section Rendering API.
- `snippets/luxella-showcase-card.liquid` is the card:
  - an image track with dots and a wishlist heart;
  - quick add: 1 variant goes straight to `/cart/add`, more than 1 opens the Dawn quick-add modal, sold out shows a label;
  - vendor (cleaned by `snippets/luxella-vendor-name.liquid`), title and one ₹ price (the existing `price` snippet,
    so there is no fake compare-at).
- Wishlist:
  - stored in localStorage as product handles, with no customer data;
  - shown on `templates/page.wishlist.json` (`sections/luxella-wishlist.liquid` plus `luxella-wishlist-card.liquid`).
- `assets/luxella-showcase.css` (scoped under `.lx-showcase`) and `assets/luxella-showcase.js` (vanilla, about 250
  lines).
- `templates/index.json`: the new section goes first. The existing sections and their settings are unchanged.

## Out of scope
- Creating Men/Women collections or tagging products (store writes, separate spec).
- Customer-account wishlist sync or a wishlist app.
- Replacing the global header. The cart, account and menu stay as they are.
- Any EMI, discount, delivery or badge claims.

## Acceptance checks
1. `python test_luxella_mcp.py` passes (repo self-check; theme files do not affect it).
2. Theme files are uploaded only to a NEW unpublished duplicate of the live theme. The live theme id `189163569325`
   is never written. Afterwards a `themes` query shows the live theme still `MAIN` and unchanged (`updatedAt`).
3. The duplicate's preview at 390px and 1280px renders:
   - the switch toggles the panel and theme;
   - tabs lazy-load products;
   - the heart persists after a reload;
   - quick add on a 1-variant product updates the cart, and on a multi-variant product opens the modal.
4. No `cdn.tailwindcss.com`, no hardcoded product data, no "% off", "EMI" or "XPRESS" strings in the new files.

## Writes to production
- One `themeDuplicate` (creates an unpublished theme). To undo, delete that theme.
- `themeFilesUpsert` on that duplicate only.
- No product, collection, page or customer writes.

## Risks
- **Thin Men view:** men stock is thin, so Men tabs show few products. Mitigation: vendor tabs. The real fix needs
  Men collections (separate spec).
- **Nested scrolling:** the image track sits inside a horizontal rail. Scroll chaining hands the gesture back to the
  rail at the ends.
- **Extra font:** the Blackletter font is a third typeface. It loads only for the hero, subset with `text=`, and uses
  `display=swap`.

## Rollout
Duplicate → upload → preview checks → founder review → the founder publishes when happy. Claude never publishes.
