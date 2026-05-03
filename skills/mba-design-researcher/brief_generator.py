"""
brief_generator.py — Phase 5: Design Brief & Listing Copy Generation
Uses AI to generate design briefs and pre-written listing copy
for validated niche opportunities.
"""

import json
import os
from openai import OpenAI

from compliance import scan_text

client = OpenAI()

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_kb(filename: str) -> str:
    path = os.path.join(_SKILL_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


A10_KB = _load_kb("A10AlgorithmParadigm.txt")
LEGAL_KB = _load_kb("LegalCompliance,Copyright&ContentPolicies.txt")
MARKET_KB = _load_kb("AdvancedMarketResearch&NicheValidation.txt")

BRIEF_SYSTEM_PROMPT = f"""You are an expert Merch by Amazon design strategist and listing copywriter.

You follow these knowledge bases as your single source of truth:

=== A10 ALGORITHM RULES ===
{A10_KB}

=== LEGAL COMPLIANCE ===
{LEGAL_KB}

=== MARKET RESEARCH METHODOLOGY ===
{MARKET_KB}

Your job is to generate:
1. A design brief (what the design should look like, text/quote, visual style, colors)
2. Pre-written listing copy (title, bullets, description, backend keywords)
3. Cross-niche intersection ideas (combining the niche with other audiences)

CRITICAL RULES:
- Title max 60 chars. Formula: [Primary Keyword] + [Audience] + [Occasion]
- Do NOT include "T-Shirt", "Tee", "Shirt", "Apparel" in title
- Bullet 1: Who & Why formula
- Bullet 2: What & Where + Cross-Sell formula
- Description: 3-4 natural sentences, LSI keywords, Google SEO optimized
- NEVER use banned/restricted words
- No keyword stuffing, no ALL CAPS, no emojis
- Backend keywords: max 250 bytes, no commas, no repeated words from title/bullets
"""


def generate_design_brief(
    niche: str,
    keyword: str,
    competition_count: int,
    avg_price: float,
    avg_bsr: int | None,
    top_listing_titles: list[str],
    sustainability: str,
) -> dict:
    """
    Generate a complete design brief and pre-written listing copy.
    Returns dict with design_brief, listing_copy, cross_niche_ideas.
    """
    top_titles_str = "\n".join(f"  - {t}" for t in top_listing_titles[:5])

    user_prompt = f"""Generate a design brief and listing copy for this validated MBA niche:

Niche: {niche}
Primary Keyword: {keyword}
Competition Count: {competition_count} designs
Average Price: ${avg_price}
Average BSR: {avg_bsr if avg_bsr else 'Unknown'}
Sustainability: {sustainability}

Top competing titles:
{top_titles_str}

Generate a COMPLETE design brief that differentiates from the competition above.

Output JSON only:
{{
  "design_brief": {{
    "suggested_text_quote": "The main text/quote for the design",
    "visual_style": "Describe the visual style (e.g., vintage distressed, minimalist, retro, hand-drawn)",
    "color_recommendations": ["color1", "color2", "color3"],
    "target_shirt_colors": ["black", "navy", "dark heather"],
    "design_elements": "Describe graphic elements to include",
    "differentiation_strategy": "How this design stands out from competition"
  }},
  "listing_copy": {{
    "title": "Max 60 chars, following the formula",
    "brand_name": "Hybrid brand name following formula",
    "bullet1": "Who & Why formula",
    "bullet2": "What & Where + Cross-Sell formula",
    "description": "3-4 sentences, LSI keywords, Google SEO",
    "backend_keywords": "Space-separated, no commas, no repeats from title/bullets"
  }},
  "keyword_research": {{
    "root_keyword": "Main keyword",
    "long_tail_keywords": ["3+ word phrases with buyer intent"],
    "lsi_keywords": ["thematically related terms"],
    "audience_keywords": ["who the product is for"],
    "occasion_keywords": ["when to buy/gift"]
  }},
  "cross_niche_ideas": [
    {{
      "combination": "Niche + Audience intersection",
      "example_text": "Suggested design text for this combo",
      "rationale": "Why this intersection works"
    }}
  ],
  "persona_targeting": {{
    "primary_persona": "Who is the ideal buyer",
    "secondary_persona": "Secondary buyer profile",
    "complementary_products": ["Products this persona also buys"]
  }}
}}"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)

    # Run compliance check on all generated text
    listing = result.get("listing_copy", {})
    for field in ["title", "bullet1", "bullet2", "description"]:
        text = listing.get(field, "")
        issues = scan_text(text)
        if issues:
            print(f"    [Compliance] Flagged in {field}: {issues}")
            # Regenerate the specific field
            listing[field] = _fix_compliance(text, issues)

    result["listing_copy"] = listing
    return result


def _fix_compliance(text: str, issues: list[str]) -> str:
    """Use AI to rewrite text removing compliance issues."""
    prompt = f"""Rewrite this Merch by Amazon listing text, removing these banned words: {issues}

Original text: {text}

Rules:
- Keep the same meaning and intent
- Do NOT use any of these banned words or their variations
- Keep it natural and readable
- Output ONLY the rewritten text, nothing else"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    return response.choices[0].message.content.strip().strip('"')


def generate_cross_niche_ideas(niche: str, count: int = 5) -> list[dict]:
    """
    Generate cross-niche intersection ideas following the knowledge base
    Intersection Strategy: Set A (Hobby) + Set B (Identity/Animal).
    """
    prompt = f"""Generate {count} cross-niche intersection ideas for Merch by Amazon.

Base niche: {niche}

Use the Intersection Strategy: combine the base niche with different audiences,
identities, animals, or hobbies to create hyper-targeted sub-niches.

Example: "Fishing" + "Cat Dad" = "Cat Dad Fishing Shirt"

Output JSON only:
{{
  "ideas": [
    {{
      "combination": "Niche + Audience",
      "sub_niche": "The resulting sub-niche name",
      "example_design_text": "Suggested text for the design",
      "target_audience": "Who would buy this",
      "rationale": "Why this works"
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
    return result.get("ideas", [])


if __name__ == "__main__":
    # Quick test
    ideas = generate_cross_niche_ideas("Fishing")
    print(json.dumps(ideas, indent=2))
