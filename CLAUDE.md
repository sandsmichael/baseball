# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Style

- Ask for clarification when uncertain — do not assume.
- Plan before writing code. Think through the task, form a plan, then act.
- Write high quality, concise, readable code. No need to account for every edge case.
- Always verify after completing a task — confirm the action meets the objective.
- After every piece of user feedback, update `lessons.md` with the pattern to prevent repeat mistakes.
- Use subagents liberally to keep the context window clean.
- Always test and verify your work. Run notebook cells after you make changes to ensure there are no errors. 

## Project Overview

Fantasy baseball data pipeline and Yahoo Fantasy Baseball API client.

- `baseball.py` — OOP data layer: fetches/merges FanGraphs + Statcast stats and computes fantasy scores
- `yahoo.py` — Yahoo Fantasy Baseball API wrapper: roster, transactions, lineup, draft analysis
- `yahoo_fantasy_baseball.ipynb` — Interactive notebook for Yahoo league management (OAuth automation via Playwright)

**Season:** Change `SEASON = 2025` in constructor args to target a different year.

## Environment

```bash
conda run -n venv python   # pybaseball, pandas, numpy, requests, yahoo_oauth
```

Caching enabled via `pybaseball.cache.enable()` — repeat runs use local cache.

## Data Sources and Rate Limits

| Source | Notes |
|---|---|
| **FanGraphs** | Scraped via pybaseball leaderboards + projections JSON API |
| **Baseball Savant (Statcast)** | 25,000-row query limit; prefer aggregate endpoints |

## baseball.py Architecture

### Classes

**`Batters(season, proj_system='steamer')`**
- Merges FanGraphs batting leaderboard + Statcast exit-velocity/barrels
- `.fetch()` → returns self; `.all` / `.qualified(min_pa=100)` / `.top(n=200)` / `.find(name)`
- `.projections` — lazy-loaded FanGraphs projections filtered to player pool
- Join key: `IDfg` (int64, cast to str) ↔ projections `playerid` (str)

**`Pitchers(season, proj_system='steamer')`**
- Merges FanGraphs pitching leaderboard + Statcast pitch-arsenal spin rates
- Same interface as Batters; role derived: SP if GS/G ≥ 0.5 else RP

**`Teams(season)`**
- FanGraphs team-level batting + pitching; `.batting` / `.pitching` DataFrames

**`League(season, proj_system='steamer')`**
- Composes Batters + Pitchers + Teams
- `.fetch()` / `.all_players` / `.projections` / `.top(batters=200, pitchers=100)` / `.export_csv(path)`

**`Fantasy(season, scoring_type, league=None, use_projections=False)`**
- `scoring_type`: `'categories'` / `'roto'` (z-score 5x5) or `'points'` (weighted per-stat)
- `.fetch()` → `.rank(min_pa=100, min_ip=20)` returns DataFrame sorted by `fantasy_score`
- Rate stats (AVG/ERA/WHIP) weighted by AB/IP in categories/roto

### Constants
- `PROJECTION_SYSTEMS`: 8 FanGraphs systems (steamer, steamerr, zips, zipr, atc, thebat, thebatx, fangraphs)
  - `fangraphs` (Depth Charts) and `zipr` are preseason-only — return 500 for completed seasons
- `YAHOO_SCORING`: Points weights dict for batting and pitching

## yahoo.py Architecture

**`Yahoo(league_id, season=None, creds_file='yahoo_oauth.json')`**

Requires OAuth2 app at developer.yahoo.com; put credentials in `yahoo_oauth.json`.

```python
y = Yahoo(league_id='12345').fetch()
```

### Read
- `.roster` — current team roster DataFrame (sorted by slot)
- `.standings` — league standings DataFrame
- `.matchup` — current week matchup dict
- `.free_agents(position, count)` / `.waivers()` / `.search(name)` / `.top_available(n, position)`

### Transactions
- `.add(player, drop=None, faab=None)` / `.drop(player)` / `.trade(give, receive, team)`

### Lineup
- `.move(player, position, for_date)` / `.start()` / `.bench()` / `.il()` / `.swap(p1, p2)`

### Draft / ADP
- `.adp(n=300)` — top n players by ADP with `percent_drafted` + `expert_rank`
- `.draft_value(rankings_df, n=300)` — value = (ADP - expert_rank) / position

### Gotchas
- Yahoo double-array: `team[0]` = properties, `team[1]` = sub-resources, `team[2]` = standings
- Game key changes each season — resolved dynamically via `/games;game_codes=mlb;seasons=YYYY`
- Ohtani appears twice (batter + pitcher); strip `\s*\((batter|pitcher)\)` suffix for name joins
- Roster PUT XML: use `<position>` (not `<selected_position>`), `<roster>` as root

## Notebook

**`yahoo_fantasy_baseball.ipynb`** — Yahoo league management via interactive notebook
- Section 2: Playwright OAuth automation (uses threading + asyncio to avoid Jupyter event loop conflict)
- 2FA detection: `'challenge-selector' in url` (NOT `'challenge' in url`)
- Saves browser state to `yahoo_browser_state.json`; subsequent runs use refresh token (no browser needed)

## Key Output

`top_300_fantasy_{SEASON}.csv` — 200 batters (min 100 PA) + 100 pitchers (min 20 IP), FanGraphs + Statcast columns.

```python
League(2025).fetch().export_csv('top_300_fantasy_2025.csv')
```

## Verification

```python
league = League(2025).fetch()
assert len(league.batters.top()) == 200
assert len(league.pitchers.top()) == 100
# Spot-check: Ohtani's MLBAM ID 660271
```
