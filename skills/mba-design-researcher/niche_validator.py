"""
niche_validator.py — Phase 4: IP & Compliance Pre-Check
Validates candidate niches against USPTO TESS trademark database,
restricted words list, and red flag detection.
"""

import asyncio
import re
from datetime import datetime

from compliance import scan_text, is_compliant


# ── USPTO TESS Trademark Search ───────────────────────────────────────────────

async def check_trademark_tess(browser, phrase: str) -> dict:
    """
    Search USPTO TESS database for trademark conflicts.
    Focuses on Class 025 (Clothing/Apparel).
    Returns dict with conflict status and details.
    """
    result = {
        "phrase": phrase,
        "trademark_status": "UNKNOWN",
        "conflicts": [],
        "class_025_hit": False,
    }

    try:
        # Navigate to TESS search
        url = "https://tmsearch.uspto.gov/bin/gate.exe?f=searchss&state=4801:1.1.1"
        page = await browser.get(url)
        await asyncio.sleep(3)

        # Try to use the free-form search
        search_input = await page.query_selector("input[name='p_s_PARA1']")
        if search_input:
            await search_input.clear_input()
            await search_input.send_keys(phrase)

            submit_btn = await page.query_selector("input[type='submit']")
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(4)

                # Check results
                body_text = await page.get_content()

                if "No TESS records" in body_text or "did not match" in body_text:
                    result["trademark_status"] = "CLEAR"
                elif "records" in body_text.lower():
                    # Check for Class 025 specifically
                    if "025" in body_text or "clothing" in body_text.lower():
                        result["trademark_status"] = "POTENTIAL_CONFLICT"
                        result["class_025_hit"] = True
                    else:
                        result["trademark_status"] = "FOUND_OTHER_CLASS"

                    # Try to extract match count
                    match = re.search(r'(\d+)\s+record', body_text)
                    if match:
                        result["conflicts"].append(f"{match.group(1)} records found")
    except Exception as e:
        result["trademark_status"] = "CHECK_FAILED"
        result["error"] = str(e)

    return result


# ── Restricted Words Check ────────────────────────────────────────────────────

def check_restricted_words(keywords: list[str]) -> dict:
    """
    Check a list of keywords against the restricted words database.
    Returns dict with clean keywords and flagged keywords.
    """
    clean = []
    flagged = []

    for kw in keywords:
        issues = scan_text(kw)
        if issues:
            flagged.append({"keyword": kw, "issues": issues})
        else:
            clean.append(kw)

    return {
        "clean_keywords": clean,
        "flagged_keywords": flagged,
        "total_checked": len(keywords),
        "total_clean": len(clean),
        "total_flagged": len(flagged),
    }


# ── Red Flag Detection ────────────────────────────────────────────────────────

RED_FLAG_PATTERNS = [
    # Pesticide triggers
    r"\b(anti.?microbial|anti.?bacterial|anti.?fungal|repell|insecticid|germ.?free)\b",
    # Celebrity / IP
    r"\b(disney|marvel|star\s*wars|harry\s*potter|dc\s*comics|nintendo|hello\s*kitty)\b",
    # Misleading effects
    r"\b(neon|glitter|metallic|holographic|glow|embroidered|sequin)\b",
    # Political / Sensitive
    r"\b(trump|biden|maga|political|election)\b",
]


def detect_red_flags(text: str) -> list[str]:
    """
    Detect red flags in niche text that should trigger immediate abort.
    Returns list of red flag descriptions.
    """
    flags = []
    text_lower = text.lower()

    for pattern in RED_FLAG_PATTERNS:
        matches = re.findall(pattern, text_lower)
        if matches:
            flags.extend(matches)

    return list(set(flags))


# ── Niche Classification ─────────────────────────────────────────────────────

def classify_niche_sustainability(niche: str) -> str:
    """
    Classify niche as Seasonal, Evergreen, or Fad.
    Based on knowledge base Phase 5 rules.
    """
    seasonal_patterns = [
        r"class of \d{4}", r"christmas", r"halloween", r"valentine",
        r"father'?s?\s*day", r"mother'?s?\s*day", r"easter", r"4th of july",
        r"independence day", r"thanksgiving", r"new year", r"back to school",
        r"graduation", r"st\.?\s*patrick", r"memorial day", r"labor day",
    ]

    evergreen_patterns = [
        r"nurse", r"teacher", r"gamer", r"programmer", r"engineer",
        r"fishing", r"hunting", r"camping", r"hiking", r"cooking",
        r"gardening", r"yoga", r"gym", r"fitness", r"dog\s*(mom|dad)",
        r"cat\s*(mom|dad)", r"coffee", r"wine\s*lover", r"book\s*lover",
        r"music", r"guitar", r"photography", r"travel",
    ]

    niche_lower = niche.lower()

    for pattern in seasonal_patterns:
        if re.search(pattern, niche_lower):
            return "SEASONAL"

    for pattern in evergreen_patterns:
        if re.search(pattern, niche_lower):
            return "EVERGREEN"

    return "POTENTIAL_FAD"


# ── Full Validation Pipeline ──────────────────────────────────────────────────

async def validate_niche(browser, keyword: str, check_tess: bool = True) -> dict:
    """
    Run full validation on a niche keyword.
    Returns comprehensive validation result.
    """
    print(f"    Validating niche: '{keyword}'...")

    # Compliance check
    compliance = check_restricted_words([keyword])

    # Red flag detection
    red_flags = detect_red_flags(keyword)

    # Sustainability classification
    sustainability = classify_niche_sustainability(keyword)

    # Trademark check (optional — slow)
    trademark = {"trademark_status": "SKIPPED"}
    if check_tess and not red_flags:
        trademark = await check_trademark_tess(browser, keyword)

    # Overall verdict
    is_safe = (
        compliance["total_flagged"] == 0
        and len(red_flags) == 0
        and trademark.get("trademark_status") not in ["POTENTIAL_CONFLICT"]
    )

    verdict = "APPROVED" if is_safe else "REJECTED"
    rejection_reasons = []
    if compliance["total_flagged"] > 0:
        rejection_reasons.append(f"Restricted words: {compliance['flagged_keywords']}")
    if red_flags:
        rejection_reasons.append(f"Red flags: {red_flags}")
    if trademark.get("class_025_hit"):
        rejection_reasons.append("Trademark conflict in Class 025 (Apparel)")

    return {
        "keyword": keyword,
        "verdict": verdict,
        "rejection_reasons": rejection_reasons,
        "compliance": compliance,
        "red_flags": red_flags,
        "trademark": trademark,
        "sustainability": sustainability,
        "timestamp": datetime.now().isoformat(),
    }
