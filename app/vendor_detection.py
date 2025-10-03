from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple, Optional

# --- Patterns ---
GSTIN_LOOSE = re.compile(
    r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9][A-Z0-9][A-Z0-9]\b",
    re.I,
)
GSTIN_STRICT = re.compile(
    r"\b(?P<state>[0-9]{2})(?P<pan>[A-Z]{5}[0-9]{4}[A-Z])(?P<entity>[A-Z0-9])(?P<z>[A-Z0-9])(?P<check>[A-Z0-9])\b",
    re.I,
)
POS_TOKEN = re.compile(
    r"\b(?:Place\s*of\s*Supply|POS|State\s*Code|State)\b[:\s]*([A-Z][A-Za-z.\-\s]+)?\b(\d{2})?\b",
    re.I,
)

VENDOR_CUES = [
    "seller", "supplier", "from", "invoice from", "sold by", "billed by",
    "issuer", "merchant", "registered office", "tax invoice from"
]
CUSTOMER_CUES = [
    "buyer", "bill to", "billed to", "ship to", "deliver to", "consignee",
    "customer", "receiver", "recipient"
]
ADDRESS_TOKENS = [
    "road", "rd", "street", "st", "lane", "ln", "near", "po", "post",
    "taluk", "district", "dist", "pin", "zip", "phone", "ph", "mob",
    "mobile", "email", "gst", "gstin", "fax", "landmark", "india", "kerala",
    "thrissur", "kochi", "ernakulam", "koratty", "building", "bldg", "bldgs", "floor"
]
NOISE_LINES = {"tax invoice", "invoice", "bill", "quotation", "estimate"}

def _is_addressy(s: str) -> bool:
    s_clean = re.sub(r"[\s,.;:/\-|]+", " ", s.lower()).strip()
    if not s_clean:
        return False
    hits = sum(tok in s_clean for tok in ADDRESS_TOKENS)
    comma_penalty = s.count(",") >= 2
    digit_penalty = sum(ch.isdigit() for ch in s) >= 6
    long_penalty = len(s) > 70
    return (hits >= 2) or comma_penalty or digit_penalty or long_penalty

def _has_any(text: str, words: List[str]) -> bool:
    t = text.lower()
    return any(w in t for w in words)

def _collect_gstin_hits(lines: List[str]) -> List[Tuple[int, re.Match]]:
    hits = []
    for i, ln in enumerate(lines):
        m = GSTIN_STRICT.search(ln) or GSTIN_LOOSE.search(ln)
        if m:
            hits.append((i, m))
    return hits

def _best_name_in_block(block: List[str]) -> Optional[str]:
    # Prefer an uppercase-like or title-ish business name that is not addressy/noise.
    scored: List[Tuple[float, str]] = []
    for s in block:
        s_strip = s.strip()
        s_low = s_strip.lower()
        if not s_strip or s_low in NOISE_LINES:
            continue
        if "gstin" in s_low:      # don't use the gstin line as the name
            continue
        if _is_addressy(s_strip):
            continue

        # Heuristics for "name-ness"
        has_letters = any(c.isalpha() for c in s_strip)
        word_count = len(s_strip.split())
        cap_ratio = sum(c.isupper() for c in s_strip if c.isalpha()) / max(1, sum(c.isalpha() for c in s_strip))
        score = 0.0
        if has_letters:
            score += 10
        # Prefer reasonable length
        if 2 <= word_count <= 7:
            score += 6
        # Prefer somewhat capitalized lines (but allow mixed case)
        score += 5 * cap_ratio
        # Penalize trailing punctuation junk
        if s_strip.endswith((".", ",", ":", ";", "|", "-")):
            score -= 2

        scored.append((score, s_strip))

    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[0][1] if scored else None

def _score_line(i: int, line: str, lines: List[str], gstin_idxs: List[int]) -> float:
    score = 0.0
    L = line.lower()

    if i in gstin_idxs:
        score += 50

    # Proximity to GSTIN within +/- 3 lines
    near = any(abs(i - g) <= 3 for g in gstin_idxs)
    if near:
        score += 20

    if _has_any(L, VENDOR_CUES):
        score += 15
    if _has_any(L, CUSTOMER_CUES):
        score -= 25
    if _is_addressy(line):
        score -= 10

    # Prefer not too short, not too long
    n = len(line.strip())
    if 10 <= n <= 60:
        score += 5

    return score

def detect_vendor_from_lines(lines: List[str]) -> Dict[str, Any]:
    """
    Input: OCR'd document as a list of text lines (top-to-bottom).
    Output: {
        "name": str|None,
        "gstin": str|None,
        "pos_state_name": str|None,
        "pos_state_code": str|None,
        "score": float,
        "needs_review": bool,
        "source": "gstin+heuristics"|"cues-only"|"fallback"
    }
    """
    # Normalize lines (keep original alongside)
    raw_lines = lines[:]
    norm_lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw_lines]

    # 1) Find POS (Place of Supply / State Code)
    pos_state_name = None
    pos_state_code = None
    for ln in norm_lines:
        m = POS_TOKEN.search(ln)
        if m:
            # group(1) may be a state name, group(2) may be the 2-digit code
            if m.group(1):
                pos_state_name = (m.group(1) or "").strip(" :.-|")
            if m.group(2):
                pos_state_code = m.group(2)

    # 2) Find GSTIN hits
    hits = _collect_gstin_hits(norm_lines)
    gstin_idxs = [i for i, _ in hits]

    # 3) Score lines
    scored = [( _score_line(i, ln, norm_lines, gstin_idxs), i, ln) for i, ln in enumerate(norm_lines)]
    scored.sort(reverse=True, key=lambda t: t[0])

    # 4) Candidate name resolution around best GSTIN
    best_gstin = None
    best_gstin_idx = None
    if hits:
        # Prefer the top-scoring line that contains/near gstin
        top = next(((s, i, ln) for (s, i, ln) in scored if i in gstin_idxs or any(abs(i - g) <= 1 for g in gstin_idxs)), None)
        if top:
            # Choose the nearest GSTIN index
            i_top = top[1]
            nearest = min(gstin_idxs, key=lambda g: abs(g - i_top))
            best_gstin_idx = nearest
            m = GSTIN_STRICT.search(norm_lines[nearest]) or GSTIN_LOOSE.search(norm_lines[nearest])
            if m:
                best_gstin = m.group(0)

            # Build a local block around GSTIN to pick name
            lo = max(0, nearest - 3)
            hi = min(len(norm_lines), nearest + 4)
            block = norm_lines[lo:hi]
            name = _best_name_in_block(block)
            src = "gstin+heuristics"
            total_score = top[0] + 5  # nudge up gstin-based detection

            return {
                "name": name,
                "gstin": best_gstin,
                "pos_state_name": pos_state_name,
                "pos_state_code": pos_state_code or (best_gstin[:2] if best_gstin else None),
                "score": float(total_score),
                "needs_review": (name is None) or (total_score < 60),
                "source": src,
                "index_hint": best_gstin_idx,
            }

    # 5) No GSTIN: fall back to vendor cues (but avoid customer cues)
    for s, i, ln in scored:
        if _has_any(ln, VENDOR_CUES) and not _has_any(ln, CUSTOMER_CUES):
            # Try to take the next non-addressy line as name
            block = norm_lines[i:i+3]
            name = _best_name_in_block(block) or ln
            return {
                "name": name,
                "gstin": None,
                "pos_state_name": pos_state_name,
                "pos_state_code": pos_state_code,
                "score": float(s),
                "needs_review": True,   # No GSTIN — flag for review
                "source": "cues-only",
                "index_hint": i,
            }

    # 6) Absolute fallback — take top non-addressy line
    for s, i, ln in scored:
        if not _is_addressy(ln) and not _has_any(ln, CUSTOMER_CUES) and ln.lower() not in NOISE_LINES:
            return {
                "name": ln,
                "gstin": None,
                "pos_state_name": pos_state_name,
                "pos_state_code": pos_state_code,
                "score": float(s) - 10,
                "needs_review": True,
                "source": "fallback",
                "index_hint": i,
            }

    # Nothing reliable
    return {
        "name": None,
        "gstin": None,
        "pos_state_name": pos_state_name,
        "pos_state_code": pos_state_code,
        "score": 0.0,
        "needs_review": True,
        "source": "fallback",
        "index_hint": None,
    }
