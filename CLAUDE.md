# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Style

- Ask for clarification when uncertain — do not assume.
- Plan before writing code. Think through the task, form a plan, then act.
- Write high quality, concise, readable code. No need to account for every edge case.
- Always verify after completing a task — confirm the action meets the objective.
- After every piece of user feedback, update `lessons.md` with the pattern to prevent repeat mistakes.
- Use subagents liberally to keep the context window clean.

## Project Overview

This is a fantasy baseball data pipeline built as a Jupyter notebook (`baseball_data.ipynb`). It fetches, merges, and exports statistics for the top 300 fantasy-relevant MLB players.


## Running the Notebook

Launch: `jupyter notebook baseball_data.ipynb`

The notebook is divided into 7 sections — run them top to bottom for a full pipeline execution:
1. Setup & imports (enables pybaseball caching)
2. Single player lookup (demonstration/debugging)
3. Bulk season stats — FanGraphs leaderboards for all batters/pitchers
4. Statcast / Baseball Savant aggregates
5. Top 300 fantasy player merge and CSV export → `top_300_fantasy_{SEASON}.csv`
6. Team-level data
7. Verification checks (data quality assertions)

**Season configuration:** Change `SEASON = 2025` at the top of the notebook to target a different year.

## Data Sources and Rate Limits

| Source | Notes |
|---|---|
| **FanGraphs** | Scraped via pybaseball — no official API |
| **Baseball Savant (Statcast)** | 25,000-row query limit; prefer aggregate endpoints |
| **Baseball Reference** | Auto 6-second delay in pybaseball; avoid per-player loops |

Caching is enabled via `pybaseball.cache.enable()` — repeat runs use local cache.

## Key Output

`top_300_fantasy_{SEASON}.csv` — 200 batters (min 100 PA, ranked by wRC+) + 100 pitchers (min 20 IP, ranked by FIP), merged FanGraphs + Statcast columns.

## Verification

Run cells in Section 7 to validate data. Key assertions include `assert len(team_bat) == 30` and spot-checks for known players (e.g., Ohtani's MLBAM ID: 660271).
