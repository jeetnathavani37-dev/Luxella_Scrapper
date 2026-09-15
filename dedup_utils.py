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
jaate hain, product-type/color/style words (bag, shoulder, tote,
black) NAHI hataye jaate - taaki genuinely alag product-variants
(jaise same naam ke alag color/type) accidentally match na ho jaayein
(fingerprint EXACT word-set match maangta hai, sirf overlap nahi -
"Coach Bag Black" aur "Coach Bag Brown" alag fingerprints denge).

NOTE (2026-09-15): TIGHTEN kiya - MIN_SIGNIFICANT_WORDS threshold add
kiya. Bohot chhote/generic naam (jaise sirf "Coach Wallet" - 2 words)
dedup ke liye SKIP kar dete hain (fingerprint None return karta hai) -
kyunki itne kam words mein do GENUINELY alag products (alag wallet
models) accidentally same fingerprint pa sakte hain. Safer trade-off:
kabhi-kabhi genuine duplicate miss ho jaayega (chhota naam wala), but
kabhi bhi GALTI se 2 alag products merge nahi honge.
"""
import re

FILLER_WORDS = {
    "the", "a", "an", "in", "with", "and", "of", "for", "by", "is",
    "new", "to", "on", "at", "from",
}

MIN_SIGNIFICANT_WORDS = 4  # isse kam words wale naam dedup se skip ho jaate hain


def compute_fingerprint(brand, name):
    """Brand + product-name se ek normalized, order-independent
    fingerprint string banata hai. Same product (chahe alag site pe
    thoda alag likha ho) usually same fingerprint dega. Agar naam bohot
    chhota/generic hai (MIN_SIGNIFICANT_WORDS se kam), None return
    karta hai - matlab is product ko dedup-check se SKIP karo (galti se
    alag products merge hone se bachane ke liye)."""
    text = f"{brand or ''} {name or ''}".lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = text.split()
    significant = sorted(set(w for w in words if w not in FILLER_WORDS and len(w) > 1))

    if len(significant) < MIN_SIGNIFICANT_WORDS:
        return None

    return "-".join(significant)
