# Luxella brand book

This is the single reference for everything about the Luxella brand: who we are, how we look, how we speak, what
we promise, and how the store and catalog must behave. Agents, the designer and the founder all read this first.

- **Owners:** founder (decisions), Claude (keeps it in sync).
- **Detail lives in:** `docs/DESIGN.md` (design tokens), `.claude/skills/luxury-voice` (writing rules) and
  `docs/PRD.md` (business goals).
- **⚠️ = needs a founder decision** before it is shown to customers. Never publish a ⚠️ item as a promise.

---

## 1. Essence
- **One line:** curated international luxury, sourced from the brands' own stores and delivered to India, calmly
  and correctly.
- **Ethos:** quiet provenance. The product and its story do the talking. Nothing shouts.
- **Tagline (from DESIGN.md):** *Sourced. Authenticated. Delivered.*
- **We are:** a premium resale and concierge store for discerning Indian buyers.
- **We are not:** a hype sneaker drop shop, a discount outlet, or a marketplace of unknown sellers.
- **Long-term:** an AI-led Luxella. Agents do the repetitive work (sourcing, catalog, reports, drafts), and the
  founder approves anything that touches money or customers.

## 2. Who we serve
- **Primary:** HNI and aspirational luxury buyers in India who want international brands at their real current
  price, without guesswork about authenticity, duties or delivery.
- **They value:** trust, speed, a quiet premium experience, and correct sizes and stock.
- **They fear:** fakes, hidden duties, long or unknown delivery, sold-out-after-payment, no returns, no human to
  talk to.

## 3. Brand positioning vs the market
**Benchmarks (teardown in progress, 2026-10-10):**
- **Look and feel:** Gucci and Balenciaga set the bar for luxury presentation.
- **Information:** Indian resellers (Culture Circle, HustleClub, Kicksmachine, Hypefly, Creepdog Crew) set the
  bar for the trust details Indian buyers expect.

Luxella's target is **luxury-house presentation with reseller-grade transparency**:

| | Luxury houses (Gucci, Balenciaga) | Indian resellers | **Luxella** |
|---|---|---|---|
| Look | editorial, huge imagery, whitespace | busy, banners, urgency | **editorial and calm** |
| Tone | understated | hype ("SALE", "HURRY") | **understated** |
| Trust info | implicit (it's the brand) | explicit (authentic, COD, delivery days) | **explicit, but calm** |
| Data accuracy | perfect (own stock) | varies (scraped) | **scraped, verified daily** (see §8) |

### Competitor data accuracy: Coach + Michael Kors (test 2026-10-10)
Raw data: `/root/backups/2026-10-10/reseller_compare.jsonl`. This is a small sample of 6–22 matched products per
site.

| | Kicksmachine | Hustle Club | Hypefly | Crepdog Crew |
|---|---|---|---|---|
| Availability correct | **86%** | 71% | 67% | 67% |
| Main error | never shows sold out (oversell risk) | copies Kicksmachine with lag | placeholder stock (qty 50) | tiny range |
| ₹ per US$ (median) | ~163–171 | ~148–166 | ~154–164 | ~143 |
| Coach / MK listed | 1,483 / 2,372 | 2,274 / 1,140 | 2,309 / 2,370 | 126 / 0 |

**What this means for Luxella:**
- Nobody follows the brand's own sale price. Michael Kors is 70–80% off on its US site and the resellers don't
  pass that on.
- **Luxella's edge** is per-size stock from the source, verified daily, and prices recomputed from the current
  source price (Kiri Bag: $195 → ₹28,099, about 144× including shipping and margin).
- **Never copy** Kicksmachine's "always in stock" listings: they mean selling items that are gone.

### UX benchmark (teardown 2026-10-10)
Screenshots and page text: `/root/backups/2026-10-10/benchmark/`. Gucci blocked every fetch (no data). Balenciaga is
desktop only.

| | Indian resellers do | Balenciaga does | **Luxella adopts** |
|---|---|---|---|
| Authenticity | certificate / "100% authentic or money back" on PDP | implicit | **calm line on every PDP + "How we authenticate" page** |
| Delivery | pincode check, "ships tomorrow", 18–28 days | estimated date range | **one honest date range, everywhere** |
| Price | strike price, % OFF, "SALE" | one price | **one price, landed (duties incl.)** |
| Payments | EMI, UPI, COD loud | cards, Klarna | **one muted line** |
| PDP | sticky add-to-bag, size chart, "we'll source it" | stacked images, details accordion, "Style it with" | **all of these, quietly** |
| Contact | green WhatsApp bubble | book appointment | **WhatsApp concierge, ink icon** |
| Collection | filter + sort | chips + "available online" toggle | **filters + "available now" default** |

**Never adopt:** "x sold", "Only 1 left", % OFF, ticker bars, app pop-ups, celebrity walls.
Build spec: `docs/specs/2026-10-10-storefront-uplift.md`.

## 4. Voice and tone
Full rules: `.claude/skills/luxury-voice/SKILL.md`. In short:
- **Short, calm, precise.** One idea per sentence. 1–3 sentences in DMs.
- **Never use** "SALE", "HURRY", "LAST CHANCE", "50% OFF", "DM now!!", exclamation marks, or ALL CAPS. No emoji
  in formal messages.
- **Exact numbers only:** ₹ with Indian commas (₹1,19,999), sizes and colours exactly as listed.
- **Promise only what is verified:** authenticity, delivery dates, duties and discounts only when the data or the
  founder confirms them.
- **Language:** English by default. Reply in Hinglish if the customer writes in Hinglish.
- **Product copy:** *"The Polène Numéro Un in smooth calfskin. Structured, quietly recognisable, made in Ubrique,
  Spain."*
- **Every outbound customer message** is a draft in the approval queue until the founder approves it.

## 5. Visual identity
Full tokens: `docs/DESIGN.md`. Key rules:

| Element | Rule |
|---|---|
| Colours | **gold never as text on paper (2.45:1, fails AA)**. `--bg #0B0B0B`, `--surface #141414`, `--ink #F5F1EA`, `--muted #A59F94`, `--line #262626`, **`--gold #B8975A`** (the ONE accent, at most 2 per screen), `--paper #F5F1EA` (light sections) |
| Type | Headings in a light serif (Cormorant Garamond; the live theme uses Cormorant + Jost). Body in a clean sans. Max 2 typefaces. Scale 12/14/16/20/28/40/64, body line-height 1.6 |
| Layout | 8 px grid, whitespace instead of dividers, max content width 1200 px, imagery edge to edge, mobile first (390 → 768 → 1280) |
| Motion | 300–600 ms ease-out, fades and gentle translate only, no bounce, respect reduced-motion. **Speed beats motion** (§7) |
| Imagery | 4:5 crop, clean background (rembg / product-photos skill), consistent framing, alt text on every image, no placeholder images live |
| States | every screen has loading (skeleton), empty, error (with a next step), success, offline/slow |
| Accessibility | contrast AA, keyboard navigable, visible focus, 44 px touch targets |

## 6. Storefront standards (what every page must have)
*Refined by the 2026-10-10 audit and benchmark. Live gaps: Sale badges everywhere, dead nav to `/`, `/pages/authenticity` 404, delivery 3–4 weeks vs 10–18 days conflict, Handbags holds boots, one-image PDPs.*
- **Header:** logo, 5–7 clear categories (Bags, Shoes, Clothing, Accessories, Brands, New In), visible search, bag
  icon. No promo marquee.
- **Home:** an editorial hero (one strong image or short video, poster as LCP), curated edits ("New this week",
  "Under ₹25,000", brand edits), a calm trust band, brand logos.
- **Collection:**
  - product cards show brand, name and price in ₹, nothing else loud;
  - filters for brand, category, size, price and in stock;
  - sort by newest and by price.
- **Product page:**
  - gallery with zoom, 4:5;
  - clear size selector: sold-out sizes visibly disabled, plus a size guide;
  - price with a duties/shipping line (⚠️ §9);
  - delivery estimate (⚠️), authenticity line (⚠️), returns line (⚠️), payment options (⚠️);
  - details in this order: style code, material, colour, origin, care;
  - "You may also like" from the same brand or category;
  - sticky add-to-bag on mobile.
- **Info pages:**
  - How we source and authenticate;
  - Shipping and duties;
  - Returns;
  - FAQ;
  - About;
  - Contact (WhatsApp concierge).
- **Never live:** price-0 products, "Untitled" or lookbook pages, placeholder images, wrong currency, broken links.

## 7. Performance standards
- **Target:** Lighthouse mobile performance ≥ 80, LCP ≤ 2.5 s, CLS ≤ 0.1. The 2026-10-05 baseline was 41–54 and
  LCP 6.4 s.
- An unpublished speed-fix draft theme exists (font preload, one CSS bundle, no blur delay on the hero, particles
  pause off-screen). See memory `theme-speed-draft`.
- **Rule:** no new animation or library unless it keeps the targets.

## 8. Catalog and data standards (how the store stays honest)
- **Sources:** about 40 brand sites, scraped into Supabase, pushed to Shopify. Products are matched by
  **(site, product_url)**, never by SKU alone.
- **Stock:** per size. A size is in stock at 10 if it is available at the source and priced; otherwise 0. The
  per-size sync keeps it right (repair done for 55 and the rest in progress; relist added sizes to about 3,340
  size-less listings, 2026-10-07/08).
- **Freshness:** data older than 3 days is treated as stale. Stale products are never newly published, repaired or
  shown as deals.
- **Price guards:**
  - price 0 or unknown never goes live (PR #15/#16);
  - the 187 leftovers were drafted on 2026-10-07;
  - the daily report alarms if any price-0 product becomes buyable.
- **Hidden products:** products that are active but unpublished are checked; 185 were published on 2026-10-07.
- **Daily truth:**
  - a 08:00 IST report covers live products, sync, failures, price-0 buyable and public ports;
  - the 07:45 IST Deal Finder covers real price drops and restocks.

### Pricing formula (current code, `pricing.py`)
1. Landed cost = source price × FX + US sales tax where it applies + shipping (₹1,250 per kg by category weight).
2. Selling price = landed cost × (1 + **25% margin**), rounded to …99.
3. Compare-at (MRP) = selling price ÷ (1 − 0.35), so every product shows a **35% "discount"**.

**Decision (founder, 2026-10-10): option (b).** Show a crossed-out price **only when the brand itself has
discounted the item**, using the brand's real original price converted with the same formula. Otherwise show one
price, with no fake "35% off".

**Not built yet.** The scrapers don't capture the brand's original price (`pricing.py` still forces 35% on every
product). It needs its own spec: capture the source compare-at, then change push and sync, then a dry-run on the
live prices.

## 9. Customer promises (⚠️ every line needs the founder's confirmation before it appears on the site)
| Promise | Current state | Needs |
|---|---|---|
| Authenticity | Bought only from the brand's official store | Wording + proof (invoice on request?) ⚠️ |
| Delivery time | Unknown publicly (US/UK → reshipper → India) | Honest range, e.g. "10–18 business days" ⚠️ |
| Duties and taxes | Built into the landed cost? | State it clearly: "prices include duties" or not ⚠️ |
| Returns | Not defined | Policy (e.g. no returns on resale vs exchange) ⚠️ |
| Payments | Shopify checkout | UPI / cards / EMI / COD? ⚠️ |
| Contact | WhatsApp concierge planned (Chatwoot) | Number + hours ⚠️ |
| Sourcing / pre-order | Items are ordered after the customer pays | Say so honestly ("sourced to order") ⚠️ |

## 10. Channels
- **Store:** luxella-9299.myshopify.com (Shopify Dawn-based theme). A custom domain is ⚠️.
- **Instagram:** content drafts only (ig-* skills); the founder posts.
- **WhatsApp concierge:** Chatwoot, self-hosted. Not live yet (needs a domain + Meta app).
- **Founder alerts:** ntfy now. Telegram approval bot built (PR #41), waiting for the token setup.

## 11. How the business runs (AI-led)
- **Workflow:** spec → plan → build → test → review → founder merge.
- **Production writes:** dry-run first, then backup, then small batch, then verify.
- **Agents** run on the Agent Standard harness (`packages/core/agent.py`): shadow, then approve, then narrow
  auto, with a kill switch and a write budget. **Live:** daily-report (read-only) and deal-finder (shadow). The
  bid-pricing agent stays a separate project.
- **Server:** SSH key-only, firewall 22-only, fail2ban.

## 12. Open decisions (founder)
1. ~~Compare-at framing~~ decided (b), real brand discounts only; build pending (§8).
2. Every customer promise in §9.
3. Custom domain + WhatsApp number.
4. Logo / wordmark usage rules (not documented yet).
5. Delivery range, authenticity promise, returns, payments, duties wording (storefront-uplift spec).

## Change log
- **2026-10-10:** first version, compiled from DESIGN.md, PRD.md, the luxury-voice skill, `pricing.py` and the
  2026-10-04..10 operations work. Benchmark and audit sections added the same day.
