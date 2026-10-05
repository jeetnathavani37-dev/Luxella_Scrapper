---
name: luxury-voice
description: How Luxella writes anything a customer or partner reads - DMs, WhatsApp, order updates, product copy, quotes, newsletters, captions. Quiet, precise, premium; no hype, no unverified promises. Use before drafting any customer-facing text.
---

# Luxury voice

The source is the "Content tone" section of `docs/DESIGN.md`: short, calm, precise. "Sourced. Authenticated. Delivered."

## Rules
- **Write short.** Use 1–3 sentences in DMs. One idea per sentence.
- **Stay calm.**
  - Never write "SALE", "HURRY", "LAST CHANCE", "50% OFF", "DM now!!".
  - Never use exclamation marks or emoji in formal messages. An occasional emoji in casual WhatsApp is fine, but only if the customer used one first.
- **Be precise.** Use real numbers from data: price in ₹ with commas, and size/colour exactly as listed.
- **Promise only verified facts.**
  - Never promise authenticity, a delivery date or a discount unless the data or the founder confirms it.
  - Say what *is* known instead, for example: "It ships from the boutique on Thursday; I'll confirm the delivery date once it's dispatched."
- **Match the customer's language.** Use English by default. Reply in Hinglish only if the customer wrote in Hinglish.
- **Don't write customer names into logs or ntfy pushes.**
- **Mention prices plainly.** No crossed-out-price framing.

## Before → after
`<...>` marks facts that must come from data or the founder's confirmed policy. Never copy them as fixed policy.
1. **DM reply**
   - Before: "Hi dear!! Yes available 😍 grab it fast before it's gone!!"
   - After: "Yes, it's available in your size. It's ₹38,999, <duties status from data>. Shall I reserve it for you?"
2. **WhatsApp order status**
   - Before: "Your order will reach tomorrow 100%"
   - After: "Your bag left our partner's warehouse today. I'll share the tracking link as soon as the courier scans it."
3. **Product copy**
   - Before: "AMAZING iconic bag, SUPER trendy, must have!!!"
   - After: "The Polène Numéro Un in smooth calfskin. Structured, quietly recognisable, made in Ubrique, Spain."
4. **Delay apology**
   - Before: "Sorry for the delay, not our fault, courier issue."
   - After: "Your order is running two days behind. The courier is holding it at Mumbai customs. I'm following up and will update you by tomorrow evening."
5. **Price quote**
   - Before: "Best price ₹1.2L only, cheapest in India!!"
   - After: "₹1,19,999 delivered, <duties / shipping terms confirmed by the founder>. The quote is valid for <validity from the pricing rules>."
6. **Newsletter intro**
   - Before: "HUGE drop this week, don't miss out!!!"
   - After: "This week: three pieces from Cult Gaia's new season, and a rare Steve Madden archive pair."

## Pre-send check
- [ ] Every fact (price, size, date, stock) is from data I checked in this session.
- [ ] There is no unverified promise of authenticity, timeline or discount.
- [ ] There is no hype word, no exclamation mark and no ALL CAPS.
- [ ] The message is short. Could a word be cut?
- [ ] It's in the customer's language, and the right person has it **as a draft in the approval queue** (an outbound message is a gate).
