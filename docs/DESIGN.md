# Design system: Luxella / Trove

Ethos: quiet provenance. The product and its story do the talking. Nothing shouts.

## Color tokens
| Token | Value | Use |
|---|---|---|
| --bg | #0B0B0B | Page background (dark mode default) |
| --surface | #141414 | Cards, panels |
| --ink | #F5F1EA | Primary text on dark (off-white) |
| --muted | #A59F94 | Secondary text |
| --line | #262626 | Borders, dividers |
| --gold | #B8975A | The ONE accent: key actions, small highlights |
| --paper | #F5F1EA | Light sections / light mode background |

Rule: gold is used sparingly. If a screen has more than 2 gold elements, remove some.

## Typography
- Headings: elegant serif (Cormorant Garamond or Playfair Display), light to regular weight.
- Body/UI: clean sans (Inter or Geist).
- Scale: 12 / 14 / 16 / 20 / 28 / 40 / 64. Generous line height (1.6 body).
- Never more than 2 typefaces.

## Space and layout
- 8px grid. Prefer large whitespace over dividers.
- Max content width 1200px; product imagery edge to edge where possible.
- Mobile first. Design at 390px, then 768px, then 1280px.

## Motion
- Slow and subtle: 300-600ms, ease-out. Fades and gentle translate only.
- No bounce, no flashy transitions. Respect prefers-reduced-motion.

## Components (shadcn/ui as the base)
Button (primary = gold outline or solid ink, secondary = ghost), Card, Dialog, Sheet (mobile drawers), Toast (Sonner), Command palette (cmdk), Input/Select with visible focus rings.

## Imagery
- High-quality product photos, clean backgrounds, consistent crop ratio (4:5).
- Watermark where needed. Alt text on every image.

## Content tone
Short, calm, precise. "Sourced. Authenticated. Delivered." Never "SALE", "HURRY", "50% OFF".

## Required states for every screen
loading (skeleton, not spinner), empty, error (with a next step), success, and offline/slow.

## Accessibility
Contrast AA minimum, keyboard navigable, visible focus, 44px minimum touch targets.
