# Fantasy Baseball Research Platform

A Python toolkit for data-driven fantasy baseball — combining public MLB data sources, machine learning, and the Yahoo Fantasy Sports API to inform draft decisions and in-season roster management.

---

## What This Project Does

The platform has three layers:

1. **Data collection** — pulls player statistics, Statcast exit-velocity/spin metrics, and Steamer/ZiPS/ATC projection data from FanGraphs and the MLB via the `pybaseball` library.
2. **Valuation modeling** — ranks every qualified MLB player under Yahoo's three scoring formats (points, categories, rotisserie) using z-score normalization and a custom points engine.
3. **Live team management** — connects to your Yahoo Fantasy leagues via OAuth to view rosters, query the waiver wire, propose trades, and manage lineups programmatically.

---

## Where the Applied Analysis Lives

> **For reviewers:** the notebooks below are the main deliverables. Start with `draft_research.ipynb` for the core ranking methodology, then `breakouts.ipynb` for the machine learning work.

### [`notebooks/draft_research.ipynb`](notebooks/draft_research.ipynb) — Draft Rankings & Value Analysis
The primary research notebook. Core work includes:

- **Player ranking** across all three Yahoo scoring formats (points, categories, roto) using z-score methodology with playing-time-weighted rate stats
- **Multi-system projections** — Steamer, ZiPS, ATC, The BAT, and Depth Charts projections fetched from the FanGraphs API and mapped to fantasy scoring
- **Draft value identification** — compares a player's projected fantasy rank against their Yahoo ADP (average draft position) to surface undervalued picks; e.g. a player projected top-30 but drafted in the 8th round shows up as high-value
- **Power/speed targets** — screens projection data for 20/20 and 30/30 club candidates, high-average hitters

### [`notebooks/breakouts.ipynb`](notebooks/breakouts.ipynb) — Breakout Player Prediction (ML)
Uses historical FanGraphs + Statcast data (2015–2024) to identify players likely to break out. Key methodology:

- **Breakout definition:** ≥2.0 WAR jump year-over-year, sustained the following season — no data leakage (all features come from the pre-breakout season)
- **K-Means clustering** on historical breakout players to identify archetypes (who breaks out and why — e.g. exit-velocity improvers vs. walk-rate improvers)
- **Decision Tree classifier** trained on labeled breakout/non-breakout players to predict breakout probability from pre-season stats
- **PCA visualization** of cluster structure; cross-validated model performance via `StratifiedKFold`
- Outputs ranked 2025 breakout candidates with archetype assignments

### [`notebooks/yahoo_fantasy_baseball.ipynb`](notebooks/yahoo_fantasy_baseball.ipynb) — Multi-League Team Management
In-season management dashboard connecting to all 10 active Yahoo leagues simultaneously:

- **All-league roster view** — color-coded HTML grid showing every roster slot across all leagues, highlighting shared players
- **Top available** — fetches the highest-% ownership unrostered players per league, filtered by batter/pitcher type
- **Upgrade candidates** — compares available waivers against current roster using both current-season stats and rest-of-season projections
- Waiver wire queries, free agent search, trade proposals, and lineup moves executed via API

### [`notebooks/team_management.ipynb`](notebooks/team_management.ipynb) — Single-League Operations
Focused notebook for managing one specific league. Covers:
- Current roster, bench, and IL status
- Active matchup and opponent roster
- Waiver wire filtered by position
- Add/drop/trade/lineup operations with live API execution

### [`notebooks/_retrievers.ipynb`](notebooks/_retrievers.ipynb) — Data Validation
Development notebook for exploring raw API responses and validating data pipelines. Not intended for analysis — used during development.

---

## File Structure

```
baseball/
│
├── baseball.py             # Core data layer — FanGraphs + Statcast pipeline
│                           #   Classes: Batters, Pitchers, Teams, League, Fantasy
│                           #   Fantasy.rank() produces the z-score / points rankings
│
├── yahoo.py                # Yahoo Fantasy Sports API client
│                           #   Class: Yahoo — roster, waivers, add/drop/trade/lineup
│                           #   Helpers: init_auth(), top_available_all_leagues(),
│                           #            upgrade_candidates(), all_rosters()
│
├── woba_weights.py         # wOBA linear weights by season (for custom run estimators)
├── advisor.py              # Experimental trade advisor utilities
│
├── browser/
│   └── yahoo_oauth.json    # OAuth tokens (auto-refreshed; do not delete)
│
└── notebooks/
    ├── draft_research.ipynb         # ← START HERE: rankings + draft value
    ├── breakouts.ipynb              # ← ML: breakout prediction (K-Means + Decision Tree)
    ├── yahoo_fantasy_baseball.ipynb # ← Multi-league in-season dashboard
    ├── team_management.ipynb        # ← Single-league operations
    └── _retrievers.ipynb            # Data exploration / dev only
```

---

## Key Technical Highlights

| Area | Implementation |
|---|---|
| Player valuation | Z-score normalization with playing-time-weighted rate stats (AVG, ERA, WHIP) across 1,000+ players |
| Projection integration | REST API calls to FanGraphs JSON endpoints for 8 projection systems (Steamer, ZiPS, ATC, The BAT, etc.) |
| ML breakout model | Scikit-learn: K-Means + PCA for archetype discovery; Decision Tree classifier with StratifiedKFold CV |
| Yahoo API | OAuth 2.0 (PKCE flow) with auto-refresh; paginated waiver/roster endpoints; lineup write operations |
| Data sources | FanGraphs (batting/pitching stats + projections), Baseball Savant / Statcast (exit velocity, barrel rate, spin), Yahoo Fantasy Sports API |

---

## Setup

**Dependencies:** `pybaseball`, `pandas`, `numpy`, `scikit-learn`, `matplotlib`, `yahoo-oauth`, `requests`

**Conda environment:** `venv` (registered as a Jupyter kernel)

**Yahoo credentials:** Run `init_auth()` in `yahoo_fantasy_baseball.ipynb` Section 1 on first use. Tokens are saved to `browser/yahoo_oauth.json` and auto-refreshed on subsequent runs — no repeated browser login needed.
