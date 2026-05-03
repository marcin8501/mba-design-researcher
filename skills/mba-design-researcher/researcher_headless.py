"""
researcher_headless.py — MBA Design Research Agent (Headless Version)
Runs the full 6-phase pipeline without a browser, using APIs and HTTP requests.
Includes deduplication, history tracking, seed rotation, and delta reporting.

Usage:
    export OPENAI_API_KEY=your_key
    python researcher_headless.py
"""

import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# Add current dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compliance import scan_text, check_niche_keywords

client = OpenAI()

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = Path(SKILL_DIR) / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
HISTORY_FILE = Path(SKILL_DIR) / "output" / "history.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Config ────────────────────────────────────────────────────────────────────

# Seed pools — the agent rotates through these across sessions
SEED_POOLS = [
    # Pool A — Core niches
    [
        "funny t-shirt", "nurse humor", "programmer jokes", "fishing gifts",
        "dog mom", "cat dad", "teacher appreciation", "gym motivation",
        "dad jokes", "retirement gifts",
    ],
    # Pool B — Profession & hobby niches
    [
        "firefighter humor", "accountant jokes", "mechanic gifts",
        "gardening lover", "hiking adventure", "camping outdoor",
        "gamer nerd", "chef cooking humor", "pilot aviation",
        "electrician funny",
    ],
    # Pool C — Identity & life event niches
    [
        "new grandma", "promoted to daddy", "first time mom",
        "class of 2026", "birthday queen", "bachelor party",
        "bridal shower", "pregnancy announcement", "divorce party",
        "40th birthday humor",
    ],
    # Pool D — Trending & seasonal
    [
        "AI humor", "work from home", "introvert funny",
        "sarcastic quotes", "millennial humor", "gen z slang",
        "plant mom", "coffee addict", "wine lover",
        "true crime obsessed",
    ],
]

MAX_NICHES_TO_ANALYZE = 30
MAX_BRIEFS_TO_GENERATE = 20


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY & DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def load_history() -> dict:
    """Load the master history database."""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {
        "sessions": [],
        "all_keywords": {},       # keyword -> {first_seen, last_seen, times_found, scores: []}
        "all_niches": {},         # keyword -> latest full niche data
        "total_sessions": 0,
        "last_seed_pool": -1,     # tracks which seed pool was used last
    }


def save_history(history: dict):
    """Save the master history database."""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def get_known_keywords(history: dict) -> set:
    """Get all previously discovered keywords."""
    return set(k.lower() for k in history.get("all_keywords", {}))


def is_duplicate(keyword: str, history: dict) -> bool:
    """Check if a keyword has already been fully researched (had a brief generated)."""
    kw_lower = keyword.lower()
    kw_data = history.get("all_keywords", {}).get(kw_lower, {})
    return kw_data.get("brief_generated", False)


def update_history(history: dict, session_id: str, new_opportunities: list[dict],
                   all_candidates: list[dict], seed_pool_idx: int):
    """Update the master history with results from this session."""
    now = datetime.now().isoformat()

    # Record session
    session_entry = {
        "session_id": session_id,
        "timestamp": now,
        "seed_pool_used": seed_pool_idx,
        "candidates_found": len(all_candidates),
        "new_opportunities": len(new_opportunities),
        "keywords": [o["keyword"] for o in new_opportunities],
    }
    history["sessions"].append(session_entry)
    history["total_sessions"] = len(history["sessions"])
    history["last_seed_pool"] = seed_pool_idx

    # Update keyword tracking
    for candidate in all_candidates:
        kw = candidate.get("keyword", "").lower()
        if not kw:
            continue
        if kw not in history["all_keywords"]:
            history["all_keywords"][kw] = {
                "first_seen": now,
                "last_seen": now,
                "times_found": 1,
                "scores": [],
                "brief_generated": False,
            }
        else:
            history["all_keywords"][kw]["last_seen"] = now
            history["all_keywords"][kw]["times_found"] += 1

    # Update with full niche data for new opportunities
    for opp in new_opportunities:
        kw = opp["keyword"].lower()
        score = opp.get("competition_data", {}).get("opportunity_score", {}).get("total_score", 0)

        history["all_keywords"][kw]["brief_generated"] = True
        history["all_keywords"][kw]["scores"].append({
            "session": session_id,
            "score": score,
            "timestamp": now,
        })
        history["all_niches"][kw] = opp

    save_history(history)


def get_next_seed_pool(history: dict) -> tuple[int, list[str]]:
    """Rotate to the next seed pool."""
    last = history.get("last_seed_pool", -1)
    next_idx = (last + 1) % len(SEED_POOLS)
    return next_idx, SEED_POOLS[next_idx]


def detect_score_changes(history: dict, new_opportunities: list[dict]) -> list[dict]:
    """Detect niches whose scores have changed since last seen."""
    changes = []
    for opp in new_opportunities:
        kw = opp["keyword"].lower()
        kw_data = history.get("all_keywords", {}).get(kw, {})
        scores = kw_data.get("scores", [])
        if len(scores) >= 2:
            prev_score = scores[-2]["score"]
            curr_score = scores[-1]["score"]
            if prev_score != curr_score:
                changes.append({
                    "keyword": opp["keyword"],
                    "previous_score": prev_score,
                    "current_score": curr_score,
                    "direction": "UP" if curr_score > prev_score else "DOWN",
                    "delta": curr_score - prev_score,
                })
    return changes


# ── Knowledge Base Loading ────────────────────────────────────────────────────

def load_kb(filename):
    path = os.path.join(SKILL_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


A10_KB = load_kb("A10AlgorithmParadigm.txt")
LEGAL_KB = load_kb("LegalCompliance,Copyright&ContentPolicies.txt")
MARKET_KB = load_kb("AdvancedMarketResearch&NicheValidation.txt")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: TREND DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

def get_amazon_autocomplete(seed: str) -> list[str]:
    """Get Amazon search autocomplete suggestions via their public API."""
    encoded = urllib.parse.quote(seed)
    url = (
        f"https://completion.amazon.com/api/2017/suggestions"
        f"?lop=en_US&site-variant=desktop&client-info=amazon-search-ui"
        f"&mid=ATVPDKIKX0DER&alias=fashion-novelty&prefix={encoded}"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return [s.get("value", "") for s in data.get("suggestions", []) if s.get("value")]
    except Exception:
        pass
    return []


def discover_autocomplete_niches(seed_keywords: list[str]) -> list[dict]:
    """Use Amazon Autocomplete to discover sub-niches with alphabet expansion."""
    niches = []
    seen = set()

    for seed in seed_keywords:
        print(f"    Autocomplete: '{seed}'")
        # Direct suggestions
        suggestions = get_amazon_autocomplete(seed)
        for s in suggestions:
            if s.lower() not in seen:
                seen.add(s.lower())
                niches.append({"source": "amazon_autocomplete", "seed": seed, "suggestion": s})

        # Alphabet expansion
        for letter in "abcdefghijklmnopqrstuvwxyz":
            expanded = f"{seed} {letter}"
            suggestions = get_amazon_autocomplete(expanded)
            for s in suggestions:
                if s.lower() not in seen:
                    seen.add(s.lower())
                    niches.append({"source": "amazon_autocomplete_expanded", "seed": expanded, "suggestion": s})
            time.sleep(0.2)

        time.sleep(0.5)

    return niches


def get_google_trends_suggestions(seed: str) -> list[str]:
    """Get Google Trends autocomplete/related suggestions."""
    url = f"https://trends.google.com/trends/api/autocomplete/{urllib.parse.quote(seed)}?hl=en-US&tz=240"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            text = resp.text
            if text.startswith(")]}'"):
                text = text[5:]
            data = json.loads(text)
            topics = data.get("default", {}).get("topics", [])
            return [t.get("title", "") for t in topics if t.get("title")]
    except Exception:
        pass
    return []


def scrape_reddit_titles(subreddit: str, limit: int = 25) -> list[dict]:
    """Scrape Reddit post titles via JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    headers = {**HEADERS, "User-Agent": "MBA-Research-Agent/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            return [
                {
                    "source": "reddit",
                    "subreddit": subreddit,
                    "title": p["data"]["title"],
                    "score": p["data"].get("score", 0),
                }
                for p in posts
                if p.get("data", {}).get("title")
            ]
    except Exception:
        pass
    return []


def run_trend_discovery(seed_keywords: list[str]) -> dict:
    """Phase 1: Collect trend signals from multiple sources."""
    print("\n  [1a] Amazon Autocomplete discovery...")
    autocomplete = discover_autocomplete_niches(seed_keywords)
    print(f"       Found {len(autocomplete)} autocomplete suggestions")

    print("\n  [1b] Google Trends suggestions...")
    google_trends = []
    for seed in seed_keywords[:5]:
        suggestions = get_google_trends_suggestions(seed)
        for s in suggestions:
            google_trends.append({"source": "google_trends", "seed": seed, "query": s})
        time.sleep(0.5)
    print(f"       Found {len(google_trends)} Google Trends signals")

    print("\n  [1c] Reddit scanning...")
    reddit = []
    for sub in ["MerchByAmazon", "AmazonMerch", "Entrepreneur"]:
        posts = scrape_reddit_titles(sub)
        reddit.extend(posts)
        time.sleep(1)
    print(f"       Found {len(reddit)} Reddit signals")

    print("\n  [1d] AI-powered trend expansion...")
    ai_niches = generate_ai_trend_ideas(seed_keywords)
    print(f"       Generated {len(ai_niches)} AI trend ideas")

    total = len(autocomplete) + len(google_trends) + len(reddit) + len(ai_niches)
    print(f"\n  Total trend signals: {total}")

    return {
        "autocomplete_niches": autocomplete,
        "google_trends": google_trends,
        "reddit_signals": reddit,
        "ai_trend_ideas": ai_niches,
        "total_signals": total,
    }


def generate_ai_trend_ideas(seed_keywords: list[str]) -> list[dict]:
    """Use AI to brainstorm trending niche ideas based on seeds and current market."""
    seeds_str = ", ".join(seed_keywords)
    prompt = f"""You are an expert Merch by Amazon niche researcher with deep knowledge of 2026 trends.

Based on these seed keywords: {seeds_str}

Generate 50 promising t-shirt niche ideas. Focus on:
- Evergreen niches with consistent demand (professions, hobbies, identities)
- Cross-niche intersections (e.g., "Cat Dad" + "Fishing" = "Cat Dad Fishing")
- Trending cultural moments, memes, and viral topics in 2026
- Underserved micro-niches that big sellers overlook
- Gift-oriented niches (birthday, retirement, graduation, holidays)
- Humor-based niches (sarcasm, puns, inside jokes for specific groups)

For each, provide the niche keyword as you'd search it on Amazon.

CRITICAL: Do NOT include these words in the keyword: "shirt", "t-shirt", "tee", "t shirt", "tshirt", "apparel", "gift", "gifts", "present", "clothing". These are MBA restricted words. The keyword should describe the NICHE/TOPIC only (e.g., "firefighter sarcasm humor" NOT "firefighter sarcasm t shirt").

Output JSON only:
{{
  "niches": [
    {{
      "keyword": "the search keyword",
      "category": "EVERGREEN/SEASONAL/TRENDING",
      "audience": "who buys this",
      "rationale": "why this is promising"
    }}
  ]
}}"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    return result.get("niches", [])


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: NICHE DRILLING (with deduplication)
# ══════════════════════════════════════════════════════════════════════════════

def extract_candidate_niches(trend_data: dict, known_keywords: set) -> tuple[list[dict], int]:
    """Use AI to analyze raw trend data and extract the best candidate niches.
    Returns (candidates, skipped_count) where skipped are known duplicates."""
    signals = []

    for item in trend_data.get("autocomplete_niches", [])[:50]:
        signals.append(f"Amazon Autocomplete: {item.get('suggestion', '')}")

    for item in trend_data.get("google_trends", [])[:20]:
        signals.append(f"Google Trends: {item.get('query', '')}")

    for item in trend_data.get("reddit_signals", [])[:15]:
        signals.append(f"Reddit ({item.get('subreddit', '')}): {item.get('title', '')}")

    for item in trend_data.get("ai_trend_ideas", [])[:50]:
        signals.append(f"AI Idea: {item.get('keyword', '')} — {item.get('rationale', '')}")

    # Tell AI about already-researched niches so it avoids them
    known_list = ", ".join(sorted(known_keywords)[:100]) if known_keywords else "(none)"

    signals_text = "\n".join(signals)

    prompt = f"""You are an expert Merch by Amazon niche researcher.

Analyze these trend signals and extract the {MAX_NICHES_TO_ANALYZE} most promising
niche keywords for MBA t-shirt designs.

IMPORTANT: These niches have ALREADY been researched in previous sessions. Do NOT suggest them again:
{known_list}

Also avoid close variations of the above (e.g., if "cat dad fishing" was done, don't suggest "fishing cat dad").

Prioritize:
- Clear buyer intent (someone would actually buy a t-shirt about this)
- Specific enough to be a real niche (not too broad like "funny")
- Evergreen preferred over fads
- Cross-niche intersections are gold
- Specific audiences: professions, hobbies, identities, life events
- FRESH ideas not covered in previous sessions

CRITICAL: Do NOT include these words in the keyword: "shirt", "t-shirt", "tee", "t shirt", "tshirt", "apparel", "gift", "gifts", "present", "clothing". These are MBA restricted words. The keyword should describe the NICHE/TOPIC only (e.g., "firefighter sarcasm humor" NOT "firefighter sarcasm t shirt").

Trend signals:
{signals_text}

Output JSON only:
{{
  "candidate_niches": [
    {{
      "keyword": "the niche keyword phrase to search on Amazon",
      "rationale": "why this is promising",
      "estimated_demand": "HIGH/MEDIUM/LOW",
      "niche_type": "EVERGREEN/SEASONAL/TRENDING",
      "target_audience": "who would buy this"
    }}
  ]
}}"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    all_candidates = result.get("candidate_niches", [])

    # Second-pass deduplication: filter out any that AI still suggested despite instructions
    filtered = []
    skipped = 0
    for cn in all_candidates:
        kw = cn.get("keyword", "").lower().strip()
        # Check exact match
        if kw in known_keywords:
            skipped += 1
            print(f"  [DEDUP] Skipping known niche: '{cn['keyword']}'")
            continue
        # Check fuzzy match (>80% word overlap)
        kw_words = set(kw.split())
        is_dup = False
        for known in known_keywords:
            known_words = set(known.split())
            if len(kw_words) > 0 and len(known_words) > 0:
                overlap = len(kw_words & known_words) / max(len(kw_words), len(known_words))
                if overlap >= 0.8:
                    skipped += 1
                    print(f"  [DEDUP] Skipping similar niche: '{cn['keyword']}' (similar to '{known}')")
                    is_dup = True
                    break
        if not is_dup:
            filtered.append(cn)

    return filtered, skipped


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3: COMPETITION & DEMAND VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

MBA_SEARCH_URL = (
    "https://www.amazon.com/s?i=fashion-novelty&bbn=12035955011"
    "&rh=p_6%3AATVPDKIKX0DER&hidden-keywords={keyword}"
)


def estimate_competition_ai(keyword: str) -> dict:
    """Use AI to estimate competition level based on niche knowledge."""
    try:
        prompt = f"""You are an expert Merch by Amazon analyst with deep knowledge of the marketplace.
Estimate the competition level for this niche keyword on Amazon MBA:

Keyword: "{keyword}"

Based on your knowledge, estimate:
1. How many competing designs likely exist (give a specific number)
2. Competition level: LOW (under 500), MEDIUM (500-2000), HIGH (2000-10000), VERY_HIGH (10000+)
3. Average price point for this niche ($)

Consider: How popular is this niche? Is it evergreen or seasonal? How specific/narrow is it?
Narrower cross-niche combinations (e.g., "cat dad fishing") have LESS competition than broad terms (e.g., "funny nurse").

Output JSON only:
{{
  "estimated_designs": 1500,
  "competition_level": "MEDIUM",
  "estimated_avg_price": 19.99,
  "reasoning": "Brief explanation"
}}"""

        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"estimated_designs": 0, "competition_level": "UNKNOWN", "estimated_avg_price": 0, "reasoning": "Failed"}


def get_competition_count(keyword: str) -> dict:
    """Check competition count and top listings for a keyword via HTTP."""
    encoded = urllib.parse.quote(keyword)
    url = MBA_SEARCH_URL.format(keyword=encoded)

    result = {
        "keyword": keyword,
        "competition_count": 0,
        "top_listings": [],
        "avg_price": 0,
        "error": None,
        "data_source": "amazon_direct",
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract result count
            result_bar = soup.select_one(".s-breadcrumb .a-color-state, .sg-col-inner .a-section .a-spacing-small span")
            if result_bar:
                match = re.search(r'of\s+(?:over\s+)?([\d,]+)\s+results?', result_bar.text)
                if match:
                    result["competition_count"] = int(match.group(1).replace(",", ""))
                else:
                    match = re.search(r'([\d,]+)\s+results?', result_bar.text)
                    if match:
                        result["competition_count"] = int(match.group(1).replace(",", ""))

            # Also try the broader page text
            if result["competition_count"] == 0:
                page_text = resp.text
                match = re.search(r'of\s+(?:over\s+)?([\d,]+)\s+results?', page_text)
                if match:
                    result["competition_count"] = int(match.group(1).replace(",", ""))
                else:
                    match = re.search(r'"totalResultCount"[:\s]+([\d]+)', page_text)
                    if match:
                        result["competition_count"] = int(match.group(1))

            # Extract top listings
            items = soup.select("[data-component-type='s-search-result']")
            prices = []
            for item in items[:10]:
                title_el = item.select_one("h2 a span, .a-text-normal")
                title = title_el.text.strip() if title_el else ""

                price_el = item.select_one(".a-price .a-offscreen")
                price = price_el.text.strip() if price_el else ""

                asin = item.get("data-asin", "")

                if title:
                    result["top_listings"].append({
                        "title": title,
                        "price": price,
                        "asin": asin,
                    })

                    price_clean = price.replace("$", "").replace(",", "")
                    try:
                        prices.append(float(price_clean))
                    except (ValueError, TypeError):
                        pass

            if prices:
                result["avg_price"] = round(sum(prices) / len(prices), 2)

        elif resp.status_code == 503:
            result["error"] = "Amazon rate limited (503)"
        else:
            result["error"] = f"HTTP {resp.status_code}"

    except Exception as e:
        result["error"] = str(e)

    # Fallback: if Amazon returned 0 or errored, use AI estimation
    if result["competition_count"] == 0:
        ai_est = estimate_competition_ai(keyword)
        est_designs = ai_est.get("estimated_designs", 0)
        if est_designs > 0:
            result["competition_count"] = est_designs
            result["data_source"] = "ai_estimate"
            result["competition_level"] = ai_est.get("competition_level", "UNKNOWN")
            result["ai_reasoning"] = ai_est.get("reasoning", "")
            if ai_est.get("estimated_avg_price", 0) > 0:
                result["avg_price"] = ai_est["estimated_avg_price"]
            result["error"] = None
        else:
            result["data_source"] = "unknown"

    return result


def calculate_opportunity_score(competition: int, avg_price: float, listing_count: int) -> dict:
    """Score a niche opportunity (0-100)."""
    score = 0
    breakdown = {}

    # Competition (max 35)
    confidence = "HIGH"
    if competition == 0:
        comp_score = 10  # Unknown — penalize uncertainty
        confidence = "LOW"
    elif competition < 500:
        comp_score = 35
    elif competition < 2000:
        comp_score = 28
    elif competition < 5000:
        comp_score = 18
    elif competition < 10000:
        comp_score = 10
    else:
        comp_score = 4
    breakdown["competition"] = comp_score
    score += comp_score

    # Price margin (max 25)
    if avg_price >= 22:
        price_score = 25
    elif avg_price >= 19:
        price_score = 20
    elif avg_price >= 16:
        price_score = 12
    elif avg_price > 0:
        price_score = 6
    else:
        price_score = 10  # Unknown
    breakdown["price_margin"] = price_score
    score += price_score

    # Quality gap (max 20)
    if listing_count < 3:
        quality_score = 20
    elif listing_count < 6:
        quality_score = 15
    elif listing_count < 10:
        quality_score = 10
    else:
        quality_score = 5
    breakdown["quality_gap"] = quality_score
    score += quality_score

    # Base demand estimate (max 20) — will be refined by AI
    breakdown["demand_base"] = 10
    score += 10

    breakdown["confidence"] = confidence

    if score >= 70:
        rating = "GOLDMINE"
    elif score >= 55:
        rating = "HIGH_PRIORITY"
    elif score >= 40:
        rating = "MODERATE"
    elif score >= 25:
        rating = "LOW_PRIORITY"
    else:
        rating = "AVOID"

    return {"total_score": score, "max_score": 100, "rating": rating, "breakdown": breakdown}


def analyze_niches(candidate_niches: list[dict]) -> list[dict]:
    """Phase 3: Analyze competition for all candidate niches."""
    analyzed = []

    for i, cn in enumerate(candidate_niches[:MAX_NICHES_TO_ANALYZE], 1):
        keyword = cn["keyword"]
        print(f"  [{i}/{min(len(candidate_niches), MAX_NICHES_TO_ANALYZE)}] '{keyword}'...", end=" ")

        comp_data = get_competition_count(keyword)

        if comp_data.get("error"):
            print(f"Error: {comp_data['error']}")
            comp_data["competition_count"] = 0

        score = calculate_opportunity_score(
            comp_data["competition_count"],
            comp_data["avg_price"],
            len(comp_data["top_listings"]),
        )

        entry = {
            "keyword": keyword,
            "rationale": cn.get("rationale", ""),
            "estimated_demand": cn.get("estimated_demand", ""),
            "niche_type": cn.get("niche_type", ""),
            "target_audience": cn.get("target_audience", ""),
            "competition_count": comp_data["competition_count"],
            "avg_price": comp_data["avg_price"],
            "top_listings": comp_data["top_listings"],
            "data_source": comp_data.get("data_source", "unknown"),
            "opportunity_score": score,
            "timestamp": datetime.now().isoformat(),
        }
        analyzed.append(entry)

        src = comp_data.get('data_source', 'unknown')
        conf = '⚠️EST' if src != 'amazon_direct' else '✓'
        print(f"Comp: {comp_data['competition_count']} [{conf}] | Price: ${comp_data['avg_price']} | Score: {score['total_score']} ({score['rating']})")

        time.sleep(2)  # Rate limiting for Amazon

    # Sort by score
    analyzed.sort(key=lambda x: x["opportunity_score"]["total_score"], reverse=True)
    return analyzed


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4: COMPLIANCE & IP CHECK
# ══════════════════════════════════════════════════════════════════════════════

RED_FLAG_PATTERNS = [
    r"\b(anti.?microbial|anti.?bacterial|anti.?fungal|repell|insecticid|germ.?free)\b",
    r"\b(disney|marvel|star\s*wars|harry\s*potter|dc\s*comics|nintendo|hello\s*kitty)\b",
    r"\b(neon|glitter|metallic|holographic|glow|embroidered|sequin)\b",
    r"\b(trump|biden|maga|political|election)\b",
]


def detect_red_flags(text: str) -> list[str]:
    flags = []
    text_lower = text.lower()
    for pattern in RED_FLAG_PATTERNS:
        matches = re.findall(pattern, text_lower)
        if matches:
            flags.extend(matches)
    return list(set(flags))


def validate_niches(analyzed_niches: list[dict]) -> list[dict]:
    """Phase 4: Run compliance checks on all analyzed niches."""
    validated = []
    rejected = 0

    for niche in analyzed_niches:
        keyword = niche["keyword"]

        # Restricted words check
        issues = scan_text(keyword)

        # Red flag check
        red_flags = detect_red_flags(keyword)

        if issues or red_flags:
            rejected += 1
            niche["validation"] = {
                "verdict": "REJECTED",
                "restricted_words": issues,
                "red_flags": red_flags,
            }
            print(f"  REJECTED: '{keyword}' — {issues + red_flags}")
        else:
            niche["validation"] = {
                "verdict": "APPROVED",
                "restricted_words": [],
                "red_flags": [],
            }
            validated.append(niche)

    print(f"\n  Approved: {len(validated)} | Rejected: {rejected}")
    return validated


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5: DESIGN BRIEF GENERATION
# ══════════════════════════════════════════════════════════════════════════════

BRIEF_SYSTEM_PROMPT = f"""You are an expert Merch by Amazon design strategist, listing copywriter, and AI image generation prompt engineer.

You follow these knowledge bases as your single source of truth:

=== A10 ALGORITHM RULES ===
{A10_KB[:3000]}

=== LEGAL COMPLIANCE ===
{LEGAL_KB[:2000]}

Your job is to generate design briefs, AI image generation prompts, and pre-written listing copy.

CRITICAL LISTING RULES:
- Title max 60 chars. Formula: [Primary Keyword] + [Audience] + [Occasion]
- Do NOT include "T-Shirt", "Tee", "Shirt", "Apparel" in title
- Bullet 1: Who & Why formula
- Bullet 2: What & Where + Cross-Sell formula
- Description: 3-4 natural sentences, LSI keywords, Google SEO optimized
- NEVER use banned/restricted words
- No keyword stuffing, no ALL CAPS, no emojis
- Backend keywords: max 250 bytes, no commas, no repeated words from title/bullets

=== AI IMAGE GENERATION MODEL ROUTING ===
You MUST recommend the best AI model for each design and provide model-specific prompts:

**Ideogram v3** — BEST FOR: Text/slogan designs, typographic art, quote-based designs, any design where readable text is the main element. Most MBA bestsellers are text-based, so this is the default choice.
Prompt structure: "[slogan text in quotes]", [typographic style], [decorative elements around text], [color palette], white background, centered layout, print-ready t-shirt design

**Midjourney v7** — BEST FOR: Illustration-heavy designs, artistic/stylized output. Niches: cottagecore, dark academia, fantasy, botanical, watercolor, concept art, animals, nature scenes.
Prompt structure: [subject], [style adjective], [art medium], [color palette], centered composition, white background, isolated design, high detail, print-ready --ar 1:1 --style raw

**Flux 2** — BEST FOR: Photorealistic designs, lifestyle imagery, retro photography aesthetic, vintage photo style.
Prompt structure: [subject in context], [photographic style], [lighting], [color treatment], isolated on white background, high resolution, print quality, commercial photography aesthetic

ROUTING RULES:
- If the design is primarily TEXT/SLOGAN based → Ideogram v3
- If the design is primarily ILLUSTRATION/ART based → Midjourney v7
- If the design needs PHOTOREALISTIC look → Flux 2
- If the design combines text + illustration → provide BOTH an Ideogram v3 prompt AND a Midjourney v7 prompt

=== IMAGE PROMPT QUALITY RULES ===
- Every prompt MUST specify: white background, isolated design, print-ready
- Include specific color palette (2-3 colors max for screen printing)
- Include composition notes (centered, balanced)
- For text designs: specify exact text in quotes, typography style, decorative elements
- For illustration designs: specify art medium, style reference, level of detail
- Provide 3 VARIANT prompts per design (different style/composition/color approaches)
- Each variant should be meaningfully different, not just word swaps

=== FILE PREPARATION SPECS ===
MBA requires: 4500x5400px, PNG, transparent background
Workflow: Generate at 1024x1024 → Remove background (Recraft) → Upscale 4x (Recraft Crisp Upscale for illustrations, Topaz for photorealistic) → Canvas resize to 4500x5400
"""


def generate_design_brief(niche: dict) -> dict:
    """Generate a complete design brief with AI model routing, image prompts, and listing copy."""
    keyword = niche["keyword"]
    top_titles = [l.get("title", "") for l in niche.get("top_listings", [])[:5]]
    top_titles_str = "\n".join(f"  - {t}" for t in top_titles) if top_titles else "  (no data)"
    data_source = niche.get("data_source", "unknown")
    confidence = "ESTIMATED" if data_source != "amazon_direct" else "VERIFIED"

    prompt = f"""Generate a complete design brief with AI image generation prompts and listing copy for this MBA niche:

Niche: {keyword}
Target Audience: {niche.get('target_audience', 'General')}
Competition: {niche.get('competition_count', 'Unknown')} designs ({confidence} — data source: {data_source})
Avg Price: ${niche.get('avg_price', 'Unknown')}
Type: {niche.get('niche_type', 'Unknown')}

Top competing titles:
{top_titles_str}

IMPORTANT: You MUST:
1. Decide the best AI image generation model for this design (Ideogram v3, Midjourney v7, or Flux 2)
2. Provide 3 detailed, production-ready image prompts optimized for that specific model
3. Each prompt variant must be meaningfully different (different style, composition, or color approach)
4. If the design combines text + illustration, provide prompts for BOTH Ideogram v3 AND Midjourney v7

Output JSON only:
{{
  "design_brief": {{
    "suggested_text_quote": "The main text/quote for the design",
    "visual_style": "Describe the visual style in detail",
    "design_type": "TEXT_SLOGAN or ILLUSTRATION or PHOTOREALISTIC or TEXT_PLUS_ILLUSTRATION",
    "color_recommendations": ["color1", "color2", "color3"],
    "target_shirt_colors": ["black", "navy", "dark heather"],
    "design_elements": "Describe graphic elements to include",
    "differentiation_strategy": "How this design stands out from competition"
  }},
  "ai_image_generation": {{
    "recommended_model": "Ideogram v3 or Midjourney v7 or Flux 2",
    "model_rationale": "Why this model is the best choice for this specific design",
    "primary_prompts": [
      {{
        "model": "The specific model this prompt is for",
        "prompt": "The complete, detailed, copy-paste-ready prompt optimized for this model. Include all style parameters, colors, composition notes, background specs.",
        "variant_name": "e.g., Bold Retro Style",
        "variant_description": "What makes this variant different"
      }},
      {{
        "model": "model name",
        "prompt": "Second variant prompt — different style or composition",
        "variant_name": "e.g., Minimalist Clean",
        "variant_description": "What makes this variant different"
      }},
      {{
        "model": "model name",
        "prompt": "Third variant prompt — different color or artistic approach",
        "variant_name": "e.g., Vintage Distressed",
        "variant_description": "What makes this variant different"
      }}
    ],
    "secondary_prompts": [
      {{
        "model": "Alternative model if design type is TEXT_PLUS_ILLUSTRATION",
        "prompt": "Alternative prompt for the secondary model",
        "variant_name": "Alternative approach",
        "variant_description": "Why try this model too"
      }}
    ],
    "negative_prompt_notes": "What to avoid in generation (e.g., no gradients, no shadows, no complex backgrounds)",
    "post_processing": {{
      "background_removal": "Recraft Remove Background",
      "upscaling": "Recraft Crisp Upscale for illustrations / Topaz for photorealistic",
      "final_dimensions": "4500x5400px PNG with transparent background",
      "color_mode": "RGB, sRGB color space"
    }}
  }},
  "listing_copy": {{
    "title": "Max 60 chars, following the formula",
    "brand_name": "Hybrid brand name",
    "bullet1": "Who & Why formula",
    "bullet2": "What & Where + Cross-Sell formula",
    "description": "3-4 sentences, LSI keywords, Google SEO",
    "backend_keywords": "Space-separated, no commas, no repeats"
  }},
  "keyword_research": {{
    "root_keyword": "Main keyword",
    "long_tail_keywords": ["3+ word phrases"],
    "lsi_keywords": ["related terms"],
    "audience_keywords": ["who buys this"],
    "occasion_keywords": ["when to buy"]
  }},
  "cross_niche_ideas": [
    {{
      "combination": "Niche + Audience intersection",
      "example_text": "Suggested design text",
      "rationale": "Why this works"
    }}
  ]
}}"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)

    # Compliance check on generated copy
    listing = result.get("listing_copy", {})
    for field in ["title", "bullet1", "bullet2", "description"]:
        text = listing.get(field, "")
        issues = scan_text(text)
        if issues:
            print(f"      [Compliance] Fixing {field}: {issues}")
            listing[field] = fix_compliance(text, issues)

    result["listing_copy"] = listing
    return result


def fix_compliance(text: str, issues: list[str]) -> str:
    """Rewrite text to remove compliance issues."""
    prompt = f"""Rewrite this MBA listing text, removing these banned words: {issues}

Original: {text}

Rules: Keep same meaning. Do NOT use banned words or variations. Output ONLY the rewritten text."""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    return response.choices[0].message.content.strip().strip('"')


def generate_briefs(validated_niches: list[dict]) -> list[dict]:
    """Phase 5: Generate design briefs for all validated niches."""
    opportunities = []

    for i, niche in enumerate(validated_niches[:MAX_BRIEFS_TO_GENERATE], 1):
        keyword = niche["keyword"]
        print(f"  [{i}/{min(len(validated_niches), MAX_BRIEFS_TO_GENERATE)}] '{keyword}'...", end=" ")

        brief = generate_design_brief(niche)

        opportunity = {
            "keyword": keyword,
            "competition_data": {
                "competition_count": niche.get("competition_count", 0),
                "avg_price": niche.get("avg_price", 0),
                "top_listings": niche.get("top_listings", []),
                "opportunity_score": niche.get("opportunity_score", {}),
            },
            "validation": niche.get("validation", {}),
            "niche_type": niche.get("niche_type", ""),
            "target_audience": niche.get("target_audience", ""),
            "design_brief": brief,
        }
        opportunities.append(opportunity)

        title = brief.get("listing_copy", {}).get("title", "")
        print(f"Title: {title}")

    return opportunities


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6: REPORT GENERATION (with delta reporting)
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(opportunities: list[dict], session_id: str, seed_pool_idx: int,
                    skipped_count: int, history: dict, score_changes: list[dict]) -> str:
    """Generate a human-readable markdown report with delta information."""
    total_historical = len(history.get("all_keywords", {}))
    total_sessions = history.get("total_sessions", 0)

    lines = [
        f"# MBA Design Research Report — Session {session_id}",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Seed Pool Used:** Pool {chr(65 + seed_pool_idx)} ({SEED_POOLS[seed_pool_idx][0]}, {SEED_POOLS[seed_pool_idx][1]}, ...)",
        f"**New Opportunities This Session:** {len(opportunities)}",
        f"**Duplicates Skipped:** {skipped_count}",
        f"**Total Historical Niches:** {total_historical}",
        f"**Total Sessions Run:** {total_sessions}",
        "",
        "> This report shows ONLY new opportunities not found in previous sessions.",
        "",
    ]

    # Score changes section
    if score_changes:
        lines.append("## Score Evolution (Returning Niches)")
        lines.append("")
        lines.append("| Niche | Previous Score | Current Score | Change |")
        lines.append("|-------|---------------|---------------|--------|")
        for sc in score_changes:
            arrow = "↑" if sc["direction"] == "UP" else "↓"
            lines.append(f"| {sc['keyword']} | {sc['previous_score']} | {sc['current_score']} | {arrow} {abs(sc['delta'])} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    sorted_opps = sorted(
        opportunities,
        key=lambda x: x.get("competition_data", {}).get("opportunity_score", {}).get("total_score", 0),
        reverse=True,
    )

    for i, opp in enumerate(sorted_opps, 1):
        kw = opp.get("keyword", "Unknown")
        score = opp.get("competition_data", {}).get("opportunity_score", {})
        comp = opp.get("competition_data", {})
        brief = opp.get("design_brief", {})
        listing = brief.get("listing_copy", {})
        design = brief.get("design_brief", {})
        keywords = brief.get("keyword_research", {})
        cross = brief.get("cross_niche_ideas", [])

        lines.append(f"## #{i}: {kw}")
        lines.append(f"**Score:** {score.get('total_score', 'N/A')}/100 ({score.get('rating', 'N/A')})")
        lines.append(f"**Type:** {opp.get('niche_type', 'N/A')} | **Audience:** {opp.get('target_audience', 'N/A')}")
        data_src = comp.get('data_source', opp.get('data_source', 'unknown'))
        conf_label = ' (ESTIMATED)' if data_src != 'amazon_direct' else ' (VERIFIED)'
        lines.append(f"**Competition:** {comp.get('competition_count', 'N/A')} designs{conf_label} | **Avg Price:** ${comp.get('avg_price', 'N/A')}")
        lines.append("")

        if design:
            lines.append("### Design Brief")
            lines.append(f"- **Suggested Text:** {design.get('suggested_text_quote', '')}")
            lines.append(f"- **Design Type:** {design.get('design_type', 'N/A')}")
            lines.append(f"- **Visual Style:** {design.get('visual_style', '')}")
            lines.append(f"- **Colors:** {', '.join(design.get('color_recommendations', []))}")
            lines.append(f"- **Shirt Colors:** {', '.join(design.get('target_shirt_colors', []))}")
            lines.append(f"- **Elements:** {design.get('design_elements', '')}")
            lines.append(f"- **Differentiation:** {design.get('differentiation_strategy', '')}")
            lines.append("")

        # AI Image Generation section
        ai_gen = brief.get("ai_image_generation", {})
        if ai_gen:
            lines.append("### AI Image Generation")
            lines.append(f"**Recommended Model:** {ai_gen.get('recommended_model', 'N/A')}")
            lines.append(f"**Rationale:** {ai_gen.get('model_rationale', '')}")
            lines.append("")

            primary = ai_gen.get("primary_prompts", [])
            if primary:
                lines.append("#### Primary Prompts (copy-paste ready)")
                lines.append("")
                for j, p in enumerate(primary, 1):
                    lines.append(f"**Variant {j}: {p.get('variant_name', '')}** ({p.get('model', '')})")
                    lines.append(f"> {p.get('variant_description', '')}")
                    lines.append("")
                    lines.append(f"```")
                    lines.append(p.get("prompt", ""))
                    lines.append(f"```")
                    lines.append("")

            secondary = ai_gen.get("secondary_prompts", [])
            if secondary and secondary[0].get("prompt"):
                lines.append("#### Secondary Prompts (alternative model)")
                lines.append("")
                for p in secondary:
                    lines.append(f"**{p.get('variant_name', '')}** ({p.get('model', '')})")
                    lines.append(f"> {p.get('variant_description', '')}")
                    lines.append("")
                    lines.append(f"```")
                    lines.append(p.get("prompt", ""))
                    lines.append(f"```")
                    lines.append("")

            neg = ai_gen.get("negative_prompt_notes", "")
            if neg:
                lines.append(f"**Avoid:** {neg}")
                lines.append("")

            post = ai_gen.get("post_processing", {})
            if post:
                lines.append("#### Post-Processing Pipeline")
                lines.append(f"1. Background removal: {post.get('background_removal', 'Recraft')}")
                lines.append(f"2. Upscaling: {post.get('upscaling', 'Recraft Crisp Upscale')}")
                lines.append(f"3. Final size: {post.get('final_dimensions', '4500x5400px')}")
                lines.append(f"4. Color mode: {post.get('color_mode', 'RGB')}")
                lines.append("")

        if listing:
            lines.append("### Pre-Written Listing")
            lines.append(f"- **Title:** {listing.get('title', '')}")
            lines.append(f"- **Brand:** {listing.get('brand_name', '')}")
            lines.append(f"- **Bullet 1:** {listing.get('bullet1', '')}")
            lines.append(f"- **Bullet 2:** {listing.get('bullet2', '')}")
            lines.append(f"- **Description:** {listing.get('description', '')}")
            lines.append(f"- **Backend:** {listing.get('backend_keywords', '')}")
            lines.append("")

        if keywords:
            lines.append("### Keywords")
            lines.append(f"- **Root:** {keywords.get('root_keyword', '')}")
            lines.append(f"- **Long-tail:** {', '.join(keywords.get('long_tail_keywords', []))}")
            lines.append(f"- **LSI:** {', '.join(keywords.get('lsi_keywords', []))}")
            lines.append("")

        if cross:
            lines.append("### Cross-Niche Ideas")
            for idea in cross[:3]:
                lines.append(f"- **{idea.get('combination', '')}:** {idea.get('example_text', '')}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("\n" + "=" * 60)
    print("MBA DESIGN RESEARCH AGENT (Headless)")
    print(f"Session: {session_id}")
    print("=" * 60)

    # Load history
    history = load_history()
    known_keywords = get_known_keywords(history)
    print(f"\nHistory: {len(known_keywords)} known niches from {history.get('total_sessions', 0)} previous sessions")

    # Rotate seed pool
    seed_pool_idx, seed_keywords = get_next_seed_pool(history)
    print(f"Using Seed Pool {chr(65 + seed_pool_idx)}: {seed_keywords[:3]}...")

    # ── PHASE 1 ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 1: TREND DISCOVERY")
    print("=" * 60)
    trend_data = run_trend_discovery(seed_keywords)
    with open(OUTPUT_DIR / f"{session_id}_01_trend_data.json", "w") as f:
        json.dump(trend_data, f, indent=2)

    # ── PHASE 2 ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 2: NICHE DRILLING (AI Analysis + Deduplication)")
    print("=" * 60)
    candidates, skipped_count = extract_candidate_niches(trend_data, known_keywords)
    print(f"\nAI identified {len(candidates)} NEW candidate niches (skipped {skipped_count} duplicates):")
    for cn in candidates[:5]:
        print(f"  - {cn['keyword']} ({cn['estimated_demand']}, {cn['niche_type']})")
    with open(OUTPUT_DIR / f"{session_id}_02_candidate_niches.json", "w") as f:
        json.dump(candidates, f, indent=2)

    if not candidates:
        print("\n  No new niches found! All candidates were duplicates.")
        print("  Try running again — the seed pool will rotate automatically.")
        update_history(history, session_id, [], [], seed_pool_idx)
        return

    # ── PHASE 3 ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 3: COMPETITION & DEMAND VALIDATION")
    print("=" * 60)
    analyzed = analyze_niches(candidates)
    with open(OUTPUT_DIR / f"{session_id}_03_competition_analysis.json", "w") as f:
        json.dump(analyzed, f, indent=2)

    # ── PHASE 4 ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 4: COMPLIANCE CHECK")
    print("=" * 60)
    validated = validate_niches(analyzed)
    with open(OUTPUT_DIR / f"{session_id}_04_validated_niches.json", "w") as f:
        json.dump(validated, f, indent=2)

    # ── PHASE 5 ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 5: DESIGN BRIEF GENERATION")
    print("=" * 60)
    opportunities = generate_briefs(validated)
    with open(OUTPUT_DIR / f"{session_id}_05_design_briefs.json", "w") as f:
        json.dump(opportunities, f, indent=2)

    # ── Update History ────────────────────────────────────────────────────
    update_history(history, session_id, opportunities, candidates, seed_pool_idx)
    score_changes = detect_score_changes(history, opportunities)

    # ── PHASE 6 ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 6: FINAL REPORT (Delta)")
    print("=" * 60)
    report = generate_report(opportunities, session_id, seed_pool_idx,
                             skipped_count, history, score_changes)
    report_path = OUTPUT_DIR / f"{session_id}_RESEARCH_REPORT.md"
    with open(report_path, "w") as f:
        f.write(report)
    with open(OUTPUT_DIR / f"{session_id}_06_full_results.json", "w") as f:
        json.dump(opportunities, f, indent=2)

    # Also save a "latest" copy for easy access
    with open(OUTPUT_DIR / "LATEST_REPORT.md", "w") as f:
        f.write(report)
    with open(OUTPUT_DIR / "latest_results.json", "w") as f:
        json.dump(opportunities, f, indent=2)

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("SESSION COMPLETE")
    print(f"{'=' * 60}")
    print(f"Session ID: {session_id}")
    print(f"Seed Pool: {chr(65 + seed_pool_idx)}")
    print(f"Trend signals: {trend_data['total_signals']}")
    print(f"Candidates (new): {len(candidates)}")
    print(f"Duplicates skipped: {skipped_count}")
    print(f"Analyzed: {len(analyzed)}")
    print(f"Validated: {len(validated)}")
    print(f"Briefs generated: {len(opportunities)}")
    print(f"Total historical niches: {len(history.get('all_keywords', {}))}")
    print(f"\nReport: {report_path}")
    print(f"History: {HISTORY_FILE}")

    if score_changes:
        print(f"\nSCORE CHANGES DETECTED:")
        for sc in score_changes:
            arrow = "↑" if sc["direction"] == "UP" else "↓"
            print(f"  {sc['keyword']}: {sc['previous_score']} → {sc['current_score']} ({arrow}{abs(sc['delta'])})")

    # Top 5
    print("\nTOP 5 NEW OPPORTUNITIES:")
    sorted_opps = sorted(
        opportunities,
        key=lambda x: x.get("competition_data", {}).get("opportunity_score", {}).get("total_score", 0),
        reverse=True,
    )
    for i, opp in enumerate(sorted_opps[:5], 1):
        score = opp["competition_data"]["opportunity_score"]
        design = opp.get("design_brief", {}).get("design_brief", {})
        ai_gen = opp.get("design_brief", {}).get("ai_image_generation", {})
        print(f"  #{i}: {opp['keyword']}")
        print(f"      Score: {score['total_score']}/100 ({score['rating']})")
        print(f"      Design: {design.get('suggested_text_quote', 'N/A')}")
        print(f"      Model: {ai_gen.get('recommended_model', 'N/A')}")
        print()


if __name__ == "__main__":
    main()
