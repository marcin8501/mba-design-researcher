# MBA Design Researcher

> Automated niche discovery and design brief generation for Merch by Amazon.

Find high-profit, low-competition opportunities using a 6-phase AI-powered research pipeline. Produces ranked design briefs with pre-written listing copy, ready to hand off to a designer.

## The Pipeline

1. **Trend Discovery** — Google Trends, Amazon Best Sellers, Autocomplete, Pinterest, Reddit
2. **Niche Drilling** — AI extracts candidate niches + cross-niche intersections
3. **Competition Validation** — competition count, BSR, price analysis, opportunity scoring (0-100)
4. **Compliance Check** — 521 restricted words, IP rules, pesticide triggers, USPTO TESS
5. **Design Brief Generation** — AI design briefs + pre-written Title, Bullets, Description
6. **Ranked Report** — top 20 opportunities sorted by score

All browsing via **nodriver** (undetected browser automation).

## Quick Start

```bash
cd skills/mba-design-researcher
pip install -r requirements.txt
export OPENAI_API_KEY=your_key
python researcher.py
```

**[→ Full documentation](skills/mba-design-researcher/README.md)**

## License
MIT
