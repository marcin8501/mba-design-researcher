"""
competition_analyzer.py — Phase 3: Competition & Demand Validation
Checks competition density, BSR ranges, design quality signals,
and price distribution for candidate niches via nodriver.
"""

import asyncio
import json
import re
import urllib.parse
from datetime import datetime


# ── Competition Count Check ───────────────────────────────────────────────────

MBA_SEARCH_URL = (
    "https://www.amazon.com/s?i=fashion-novelty&bbn=12035955011"
    "&rh=p_6%3AATVPDKIKX0DER&hidden-keywords={keyword}"
)


async def get_competition_count(browser, keyword: str) -> int:
    """
    Check how many competing MBA designs exist for a keyword.
    Uses the MBA-specific search URL that filters for Merch products only.
    """
    encoded = urllib.parse.quote(keyword)
    url = MBA_SEARCH_URL.format(keyword=encoded)
    page = await browser.get(url)
    await asyncio.sleep(3)

    try:
        body_text = await page.get_content()
        match = re.search(r'of\s+(?:over\s+)?([\d,]+)\s+results?', body_text)
        if match:
            return int(match.group(1).replace(",", ""))
        match = re.search(r'([\d,]+)\s+results?', body_text)
        if match:
            return int(match.group(1).replace(",", ""))
    except Exception:
        pass

    try:
        items = await page.query_selector_all("[data-component-type='s-search-result']")
        return len(items)
    except Exception:
        return 0


# ── Top Listings Analysis ─────────────────────────────────────────────────────

async def analyze_top_listings(browser, keyword: str, max_items: int = 10) -> list[dict]:
    """Analyze the top listings for a keyword: title, price, rating, reviews."""
    encoded = urllib.parse.quote(keyword)
    url = MBA_SEARCH_URL.format(keyword=encoded)
    page = await browser.get(url)
    await asyncio.sleep(3)

    listings = []
    try:
        items = await page.query_selector_all("[data-component-type='s-search-result']")
        for item in items[:max_items]:
            try:
                title_el = await item.query_selector("h2 a span, .a-text-normal")
                title = (title_el.text or "").strip() if title_el else ""

                price_el = await item.query_selector(".a-price .a-offscreen, .a-price-whole")
                price = (price_el.text or "").strip() if price_el else ""

                asin = await item.get_attribute("data-asin") or ""

                rating_el = await item.query_selector(".a-icon-alt")
                rating = (rating_el.text or "").strip() if rating_el else ""

                review_el = await item.query_selector(".a-size-small .a-link-normal")
                reviews = (review_el.text or "").strip() if review_el else ""

                if title:
                    listings.append({
                        "title": title,
                        "price": price,
                        "asin": asin,
                        "rating": rating,
                        "review_count": reviews,
                    })
            except Exception:
                continue
    except Exception:
        pass

    return listings


# ── BSR Check (Individual Product) ────────────────────────────────────────────

async def get_bsr(browser, asin: str) -> dict:
    """Visit a product page and extract BSR data."""
    url = f"https://www.amazon.com/dp/{asin}"
    page = await browser.get(url)
    await asyncio.sleep(3)

    bsr_data = {"asin": asin, "bsr_rank": None, "bsr_category": ""}
    try:
        body_text = await page.get_content()
        match = re.search(r'#([\d,]+)\s+in\s+([^<\n(]+)', body_text)
        if match:
            bsr_data["bsr_rank"] = int(match.group(1).replace(",", ""))
            bsr_data["bsr_category"] = match.group(2).strip()
    except Exception:
        pass

    return bsr_data


# ── Opportunity Scoring ───────────────────────────────────────────────────────

def calculate_opportunity_score(
    competition: int,
    avg_bsr: int | None,
    avg_price: float,
    listing_count: int,
) -> dict:
    """
    Score a niche opportunity based on the knowledge base formula:
    High Demand (Low BSRs) + Low Supply (Low Result Count) + Low Quality = Goldmine

    Returns score dict with overall rating (0-100) and breakdown.
    """
    score = 0
    breakdown = {}

    # Competition score (lower = better, max 30 points)
    if competition < 500:
        comp_score = 30
    elif competition < 2000:
        comp_score = 25
    elif competition < 5000:
        comp_score = 15
    elif competition < 10000:
        comp_score = 8
    else:
        comp_score = 3
    breakdown["competition"] = comp_score
    score += comp_score

    # BSR score (lower BSR = higher demand, max 40 points)
    if avg_bsr is not None:
        if avg_bsr < 100000:
            bsr_score = 40
        elif avg_bsr < 300000:
            bsr_score = 30
        elif avg_bsr < 500000:
            bsr_score = 15
        elif avg_bsr < 1000000:
            bsr_score = 8
        else:
            bsr_score = 3
    else:
        bsr_score = 10  # Unknown — neutral
    breakdown["demand_bsr"] = bsr_score
    score += bsr_score

    # Price score (higher avg price = more margin, max 15 points)
    if avg_price >= 22:
        price_score = 15
    elif avg_price >= 18:
        price_score = 12
    elif avg_price >= 15:
        price_score = 8
    else:
        price_score = 4
    breakdown["price_margin"] = price_score
    score += price_score

    # Listing quality score (fewer high-quality listings = more opportunity, max 15 points)
    if listing_count < 3:
        quality_score = 15
    elif listing_count < 6:
        quality_score = 12
    elif listing_count < 10:
        quality_score = 8
    else:
        quality_score = 4
    breakdown["quality_gap"] = quality_score
    score += quality_score

    # Rating
    if score >= 75:
        rating = "GOLDMINE"
    elif score >= 55:
        rating = "HIGH_PRIORITY"
    elif score >= 40:
        rating = "MODERATE"
    elif score >= 25:
        rating = "LOW_PRIORITY"
    else:
        rating = "AVOID"

    return {
        "total_score": score,
        "max_score": 100,
        "rating": rating,
        "breakdown": breakdown,
    }


# ── Full Niche Analysis ───────────────────────────────────────────────────────

async def analyze_niche(browser, keyword: str) -> dict:
    """
    Run full competition analysis for a niche keyword.
    Returns comprehensive niche analysis dict.
    """
    print(f"    Analyzing niche: '{keyword}'...")

    # Competition count
    comp_count = await get_competition_count(browser, keyword)
    print(f"      Competition count: {comp_count}")

    # Top listings analysis
    top_listings = await analyze_top_listings(browser, keyword, max_items=10)
    print(f"      Top listings found: {len(top_listings)}")

    # Extract price data
    prices = []
    for listing in top_listings:
        price_str = listing.get("price", "").replace("$", "").replace(",", "")
        try:
            prices.append(float(price_str))
        except (ValueError, TypeError):
            pass

    avg_price = round(sum(prices) / len(prices), 2) if prices else 0
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0

    # BSR check for top 3 listings
    bsr_data = []
    for listing in top_listings[:3]:
        if listing.get("asin"):
            bsr = await get_bsr(browser, listing["asin"])
            bsr_data.append(bsr)
            await asyncio.sleep(1)

    bsr_ranks = [b["bsr_rank"] for b in bsr_data if b["bsr_rank"] is not None]
    avg_bsr = int(sum(bsr_ranks) / len(bsr_ranks)) if bsr_ranks else None

    # Score the niche opportunity
    score = calculate_opportunity_score(comp_count, avg_bsr, avg_price, len(top_listings))

    return {
        "keyword": keyword,
        "competition_count": comp_count,
        "top_listings": top_listings,
        "price_analysis": {
            "avg_price": avg_price,
            "min_price": min_price,
            "max_price": max_price,
            "price_count": len(prices),
        },
        "bsr_analysis": {
            "bsr_data": bsr_data,
            "avg_bsr": avg_bsr,
            "bsr_count": len(bsr_ranks),
        },
        "opportunity_score": score,
        "timestamp": datetime.now().isoformat(),
    }
