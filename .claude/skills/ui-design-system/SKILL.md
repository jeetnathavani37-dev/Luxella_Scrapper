---
name: ui-design-system
description: Apply the Luxella/Trove design system (docs/DESIGN.md) in code - tokens as CSS variables, Tailwind/shadcn setup, type scale, motion, required states, and the design checks to run. Use for any Luxella UI - storefront, admin dashboard, landing page, Trove, or Shopify theme edits.
---

# Luxella design system in code

`docs/DESIGN.md` is the source of truth. This skill covers how to apply it.

## Tokens (CSS variables, dark default)
```css
:root {
  --bg: #0B0B0B; --surface: #141414; --ink: #F5F1EA; --muted: #A59F94;
  --line: #262626; --gold: #B8975A; --paper: #F5F1EA;
  --font-serif: "Cormorant Garamond", "Playfair Display", serif;
  --font-sans: "Geist", "Inter", system-ui, sans-serif;
  --ease: cubic-bezier(0.16, 1, 0.3, 1); --dur: 400ms;
}
@media (prefers-reduced-motion: reduce) { :root { --dur: 0ms; } }
body { background: var(--bg); color: var(--ink); font-family: var(--font-sans); line-height: 1.6; }
h1, h2, h3 { font-family: var(--font-serif); font-weight: 400; }
```
- **Tailwind v4:** map these in `@theme` (`--color-bg: var(--bg)` and so on) and use `bg-bg text-ink border-line`.
- **shadcn:** set `--background`, `--foreground`, `--primary` (ink) and `--ring` (gold) from these tokens.
- **Type scale (px):** 12 / 14 / 16 / 20 / 28 / 40 / 64. Spacing follows an 8px grid.
- **Buttons:** primary is a gold outline or solid ink; secondary is ghost.
- **Gold budget:** at most 2 gold elements on a screen. Count them.

## Building blocks
- **React/Next:** shadcn/ui with Sonner (toasts), Vaul/Sheet (mobile drawers), cmdk (search) and Motion (300–600ms ease-out fades). Install versions and gotchas are in the global `ui-kit` skill; prototype in `/root/ui-playground`.
- **Shopify Liquid theme:** CSS variables plus vanilla GSAP and Lenis only. The staged files are in `/root/luxella-theme-gsap`. Work only on an **unpublished duplicate** theme and never publish.
- **Images:** 4:5 crop, `alt` on every image, lazy-load below the fold.

## Every screen ships with
loading (skeleton) · empty · error with a next step · success · offline/slow. Test at 390, 768 and 1280px.

## Checks (run them and paste the output)
```bash
I=~/.claude/skills/impeccable/scripts/impeccable
$I detect <src-dir>                                                         # anti-patterns in code
IMPECCABLE_BROWSER=/root/agent-tools/impeccable/chrome-nosandbox $I detect <url> --viewport 390x844
```
- Fix contrast below AA, text overflow, layout-animating transitions (width/height), bounce easing and gradient text.
- Known issues on the live store from the 2026-10-04 scan:
  - empty category tiles (Footwear and Accessories)
  - faint category descriptions (0.38 opacity)
  - a Times fallback font on the trust row
  - a 10px link on the product page

Copy tone: short, calm, precise ("Sourced. Authenticated. Delivered."). Never "SALE", "HURRY" or "50% OFF".
