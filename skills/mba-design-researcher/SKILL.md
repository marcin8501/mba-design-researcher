# Skill: MBA Design Researcher

## Purpose
Automated niche discovery, trend analysis, competition validation, and design brief generation for Merch by Amazon. Finds high-profit, low-competition opportunities and produces ready-to-use design briefs with pre-written listing copy.

## Knowledge Base (Single Source of Truth)
- `A10AlgorithmParadigm.txt` — A10/A11 algorithm rules, keyword strategy, listing formulas
- `AdvancedMarketResearch&NicheValidation.txt` — 7-phase niche research methodology
- `Amazon_Advertising_2026_–_The_Shift_to_Persona_Based_Matching.txt` — Persona-based targeting for Rufus/Cosmo
- `LegalCompliance,Copyright&ContentPolicies.txt` — Banned words, IP rules, pesticide triggers
- `RestrictedWords.txt` — Full list of 521 restricted/banned words

## The 6-Phase Research Pipeline

### Phase 1: Trend Discovery
Scrapes multiple sources via nodriver (undetected browser):
- Google Trends — rising search queries
- Amazon Best Sellers & Movers and Shakers — trending novelty t-shirts
- Amazon Autocomplete — what people are actually searching for (with alphabet expansion)
- Pinterest Trends — emerging visual/aesthetic trends
- Reddit (r/MerchByAmazon) — early viral signals

### Phase 2: Niche Drilling
AI analyzes all trend signals and extracts the most promising candidate niches. Applies:
- Cross-Niche Intersection Strategy (e.g., "Fishing" + "Cat Dad")
- Audience segmentation (professions, hobbies, identities)
- Evergreen vs Seasonal vs Fad classification

### Phase 3: Competition & Demand Validation
For each candidate niche:
- Competition count via MBA-specific Amazon search URL
- Top 10 listings analysis (titles, prices, ratings)
- BSR extraction for top 3 products
- Opportunity scoring (0-100): Competition + Demand + Price Margin + Quality Gap

### Phase 4: IP & Compliance Pre-Check
- Scans all keywords against RestrictedWords.txt (521 words)
- Red flag detection (pesticide triggers, IP, misleading effects)
- Optional USPTO TESS trademark search (Class 025)
- Auto-rejects any niche with compliance issues

### Phase 5: Design Brief Generation
For each validated niche, AI generates:
- Design brief (text/quote, visual style, colors, shirt colors, graphic elements, differentiation)
- Pre-written listing copy (title, brand, bullets, description, backend keywords)
- Keyword research (root, long-tail, LSI, audience, occasion)
- Cross-niche intersection ideas
- Persona targeting (primary/secondary buyer, complementary products)

### Phase 6: Output
- Ranked markdown report of top 20 opportunities
- Full JSON data files for each phase
- All saved to `output/` directory

## Activation Prompt
```
You are a Merch by Amazon design research agent. Your goal is to find high-profit, low-competition niche opportunities and generate ready-to-use design briefs.

Browser: Use nodriver (pip install nodriver) for all web browsing — it bypasses bot detection.

Run the full 6-phase research pipeline:
1. Trend Discovery — scrape Google Trends, Amazon Best Sellers, Amazon Autocomplete, Pinterest Trends, Reddit
2. Niche Drilling — use AI to extract candidate niches from trend signals, apply cross-niche intersection strategy
3. Competition Validation — check competition count, BSR, prices, and score each niche (0-100)
4. IP & Compliance Check — scan against restricted words, red flags, optionally check USPTO TESS
5. Design Brief Generation — generate design briefs + pre-written listing copy for validated niches
6. Output — produce a ranked report of top opportunities with all data

Follow the knowledge base files as the single source of truth for all rules.
```

## How to Run
```bash
cd skills/mba-design-researcher
pip install -r requirements.txt
export OPENAI_API_KEY=your_key
python researcher.py
```

## Output Files
| File | Description |
|------|-------------|
| `output/01_trend_data.json` | Raw trend signals from all sources |
| `output/02_candidate_niches.json` | AI-extracted candidate niches |
| `output/03_competition_analysis.json` | Full competition analysis per niche |
| `output/04_validated_niches.json` | Niches that passed compliance |
| `output/05_design_briefs.json` | Design briefs + listing copy |
| `output/06_full_results.json` | Complete results |
| `output/RESEARCH_REPORT.md` | Human-readable ranked report |
