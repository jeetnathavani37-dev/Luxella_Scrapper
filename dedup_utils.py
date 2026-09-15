"""
dedup_utils.py

Duplicate-detection ke liye shared logic. Alag-alag sites products ka
naam thoda alag likhte hain (jaise "Coach Tabby Shoulder Bag" vs
"Tabby 20 Shoulder Bag Coach") - isliye exact-string-match kaam nahi
karega. Fingerprint approach: brand + naam ke saare significant words
ko nikaal ke, sort karke ek consistent "key" banate hain - taaki alag
order/wording mein likhe naam bhi same fingerprint pe match ho jaayein.

NOTE: Ye conservative hai (galti se alag products merge na ho jaayein
isliye) - sirf common filler words (the, a, in, with, etc.) hi hataye
jaate hain, product-type words (bag, shoulder, tote) NAHI hataye
jaate - taaki genuinely alag product-types accidentally match na ho
jaayein.
"""
import re

FILLER_WORDS = {
    "the", "a", "an", "in", "with", "and", "of", "for", "by", "is",
    "new", "to", "on", "at", "from",
}


def compute_fingerprint(brand, name):
    """Brand + product-name se ek normalized, order-independent
    fingerprint string banata hai. Same product (chahe alag site pe
    thoda alag likha ho) usually same fingerprint dega."""
    text = f"{brand or ''} {name or ''}".lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = text.split()
    significant = sorted(set(w for w in words if w not in FILLER_WORDS and len(w) > 1))
    return "-".join(significant)
