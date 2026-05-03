# MBA Design Researcher

Automated niche discovery and design brief generation for Merch by Amazon. Finds high-profit, low-competition opportunities using a 6-phase research pipeline.

## What It Does

1. **Discovers trends** from Google Trends, Amazon Best Sellers, Amazon Autocomplete, Pinterest, and Reddit
2. **Drills into niches** using AI to find the most promising sub-niches and cross-niche intersections
3. **Validates demand** by checking competition count, BSR, and price data on Amazon
4. **Scores opportunities** on a 0-100 scale (GOLDMINE / HIGH_PRIORITY / MODERATE / LOW_PRIORITY / AVOID)
5. **Checks compliance** against 521 restricted words, IP rules, and pesticide triggers
6. **Generates design briefs** with suggested text, visual style, colors, and pre-written listing copy

All browsing is done via **nodriver** (undetected browser automation) to avoid bot detection.

## Quick Start

```bash
cd skills/mba-design-researcher
pip install -r requirements.txt
export OPENAI_API_KEY=your_key
python researcher.py
```

The script will:
1. Ask for seed keywords (or use defaults)
2. Open a browser and scrape trend data
3. Use AI to identify candidate niches
4. Analyze competition on Amazon
5. Validate compliance
6. Generate design briefs
7. Save everything to `output/`

## Output

After running, check the `output/` directory:

- **RESEARCH_REPORT.md** — Human-readable ranked report of all opportunities
- **01_trend_data.json** — Raw trend signals
- **02_candidate_niches.json** — AI-identified niches
- **03_competition_analysis.json** — Competition data per niche
- **04_validated_niches.json** — Compliance-approved niches
- **05_design_briefs.json** — Design briefs with listing copy
- **06_full_results.json** — Everything combined

## Opportunity Scoring

Each niche gets a score out of 100 based on:

| Factor | Max Points | What It Measures |
|--------|-----------|------------------|
| Competition | 30 | Fewer competing designs = higher score |
| Demand (BSR) | 40 | Lower BSR = more sales = higher score |
| Price Margin | 15 | Higher avg price = more profit per sale |
| Quality Gap | 15 | Fewer quality listings = more room for you |

**Ratings:**
- 75+ = GOLDMINE
- 55-74 = HIGH_PRIORITY
- 40-54 = MODERATE
- 25-39 = LOW_PRIORITY
- Below 25 = AVOID

## Configuration

Edit the top of `researcher.py` to customize:

```python
DEFAULT_SEEDS = ["funny t-shirt", "nurse humor", ...]  # Starting keywords
MAX_NICHES_TO_ANALYZE = 30      # How many niches to fully analyze
MAX_BRIEFS_TO_GENERATE = 20     # How many design briefs to produce
CHECK_TESS_TRADEMARKS = False   # Set True for USPTO checks (slower)
```

## Files

| File | Description |
|------|-------------|
| `researcher.py` | Main script — run this |
| `trend_discovery.py` | Phase 1: Trend scraping from multiple sources |
| `competition_analyzer.py` | Phase 3: Competition count, BSR, price analysis |
| `niche_validator.py` | Phase 4: IP check, compliance, red flags |
| `brief_generator.py` | Phase 5: AI design brief + listing copy generation |
| `compliance.py` | Restricted words scanner |
| `requirements.txt` | Python dependencies |
| `SKILL.md` | Skill definition for Manus agents |

## Knowledge Base

All rules come from these files (included in the repo):
- A10 Algorithm Paradigm (keyword strategy, listing formulas)
- Advanced Market Research & Niche Validation (7-phase methodology)
- Amazon Advertising 2026 (persona-based targeting)
- Legal Compliance (banned words, IP, pesticide triggers)
- RestrictedWords.txt (521 restricted terms)
