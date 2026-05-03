"""
compliance.py — MBA Compliance Checker
Scans text against RestrictedWords.txt and hardcoded banned terms.
Used for pre-checking niche keywords and design briefs before investment.
"""

import os
import re

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_RESTRICTED_WORDS_FILE = os.path.join(_SKILL_DIR, "RestrictedWords.txt")


def _load_restricted_words() -> list[str]:
    words = []
    with open(_RESTRICTED_WORDS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if w:
                words.append(w.lower())
    return words


RESTRICTED_WORDS: list[str] = _load_restricted_words()

ADDITIONAL_BANNED = [
    "free shipping", "prime shipping", "satisfaction guaranteed", "money back",
    "refund", "returns", "risk free", "easy returns", "limited quantities",
    "ships in", "ready to ship", "arrive faster", "best seller", "closeout",
    "special offer", "on sale", "discount", "cheap", "bargain", "free gift",
    "bonus", "buy now", "high quality", "premium", "top rated", "best quality",
    "durable", "soft", "thick", "heavy duty", "professional quality",
    "award winning", "100% quality", "guarantee", "t-shirt", "shirt", "tee",
    "hoodie", "apparel", "fitted", "looser", "size up", "bigger size",
    "maternity", "sizing", "material", "neon", "glitter", "sparkle",
    "sparkling", "glow in the dark", "glow effect", "glows in black light",
    "metallic", "foil", "rose gold", "sequin", "texture", "textured",
    "wood", "marble", "holographic", "3d", "embroidered", "antimicrobial",
    "antibacterial", "antifungal", "antiseptic", "disinfectant", "repellent",
    "insecticide", "germ", "virus", "bacteria", "non-toxic", "safe",
    "harmless", "eco-friendly", "biodegradable", "bpa free", "hypoallergenic",
    "therapeutic", "cure", "heal", "treatment", "remedy", "detoxify",
    "disney", "marvel", "star wars", "harry potter", "dc comics", "nintendo",
    "hello kitty", "amazon", "prime", "kindle", "alexa", "aws",
    "taylor swift", "trump",
]

ALL_BANNED: list[str] = list(set(RESTRICTED_WORDS + [b.lower() for b in ADDITIONAL_BANNED]))


def scan_text(text: str) -> list[str]:
    """Scan text for banned/restricted words. Returns list of flagged words."""
    text_lower = text.lower()
    flagged = []
    for word in ALL_BANNED:
        if " " in word:
            if word in text_lower:
                flagged.append(word)
        else:
            pattern = r"\b" + re.escape(word) + r"\b"
            if re.search(pattern, text_lower):
                flagged.append(word)
    return list(set(flagged))


def is_compliant(text: str) -> bool:
    """Returns True if text contains no banned words."""
    return len(scan_text(text)) == 0


def check_niche_keywords(keywords: list[str]) -> dict:
    """
    Check a list of niche keywords for compliance issues.
    Returns dict mapping each keyword to its flagged terms (empty list if clean).
    """
    results = {}
    for kw in keywords:
        results[kw] = scan_text(kw)
    return results
