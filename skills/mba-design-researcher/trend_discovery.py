"""
trend_discovery.py — Phase 1: Trend Discovery
Scrapes Google Trends, Amazon Best Sellers / Movers & Shakers,
Pinterest Trends, and Reddit for emerging niche signals.
All browsing done via nodriver (undetected).
"""

import asyncio
import json
import re
from datetime import datetime


# ── Google Trends ─────────────────────────────────────────────────────────────

async def scrape_google_trends(browser, seed_keywords: list[str]) -> list[dict]:
    """
    Check Google Trends for rising queries related to seed keywords.
    Returns list of trending topics with relative interest scores.
    """
    trends = []
    for seed in seed_keywords:
        url = f"https://trends.google.com/trends/explore?q={seed}&geo=US&hl=en"
        page = await browser.get(url)
        await asyncio.sleep(4)

        try:
            # Look for related queries section
            related_els = await page.query_selector_all(
                ".fe-related-queries-wrapper .comparison-item"
            )
            for el in related_els[:10]:
                text = el.text or ""
                if text.strip():
                    trends.append({
                        "source": "google_trends",
                        "seed": seed,
                        "query": text.strip(),
                        "timestamp": datetime.now().isoformat(),
                    })
        except Exception:
            pass

        # Also try the trending searches page
        try:
            rising_els = await page.query_selector_all(
                ".fe-atoms-generic-content-container"
            )
            for el in rising_els[:10]:
                text = el.text or ""
                if text.strip() and len(text.strip()) < 100:
                    trends.append({
                        "source": "google_trends_rising",
                        "seed": seed,
                        "query": text.strip(),
                        "timestamp": datetime.now().isoformat(),
                    })
        except Exception:
            pass

    return trends


# ── Amazon Best Sellers & Movers and Shakers ──────────────────────────────────

AMAZON_NOVELTY_BESTSELLERS = "https://www.amazon.com/Best-Sellers-Novelty-T-Shirts/zgbs/fashion/9056921011"
AMAZON_NOVELTY_MOVERS = "https://www.amazon.com/gp/movers-and-shakers/fashion/9056921011"


async def scrape_amazon_bestsellers(browser) -> list[dict]:
    """Scrape Amazon Novelty T-Shirt Best Sellers for trending designs."""
    results = []

    for label, url in [("bestsellers", AMAZON_NOVELTY_BESTSELLERS),
                       ("movers_shakers", AMAZON_NOVELTY_MOVERS)]:
        page = await browser.get(url)
        await asyncio.sleep(3)

        try:
            items = await page.query_selector_all(
                ".zg-grid-general-faceout, .a-list-item .zg-item-immersion"
            )
            for item in items[:30]:
                try:
                    # Get product title
                    title_el = await item.query_selector(
                        ".p13n-sc-truncate, ._cDEzb_p13n-sc-css-line-clamp-1_1Fn1y, .a-link-normal span"
                    )
                    title = ""
                    if title_el:
                        title = (title_el.text or "").strip()

                    # Get price
                    price_el = await item.query_selector(".p13n-sc-price, ._cDEzb_p13n-sc-price_3mJ9Z")
                    price = ""
                    if price_el:
                        price = (price_el.text or "").strip()

                    # Get rank
                    rank_el = await item.query_selector(".zg-bdg-text, .zg-badge-text")
                    rank = ""
                    if rank_el:
                        rank = (rank_el.text or "").strip().replace("#", "")

                    if title:
                        results.append({
                            "source": f"amazon_{label}",
                            "title": title,
                            "price": price,
                            "rank": rank,
                            "timestamp": datetime.now().isoformat(),
                        })
                except Exception:
                    continue
        except Exception:
            pass

    return results


# ── Amazon Autocomplete (Niche Discovery) ─────────────────────────────────────

async def get_amazon_autocomplete(browser, seed: str) -> list[str]:
    """Get Amazon search autocomplete suggestions for a seed keyword."""
    encoded = seed.replace(" ", "+")
    url = (
        f"https://completion.amazon.com/api/2017/suggestions"
        f"?lop=en_US&site-variant=desktop&category=fashion-novelty"
        f"&prefix={encoded}&mid=ATVPDKIKX0DER"
    )
    page = await browser.get(url)
    await asyncio.sleep(1)

    try:
        body = await page.get_content()
        # Try to parse JSON from page body
        text = body
        if "<" in text:
            # Extract text content from HTML wrapper
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)
        data = json.loads(text)
        suggestions = [s.get("value", "") for s in data.get("suggestions", [])]
        return [s for s in suggestions if s][:10]
    except Exception:
        return []


async def discover_niches_via_autocomplete(browser, seed_keywords: list[str]) -> list[dict]:
    """
    Use Amazon Autocomplete to discover sub-niches from seed keywords.
    Expands each seed with alphabet suffixes (a-z) for broader discovery.
    """
    niches = []
    seen = set()

    for seed in seed_keywords:
        # Direct autocomplete
        suggestions = await get_amazon_autocomplete(browser, seed)
        for s in suggestions:
            if s.lower() not in seen:
                seen.add(s.lower())
                niches.append({
                    "source": "amazon_autocomplete",
                    "seed": seed,
                    "suggestion": s,
                })

        # Alphabet expansion (e.g., "fishing a", "fishing b", ...)
        for letter in "abcdefghijklmnopqrstuvwxyz":
            expanded = f"{seed} {letter}"
            suggestions = await get_amazon_autocomplete(browser, expanded)
            for s in suggestions:
                if s.lower() not in seen:
                    seen.add(s.lower())
                    niches.append({
                        "source": "amazon_autocomplete_expanded",
                        "seed": expanded,
                        "suggestion": s,
                    })
            await asyncio.sleep(0.3)  # Rate limit

    return niches


# ── Pinterest Trends ──────────────────────────────────────────────────────────

async def scrape_pinterest_trends(browser, seed_keywords: list[str]) -> list[dict]:
    """Scrape Pinterest Trends for emerging visual/aesthetic trends."""
    trends = []

    for seed in seed_keywords:
        url = f"https://trends.pinterest.com/search?q={seed}&geo=US"
        page = await browser.get(url)
        await asyncio.sleep(3)

        try:
            # Look for trending pins / related trends
            trend_els = await page.query_selector_all(
                ".trendItem, [data-test-id='trend-item'], .relatedTrend"
            )
            for el in trend_els[:10]:
                text = (el.text or "").strip()
                if text and len(text) < 100:
                    trends.append({
                        "source": "pinterest_trends",
                        "seed": seed,
                        "trend": text,
                        "timestamp": datetime.now().isoformat(),
                    })
        except Exception:
            pass

    return trends


# ── Reddit Scanning ───────────────────────────────────────────────────────────

REDDIT_SUBS = [
    "https://www.reddit.com/r/MerchByAmazon/hot/",
    "https://www.reddit.com/r/AmazonMerch/hot/",
    "https://www.reddit.com/r/MerchByAmazon/new/",
]


async def scrape_reddit_signals(browser) -> list[dict]:
    """Scrape MBA-related subreddits for trending topics and niche ideas."""
    signals = []

    for url in REDDIT_SUBS:
        page = await browser.get(url)
        await asyncio.sleep(3)

        try:
            posts = await page.query_selector_all(
                "shreddit-post, .Post, [data-testid='post-container']"
            )
            for post in posts[:15]:
                try:
                    title_el = await post.query_selector(
                        "a[slot='title'], h3, [data-testid='post-title']"
                    )
                    title = ""
                    if title_el:
                        title = (title_el.text or "").strip()

                    if title and len(title) > 10:
                        signals.append({
                            "source": "reddit",
                            "subreddit": url.split("/r/")[1].split("/")[0],
                            "title": title,
                            "timestamp": datetime.now().isoformat(),
                        })
                except Exception:
                    continue
        except Exception:
            pass

    return signals


# ── Master Discovery Function ─────────────────────────────────────────────────

async def run_trend_discovery(browser, seed_keywords: list[str]) -> dict:
    """
    Run all trend discovery sources and return aggregated results.
    """
    print("  [Phase 1] Running trend discovery...")

    print("    Checking Google Trends...")
    google_trends = await scrape_google_trends(browser, seed_keywords)
    print(f"    Found {len(google_trends)} Google Trends signals")

    print("    Scraping Amazon Best Sellers & Movers...")
    amazon_data = await scrape_amazon_bestsellers(browser)
    print(f"    Found {len(amazon_data)} Amazon trending products")

    print("    Discovering niches via Amazon Autocomplete...")
    autocomplete_niches = await discover_niches_via_autocomplete(browser, seed_keywords[:5])
    print(f"    Found {len(autocomplete_niches)} autocomplete niches")

    print("    Checking Pinterest Trends...")
    pinterest = await scrape_pinterest_trends(browser, seed_keywords[:3])
    print(f"    Found {len(pinterest)} Pinterest signals")

    print("    Scanning Reddit...")
    reddit = await scrape_reddit_signals(browser)
    print(f"    Found {len(reddit)} Reddit signals")

    return {
        "google_trends": google_trends,
        "amazon_bestsellers": amazon_data,
        "autocomplete_niches": autocomplete_niches,
        "pinterest_trends": pinterest,
        "reddit_signals": reddit,
        "total_signals": (
            len(google_trends) + len(amazon_data) + len(autocomplete_niches)
            + len(pinterest) + len(reddit)
        ),
    }
