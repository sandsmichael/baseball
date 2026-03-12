"""
baseball.py — OOP data layer for the fantasy baseball pipeline.

Classes:
    Batters(season)   — FanGraphs batting leaderboard + Statcast exit-velocity/barrels
    Pitchers(season)  — FanGraphs pitching leaderboard + Statcast pitch-arsenal spin
    Teams(season)     — FanGraphs team batting + pitching
    League(season)    — Composes the three classes above
    Fantasy(season, scoring_type, league)  — Yahoo scoring ranks (categories/roto/points)

Usage:
    from baseball import League, Batters, Pitchers, Teams, Fantasy

    # Full pipeline
    league = League(2025).fetch()
    df = league.top()          # 300 rows: 200 batters + 100 pitchers

    # Standalone
    Batters(2025).fetch().top(10)

    # Fantasy ranking
    f = Fantasy(2025, 'points').fetch()
    f.rank().head(10)

    # Projections
    league.batters.projections.head(5)   # lazy-fetched Steamer batting projections
    league.projections.head(5)           # combined with player_type column
"""

import warnings
warnings.filterwarnings('ignore')

import requests
import numpy as np
import pandas as pd
import pybaseball
from pybaseball import (
    batting_stats,
    pitching_stats,
    team_batting,
    team_pitching,
    statcast_batter_exitvelo_barrels,
    statcast_pitcher_pitch_arsenal,
)

pybaseball.cache.enable()


# ── Constants ─────────────────────────────────────────────────────────────────

PROJECTION_SYSTEMS = [
    'steamer',   # Steamer full-season
    'steamerr',  # Steamer rest-of-season
    'zips',      # ZiPS full-season
    'zipr',      # ZiPS rest-of-season
    'atc',       # ATC
    'thebat',    # The BAT
    'thebatx',   # The BAT X
    'fangraphs', # Depth Charts (50/50 Steamer + ZiPS blend with playing time)
]

YAHOO_SCORING = {
    'categories': {
        'batting':  ['R', 'HR', 'RBI', 'SB', 'AVG'],
        'pitching': ['W', 'SV', 'SO', 'ERA', 'WHIP'],
    },
    'roto': {
        'batting':  ['R', 'HR', 'RBI', 'SB', 'AVG'],
        'pitching': ['W', 'SV', 'SO', 'ERA', 'WHIP'],
    },
    'points': {
        'batting':  {
            '1B': 2.6, '2B': 5.2, '3B': 7.8, 'HR': 10.4,
            'R': 1.9, 'RBI': 1.9, 'BB': 2.6, 'SB': 4.2, 'HBP': 2.6,
        },
        'pitching': {
            'W': 8.0, 'SV': 8.0, 'SO': 3.0, 'Outs': 1.0,
            'H': -1.3, 'BB': -1.3, 'HBP': -1.3, 'ER': -3.0,
        },
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_name_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'Name' column in 'First Last' format from Statcast data."""
    if 'last_name, first_name' in df.columns:
        df['Name'] = df['last_name, first_name'].apply(
            lambda x: ' '.join(reversed(x.split(', '))) if isinstance(x, str) and ',' in x else x
        )
    elif 'first_name' in df.columns and 'last_name' in df.columns:
        df['Name'] = df['first_name'].str.strip() + ' ' + df['last_name'].str.strip()
    elif 'player_name' in df.columns:
        df['Name'] = df['player_name'].apply(
            lambda x: ' '.join(reversed(x.split(', '))) if isinstance(x, str) and ',' in x else x
        )
    return df


def _safe_zscore(series: pd.Series) -> pd.Series:
    """Return z-scores; returns zeros if std is 0."""
    std = series.std()
    if std == 0 or pd.isna(std):
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def _ip_to_outs(ip: float) -> int:
    """Convert FanGraphs IP notation (e.g. 195.1 = 195⅓ innings) to total outs."""
    return int(ip) * 3 + round((ip * 10) % 10)


# ── Batters ───────────────────────────────────────────────────────────────────

class Batters:
    """FanGraphs batting leaderboard merged with Statcast exit-velocity/barrels."""

    def __init__(self, season: int, proj_system: str = 'steamer'):
        self.season = season
        self.proj_system = proj_system
        self._fetched = False
        self._merged = None
        self._proj = None
        self._proj_fetched = False

    @staticmethod
    def _fetch_position_map() -> pd.Series:
        """Fetch playerid → position string from FanGraphs steamer batting projections."""
        url = 'https://www.fangraphs.com/api/projections?stats=bat&type=steamer&pos=all&teamid=0&players=0'
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = pd.DataFrame(resp.json())[['playerid', 'minpos']]
            # Normalize playerid to clean int string ("15640.0" → "15640") for reliable join
            data['playerid'] = data['playerid'].astype(float).astype(int).astype(str)
            return data.set_index('playerid')['minpos']
        except Exception:
            return pd.Series(dtype=str)

    def _fetch(self):
        if self._fetched:
            return

        raw = batting_stats(self.season, qual=0)

        statcast = statcast_batter_exitvelo_barrels(self.season)
        statcast = _build_name_column(statcast)

        ev_cols = ['Name', 'avg_hit_speed', 'max_hit_speed', 'brl_pa', 'brl_percent', 'player_id']
        ev_cols_available = [c for c in ev_cols if c in statcast.columns]

        self._merged = raw.merge(statcast[ev_cols_available], on='Name', how='left')

        # Drop WAR positional adjustment column (float like -3.4); add real fielding position
        self._merged = self._merged.drop(columns=['Pos'], errors='ignore')
        pos_map = self._fetch_position_map()
        self._merged['Pos'] = self._merged['IDfg'].astype(int).astype(str).map(pos_map)

        self._fetched = True

    def _fetch_projections(self) -> pd.DataFrame:
        self._fetch()  # ensure _merged (and IDfg) is ready
        url = (
            f'https://www.fangraphs.com/api/projections'
            f'?stats=bat&type={self.proj_system}&pos=all&teamid=0&players=0'
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        raw = pd.DataFrame(resp.json())
        # Filter to players in our pool; IDfg (int) matches playerid (str)
        our_ids = set(self._merged['IDfg'].dropna().astype(str))
        return raw[raw['playerid'].isin(our_ids)].reset_index(drop=True)

    @property
    def projections(self) -> pd.DataFrame:
        """Lazily fetch and return FanGraphs batting projections for players in this pool."""
        if not self._proj_fetched:
            self._proj = self._fetch_projections()
            self._proj_fetched = True
        return self._proj

    def fetch(self) -> 'Batters':
        """Explicitly trigger data fetch. Returns self for chaining."""
        self._fetch()
        return self

    @property
    def all(self) -> pd.DataFrame:
        self._fetch()
        return self._merged

    def qualified(self, min_pa: int = 100) -> pd.DataFrame:
        """All players with at least min_pa plate appearances, sorted by wRC+ descending."""
        self._fetch()
        return (
            self._merged[self._merged['PA'] >= min_pa]
            .sort_values('wRC+', ascending=False)
            .reset_index(drop=True)
        )

    def top(self, n: int = 200) -> pd.DataFrame:
        """Top n qualified batters with 1-based rank index."""
        df = self.qualified().head(n).copy()
        df.index = range(1, len(df) + 1)
        df.index.name = 'rank'
        return df

    def find(self, name: str) -> pd.DataFrame:
        """Case-insensitive substring search on Name."""
        self._fetch()
        mask = self._merged['Name'].str.contains(name, case=False, na=False)
        return self._merged[mask]

    def __len__(self) -> int:
        self._fetch()
        return len(self._merged)


# ── Pitchers ──────────────────────────────────────────────────────────────────

class Pitchers:
    """FanGraphs pitching leaderboard merged with Statcast pitch-arsenal spin rates."""

    def __init__(self, season: int, proj_system: str = 'steamer'):
        self.season = season
        self.proj_system = proj_system
        self._fetched = False
        self._merged = None
        self._proj = None
        self._proj_fetched = False

    def _fetch(self):
        if self._fetched:
            return

        raw = pitching_stats(self.season, qual=0)

        spin = statcast_pitcher_pitch_arsenal(self.season, minP=100, arsenal_type='avg_spin')
        spin = _build_name_column(spin)

        _exclude = {'last_name, first_name', 'last_name', 'first_name', 'player_name'}
        spin_cols = [c for c in spin.columns if c not in _exclude]

        self._merged = raw.merge(spin[spin_cols], on='Name', how='left')

        # Derive pitcher role from GS/G ratio (>= 0.5 → SP, else RP)
        self._merged['Pos'] = np.where(
            self._merged['GS'] / self._merged['G'].clip(lower=1) >= 0.5, 'SP', 'RP'
        )

        self._fetched = True

    def _fetch_projections(self) -> pd.DataFrame:
        self._fetch()  # ensure _merged (and IDfg) is ready
        url = (
            f'https://www.fangraphs.com/api/projections'
            f'?stats=pit&type={self.proj_system}&pos=all&teamid=0&players=0'
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        raw = pd.DataFrame(resp.json())
        # Filter to players in our pool; IDfg (int) matches playerid (str)
        our_ids = set(self._merged['IDfg'].dropna().astype(str))
        return raw[raw['playerid'].isin(our_ids)].reset_index(drop=True)

    @property
    def projections(self) -> pd.DataFrame:
        """Lazily fetch and return FanGraphs pitching projections for players in this pool."""
        if not self._proj_fetched:
            self._proj = self._fetch_projections()
            self._proj_fetched = True
        return self._proj

    def fetch(self) -> 'Pitchers':
        """Explicitly trigger data fetch. Returns self for chaining."""
        self._fetch()
        return self

    @property
    def all(self) -> pd.DataFrame:
        self._fetch()
        return self._merged

    def qualified(self, min_ip: float = 20) -> pd.DataFrame:
        """All pitchers with at least min_ip innings pitched, sorted by FIP ascending."""
        self._fetch()
        return (
            self._merged[self._merged['IP'] >= min_ip]
            .sort_values('FIP', ascending=True)
            .reset_index(drop=True)
        )

    def top(self, n: int = 100) -> pd.DataFrame:
        """Top n qualified pitchers with 1-based rank index."""
        df = self.qualified().head(n).copy()
        df.index = range(1, len(df) + 1)
        df.index.name = 'rank'
        return df

    def find(self, name: str) -> pd.DataFrame:
        """Case-insensitive substring search on Name."""
        self._fetch()
        mask = self._merged['Name'].str.contains(name, case=False, na=False)
        return self._merged[mask]

    def __len__(self) -> int:
        self._fetch()
        return len(self._merged)


# ── Teams ─────────────────────────────────────────────────────────────────────

class Teams:
    """FanGraphs team-level batting and pitching leaderboards."""

    def __init__(self, season: int):
        self.season = season
        self._fetched = False
        self._batting = None
        self._pitching = None

    def _fetch(self):
        if self._fetched:
            return
        self._batting = team_batting(self.season)
        self._pitching = team_pitching(self.season)
        self._fetched = True

    def fetch(self) -> 'Teams':
        """Explicitly trigger data fetch. Returns self for chaining."""
        self._fetch()
        return self

    @property
    def batting(self) -> pd.DataFrame:
        self._fetch()
        return self._batting

    @property
    def pitching(self) -> pd.DataFrame:
        self._fetch()
        return self._pitching

    def find(self, team: str) -> dict:
        """Return batting and pitching rows for a team (case-insensitive substring match)."""
        self._fetch()
        bat = self._batting[self._batting['Team'].str.contains(team, case=False, na=False)]
        pit = self._pitching[self._pitching['Team'].str.contains(team, case=False, na=False)]
        return {'batting': bat, 'pitching': pit}

    def __len__(self) -> int:
        self._fetch()
        return len(self._batting)


# ── League ────────────────────────────────────────────────────────────────────

class League:
    """Composes Batters, Pitchers, and Teams. Provides cross-player views."""

    def __init__(self, season: int, proj_system: str = 'steamer'):
        self.season = season
        self.proj_system = proj_system
        self.batters = Batters(season, proj_system=proj_system)
        self.pitchers = Pitchers(season, proj_system=proj_system)
        self.teams = Teams(season)

    def fetch(self) -> 'League':
        """Trigger fetch on all sub-objects. Returns self for chaining."""
        self.batters.fetch()
        self.pitchers.fetch()
        self.teams.fetch()
        return self

    @property
    def projections(self) -> pd.DataFrame:
        """Combined batting + pitching projections with a player_type column."""
        bat = self.batters.projections.copy()
        bat['player_type'] = 'batter'
        pit = self.pitchers.projections.copy()
        pit['player_type'] = 'pitcher'
        return pd.concat([bat, pit], ignore_index=True)

    @property
    def all_players(self) -> pd.DataFrame:
        """All batters and pitchers concatenated with a player_type column."""
        bat = self.batters.all.copy()
        bat['player_type'] = 'batter'
        pit = self.pitchers.all.copy()
        pit['player_type'] = 'pitcher'
        return pd.concat([bat, pit], ignore_index=True)

    def top(self, batters: int = 200, pitchers: int = 100) -> pd.DataFrame:
        """Top N batters + top M pitchers combined with a player_type column."""
        bat = self.batters.top(batters).copy()
        bat['player_type'] = 'batter'
        pit = self.pitchers.top(pitchers).copy()
        pit['player_type'] = 'pitcher'
        return pd.concat([bat, pit], ignore_index=True)

    def find(self, name: str) -> pd.DataFrame:
        """Search batters and pitchers by name (case-insensitive substring)."""
        bat = self.batters.find(name).copy()
        bat['player_type'] = 'batter'
        pit = self.pitchers.find(name).copy()
        pit['player_type'] = 'pitcher'
        return pd.concat([bat, pit], ignore_index=True)

    def export_csv(self, path: str = None) -> str:
        """Export top(200, 100) to CSV. Returns the file path."""
        if path is None:
            path = f'top_300_fantasy_{self.season}.csv'
        self.top().to_csv(path, index=True)
        return path


# ── Fantasy ───────────────────────────────────────────────────────────────────

class Fantasy:
    """
    Fantasy baseball ranking engine using Yahoo standard public league scoring.

    Supports three scoring types:
        'categories' — standard 5x5 head-to-head categories
        'roto'       — standard 5x5 rotisserie (same stat lists as categories)
        'points'     — points-based league with per-stat point values

    For categories/roto, player value is expressed as a sum of z-scores across
    all relevant stats (rate stats are weighted by playing time first).
    For points, raw point totals are computed per stat and summed.

    Usage:
        f = Fantasy(2025, 'points').fetch()
        df = f.rank()          # DataFrame with fantasy_score + per-stat breakdown

        # Reuse an existing fetched League
        league = League(2025).fetch()
        f = Fantasy(2025, 'roto', league=league)
        df = f.rank()

        # Score using projections instead of historical data
        league_proj = League(2025, proj_system='atc')
        f = Fantasy(2025, 'points', league=league_proj, use_projections=True)
        df = f.rank()
    """

    SCORING = YAHOO_SCORING

    def __init__(self, season: int, scoring_type: str, league: 'League' = None,
                 use_projections: bool = False):
        valid = ('categories', 'roto', 'points')
        if scoring_type not in valid:
            raise ValueError(f"scoring_type must be one of {valid}, got {scoring_type!r}")

        self.season = season
        self._scoring_type = scoring_type
        self._use_projections = use_projections
        self.league = league if league is not None else League(season)

    @property
    def scoring(self) -> dict:
        """Active scoring configuration for the chosen scoring_type."""
        return self.SCORING[self._scoring_type]

    def fetch(self) -> 'Fantasy':
        """Trigger league data fetch. Returns self for chaining."""
        self.league.fetch()
        return self

    def _get_bat_df(self, min_pa: int) -> pd.DataFrame:
        """Return the batting DataFrame to score — projections or historical."""
        if self._use_projections:
            df = self.league.batters.projections.copy()
            if 'Name' not in df.columns and 'PlayerName' in df.columns:
                df = df.rename(columns={'PlayerName': 'Name'})
            if 'PA' in df.columns:
                df = df[df['PA'] >= min_pa]
            return df.reset_index(drop=True)
        return self.league.batters.qualified(min_pa).copy()

    def _get_pit_df(self, min_ip: float) -> pd.DataFrame:
        """Return the pitching DataFrame to score — projections or historical."""
        if self._use_projections:
            df = self.league.pitchers.projections.copy()
            if 'Name' not in df.columns and 'PlayerName' in df.columns:
                df = df.rename(columns={'PlayerName': 'Name'})
            if 'IP' in df.columns:
                df = df[df['IP'] >= min_ip]
            return df.reset_index(drop=True)
        return self.league.pitchers.qualified(min_ip).copy()

    def _to_outs(self, ip_series: pd.Series) -> pd.Series:
        """Convert IP to outs. Projections use decimal IP; historical uses FG notation."""
        if self._use_projections:
            return (ip_series * 3).round().astype(int)
        return ip_series.apply(_ip_to_outs)

    def rank(self, min_pa: int = 100, min_ip: float = 20) -> pd.DataFrame:
        """
        Rank all qualified players by fantasy value.

        Returns a DataFrame sorted descending by fantasy_score with a 1-based
        rank index and per-stat breakdown columns (pts_* or z_*).
        """
        if self._scoring_type == 'points':
            return self._rank_points(min_pa, min_ip)
        else:
            return self._rank_categories(min_pa, min_ip)

    # ── Points ranking ────────────────────────────────────────────────────────

    def _rank_points(self, min_pa: int, min_ip: float) -> pd.DataFrame:
        pts_cfg = self.scoring  # {'batting': {...}, 'pitching': {...}}

        # Batters
        bat_df = self._get_bat_df(min_pa)
        bat_pts = pts_cfg['batting']
        for stat, val in bat_pts.items():
            bat_df[f'pts_{stat}'] = bat_df[stat].fillna(0) * val if stat in bat_df.columns else 0.0
        bat_df['fantasy_score'] = sum(bat_df[f'pts_{s}'] for s in bat_pts)
        bat_df['player_type'] = 'batter'

        # Pitchers — convert IP to Outs (format differs between historical and projections)
        pit_df = self._get_pit_df(min_ip)
        pit_df['Outs'] = self._to_outs(pit_df['IP'])
        pit_pts = pts_cfg['pitching']
        for stat, val in pit_pts.items():
            pit_df[f'pts_{stat}'] = pit_df[stat].fillna(0) * val if stat in pit_df.columns else 0.0
        pit_df['fantasy_score'] = sum(pit_df[f'pts_{s}'] for s in pit_pts)
        pit_df['player_type'] = 'pitcher'

        return self._finalize(bat_df, pit_df)

    # ── Categories / Roto ranking (z-score based) ─────────────────────────────

    def _rank_categories(self, min_pa: int, min_ip: float) -> pd.DataFrame:
        cats = self.scoring  # {'batting': [...], 'pitching': [...]}
        bat_cats = cats['batting']   # ['R', 'HR', 'RBI', 'SB', 'AVG']
        pit_cats = cats['pitching']  # ['W', 'SV', 'SO', 'ERA', 'WHIP']

        bat_df = self._get_bat_df(min_pa)
        pit_df = self._get_pit_df(min_ip)

        # Batting z-scores
        for cat in bat_cats:
            if cat == 'AVG':
                pool_mean = bat_df['AVG'].mean()
                excess_hits = (bat_df['AVG'] - pool_mean) * bat_df['AB']
                bat_df['z_AVG'] = _safe_zscore(excess_hits)
            else:
                bat_df[f'z_{cat}'] = _safe_zscore(bat_df[cat].fillna(0))

        bat_df['fantasy_score'] = sum(bat_df[f'z_{cat}'] for cat in bat_cats)
        bat_df['player_type'] = 'batter'

        # Pitching z-scores
        for cat in pit_cats:
            if cat == 'ERA':
                pool_mean = pit_df['ERA'].mean()
                era_contrib = (pool_mean - pit_df['ERA']) * pit_df['IP'] / 9
                pit_df['z_ERA'] = _safe_zscore(era_contrib)
            elif cat == 'WHIP':
                pool_mean = pit_df['WHIP'].mean()
                whip_contrib = (pool_mean - pit_df['WHIP']) * pit_df['IP']
                pit_df['z_WHIP'] = _safe_zscore(whip_contrib)
            else:
                pit_df[f'z_{cat}'] = _safe_zscore(pit_df[cat].fillna(0))

        pit_df['fantasy_score'] = sum(pit_df[f'z_{cat}'] for cat in pit_cats)
        pit_df['player_type'] = 'pitcher'

        return self._finalize(bat_df, pit_df)

    # ── Shared finalization ───────────────────────────────────────────────────

    @staticmethod
    def _finalize(bat_df: pd.DataFrame, pit_df: pd.DataFrame) -> pd.DataFrame:
        combined = pd.concat([bat_df, pit_df], ignore_index=True)
        combined = combined.sort_values('fantasy_score', ascending=False).reset_index(drop=True)
        combined.index = range(1, len(combined) + 1)
        combined.index.name = 'rank'
        return combined
