"""
researcher.py — MBA Design Research Agent
Main orchestration script. Runs the full 6-phase research pipeline.

Usage:
    pip install -r requirements.txt
    export OPENAI_API_KEY=your_key
    python researcher.py

Phases:
1. Trend Discovery — Google Trends, Amazon Best Sellers, Autocomplete, Pinterest, Reddit
2. Niche Drilling — AI-powered sub-niche generation + cross-niche intersections
3. Competition & Demand Validation — competition count, BSR, price analysis, scoring
4. IP & Compliance Pre-Check — USPTO TESS, restricted words, red flags
5. Design Brief Generation — AI design briefs + pre-written listing copy
6. Output — ranked report of top opportunities
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import nodriver as uc

from trend_discovery import run_trend_discovery, discover_niches_via_autocomplete
from competition_analyzer import analyze_niche
from niche_validator import validate_niche, classify_niche_sustainability
from brief_generator import generate_design_brief, generate_cross_niche_ideas
from compliance import check_niche_keywords

# ── Config ────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Default seed keywords — can be overridden via config or CLI
DEFAULT_SEEDS = [
    "funny t-shirt",
    "nurse humor",
    "programmer jokes",
    "fishing gifts",
    "dog mom",
    "cat dad",
    "teacher appreciation",
    "gym motivation",
    "dad jokes",
    "retirement gifts",
]

MAX_NICHES_TO_ANALYZE = 30  # How many candidate niches to fully analyze
MAX_BRIEFS_TO_GENERATE = 20  # How many design briefs to produce
CHECK_TESS_TRADEMARKS = False  # Set True for thorough checks (slower)


# ── AI-Powered Niche Extraction ───────────────────────────────────────────────

def extract_candidate_niches_from_trends(trend_data: dict) -> list[str]:
    """
    Use AI to analyze raw trend data and extract the most promising
    niche keywords for MBA t-shirts.
    """
    from openai import OpenAI
    client = OpenAI()

    # Compile trend signals into a summary
    signals = []

    for item in trend_data.get("google_trends", [])[:20]:
        signals.append(f"Google Trends: {item.get('query', '')}")

    for item in trend_data.get("amazon_bestsellers", [])[:20]:
        signals.append(f"Amazon Trending: {item.get('title', '')}")

    for item in trend_data.get("autocomplete_niches", [])[:30]:
        signals.append(f"Amazon Autocomplete: {item.get('suggestion', '')}")

    for item in trend_data.get("pinterest_trends", [])[:10]:
        signals.append(f"Pinterest: {item.get('trend', '')}")

    for item in trend_data.get("reddit_signals", [])[:10]:
        signals.append(f"Reddit: {item.get('title', '')}")

    signals_text = "\n".join(signals)

    prompt = f"""You are an expert Merch by Amazon niche researcher.

Analyze these trend signals and extract the {MAX_NICHES_TO_ANALYZE} most promising
niche keywords for MBA t-shirt designs.

Focus on:
- Niches with clear buyer intent (people who would buy a t-shirt about this)
- Underserved niches (not oversaturated)
- Evergreen niches preferred over fads
- Cross-niche intersections (e.g., "Cat Dad Fishing")
- Specific audiences (professions, hobbies, identities)

Trend signals:
{signals_text}

Output JSON only:
{{
  "candidate_niches": [
    {{
      "keyword": "the niche keyword phrase",
      "rationale": "why this is promising",
      "estimated_demand": "HIGH/MEDIUM/LOW",
      "niche_type": "EVERGREEN/SEASONAL/FAD"
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
    return result.get("candidate_niches", [])


# ── Report Generation ─────────────────────────────────────────────────────────

def generate_report(opportunities: list[dict]) -> str:
    """Generate a human-readable markdown report of top opportunities."""
    lines = [
        f"# MBA Design Research Report",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total Opportunities Analyzed:** {len(opportunities)}",
        "",
        "---",
        "",
    ]

    # Sort by opportunity score
    sorted_opps = sorted(
        opportunities,
        key=lambda x: x.get("competition_data", {}).get("opportunity_score", {}).get("total_score", 0),
        reverse=True,
    )

    for i, opp in enumerate(sorted_opps, 1):
        kw = opp.get("keyword", "Unknown")
        score = opp.get("competition_data", {}).get("opportunity_score", {})
        comp = opp.get("competition_data", {})
        validation = opp.get("validation", {})
        brief = opp.get("design_brief", {})
        listing = brief.get("listing_copy", {})
        design = brief.get("design_brief", {})

        rating = score.get("rating", "N/A")
        total = score.get("total_score", 0)

        lines.append(f"## #{i}: {kw}")
        lines.append(f"**Score:** {total}/100 ({rating})")
        lines.append(f"**Sustainability:** {validation.get('sustainability', 'N/A')}")
        lines.append(f"**Competition:** {comp.get('competition_count', 'N/A')} designs")
        lines.append(f"**Avg Price:** ${comp.get('price_analysis', {}).get('avg_price', 'N/A')}")
        lines.append(f"**Avg BSR:** {comp.get('bsr_analysis', {}).get('avg_bsr', 'N/A')}")
        lines.append(f"**Compliance:** {validation.get('verdict', 'N/A')}")
        lines.append("")

        if design:
            lines.append("### Design Brief")
            lines.append(f"- **Suggested Text:** {design.get('suggested_text_quote', '')}")
            lines.append(f"- **Visual Style:** {design.get('visual_style', '')}")
            lines.append(f"- **Colors:** {', '.join(design.get('color_recommendations', []))}")
            lines.append(f"- **Shirt Colors:** {', '.join(design.get('target_shirt_colors', []))}")
            lines.append(f"- **Elements:** {design.get('design_elements', '')}")
            lines.append(f"- **Differentiation:** {design.get('differentiation_strategy', '')}")
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

        cross = brief.get("cross_niche_ideas", [])
        if cross:
            lines.append("### Cross-Niche Ideas")
            for idea in cross[:3]:
                lines.append(f"- **{idea.get('combination', '')}:** {idea.get('example_text', '')} — {idea.get('rationale', '')}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── Main Pipeline ─────────────────────────────────────────────────────────────

async def main():
    print("\n" + "=" * 60)
    print("MBA DESIGN RESEARCH AGENT")
    print(f"Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Ask for custom seed keywords or use defaults
    print(f"\nDefault seed keywords: {DEFAULT_SEEDS}")
    custom = input("Enter custom seed keywords (comma-separated) or press Enter for defaults: ").strip()
    if custom:
        seed_keywords = [s.strip() for s in custom.split(",") if s.strip()]
    else:
        seed_keywords = DEFAULT_SEEDS

    print(f"\nUsing {len(seed_keywords)} seed keywords: {seed_keywords}")

    # Start browser with nodriver
    browser = await uc.start(
        headless=False,
        browser_args=["--start-maximized"],
    )

    try:
        # ── PHASE 1: Trend Discovery ─────────────────────────────────────
        print("\n" + "=" * 60)
        print("PHASE 1: TREND DISCOVERY")
        print("=" * 60)

        trend_data = await run_trend_discovery(browser, seed_keywords)
        print(f"\nTotal trend signals collected: {trend_data['total_signals']}")

        # Save raw trend data
        with open(OUTPUT_DIR / "01_trend_data.json", "w") as f:
            json.dump(trend_data, f, indent=2)

        # ── PHASE 2: Niche Drilling ──────────────────────────────────────
        print("\n" + "=" * 60)
        print("PHASE 2: NICHE DRILLING (AI Analysis)")
        print("=" * 60)

        candidate_niches = extract_candidate_niches_from_trends(trend_data)
        print(f"AI identified {len(candidate_niches)} candidate niches")

        for cn in candidate_niches[:5]:
            print(f"  - {cn['keyword']} ({cn['estimated_demand']}, {cn['niche_type']})")

        with open(OUTPUT_DIR / "02_candidate_niches.json", "w") as f:
            json.dump(candidate_niches, f, indent=2)

        # ── PHASE 3: Competition & Demand Validation ─────────────────────
        print("\n" + "=" * 60)
        print("PHASE 3: COMPETITION & DEMAND VALIDATION")
        print("=" * 60)

        analyzed_niches = []
        for i, cn in enumerate(candidate_niches[:MAX_NICHES_TO_ANALYZE], 1):
            keyword = cn["keyword"]
            print(f"\n  [{i}/{min(len(candidate_niches), MAX_NICHES_TO_ANALYZE)}] {keyword}")

            analysis = await analyze_niche(browser, keyword)
            analysis["ai_rationale"] = cn.get("rationale", "")
            analysis["ai_demand"] = cn.get("estimated_demand", "")
            analysis["ai_type"] = cn.get("niche_type", "")
            analyzed_niches.append(analysis)

            score = analysis["opportunity_score"]
            print(f"      Score: {score['total_score']}/100 ({score['rating']})")

            await asyncio.sleep(1)

        # Sort by score
        analyzed_niches.sort(
            key=lambda x: x["opportunity_score"]["total_score"],
            reverse=True,
        )

        with open(OUTPUT_DIR / "03_competition_analysis.json", "w") as f:
            json.dump(analyzed_niches, f, indent=2)

        # ── PHASE 4: IP & Compliance Pre-Check ───────────────────────────
        print("\n" + "=" * 60)
        print("PHASE 4: IP & COMPLIANCE PRE-CHECK")
        print("=" * 60)

        validated_niches = []
        for i, niche in enumerate(analyzed_niches[:MAX_BRIEFS_TO_GENERATE + 5], 1):
            keyword = niche["keyword"]
            print(f"\n  [{i}] Validating: {keyword}")

            validation = await validate_niche(
                browser, keyword, check_tess=CHECK_TESS_TRADEMARKS
            )

            niche["validation"] = validation
            print(f"      Verdict: {validation['verdict']}")
            print(f"      Sustainability: {validation['sustainability']}")

            if validation["verdict"] == "APPROVED":
                validated_niches.append(niche)
            else:
                print(f"      REJECTED: {validation['rejection_reasons']}")

        print(f"\n  Approved: {len(validated_niches)} / {len(analyzed_niches[:MAX_BRIEFS_TO_GENERATE + 5])}")

        with open(OUTPUT_DIR / "04_validated_niches.json", "w") as f:
            json.dump(validated_niches, f, indent=2)

        # ── PHASE 5: Design Brief Generation ─────────────────────────────
        print("\n" + "=" * 60)
        print("PHASE 5: DESIGN BRIEF GENERATION")
        print("=" * 60)

        opportunities = []
        for i, niche in enumerate(validated_niches[:MAX_BRIEFS_TO_GENERATE], 1):
            keyword = niche["keyword"]
            print(f"\n  [{i}/{min(len(validated_niches), MAX_BRIEFS_TO_GENERATE)}] Generating brief: {keyword}")

            top_titles = [l.get("title", "") for l in niche.get("top_listings", [])[:5]]

            brief = generate_design_brief(
                niche=keyword,
                keyword=keyword,
                competition_count=niche.get("competition_count", 0),
                avg_price=niche.get("price_analysis", {}).get("avg_price", 0),
                avg_bsr=niche.get("bsr_analysis", {}).get("avg_bsr"),
                top_listing_titles=top_titles,
                sustainability=niche.get("validation", {}).get("sustainability", "UNKNOWN"),
            )

            opportunity = {
                "keyword": keyword,
                "competition_data": niche,
                "validation": niche.get("validation", {}),
                "design_brief": brief,
            }
            opportunities.append(opportunity)

            title = brief.get("listing_copy", {}).get("title", "")
            print(f"      Title: {title}")
            print(f"      Design: {brief.get('design_brief', {}).get('suggested_text_quote', '')}")

        with open(OUTPUT_DIR / "05_design_briefs.json", "w") as f:
            json.dump(opportunities, f, indent=2)

        # ── PHASE 6: Output Report ───────────────────────────────────────
        print("\n" + "=" * 60)
        print("PHASE 6: GENERATING FINAL REPORT")
        print("=" * 60)

        report = generate_report(opportunities)
        report_path = OUTPUT_DIR / "RESEARCH_REPORT.md"
        with open(report_path, "w") as f:
            f.write(report)

        # Also save full JSON
        with open(OUTPUT_DIR / "06_full_results.json", "w") as f:
            json.dump(opportunities, f, indent=2)

        # ── Summary ──────────────────────────────────────────────────────
        print(f"\n{'=' * 60}")
        print("SESSION COMPLETE")
        print(f"{'=' * 60}")
        print(f"Trend signals collected: {trend_data['total_signals']}")
        print(f"Candidate niches identified: {len(candidate_niches)}")
        print(f"Niches fully analyzed: {len(analyzed_niches)}")
        print(f"Niches validated (approved): {len(validated_niches)}")
        print(f"Design briefs generated: {len(opportunities)}")
        print(f"\nReport saved to: {report_path}")
        print(f"All data saved to: {OUTPUT_DIR}/")
        print()

        # Print top 5
        print("TOP 5 OPPORTUNITIES:")
        for i, opp in enumerate(opportunities[:5], 1):
            score = opp["competition_data"]["opportunity_score"]
            brief = opp.get("design_brief", {}).get("design_brief", {})
            print(f"  #{i}: {opp['keyword']}")
            print(f"      Score: {score['total_score']}/100 ({score['rating']})")
            print(f"      Design: {brief.get('suggested_text_quote', 'N/A')}")
            print()

    finally:
        print("Closing browser...")
        browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
