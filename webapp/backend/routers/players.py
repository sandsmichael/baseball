"""
Cross-league player lookup: availability + historical stats + multi-system projections.
"""
import sys
import os
import math
from statistics import mean

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from urllib.parse import quote_plus

from yahoo_oauth import OAuth2
from yahoo import Yahoo, _fetch_fg_projections, _refresh_tokens, _token_is_expired

from ..config import CREDS_FILE, SEASON
from ..routers.dashboard import _get_leagues_df
from ..serializers import _clean

BASE = 'https://fantasysports.yahooapis.com/fantasy/v2'

router = APIRouter(prefix='/api/players', tags=['players'])

# Projection systems to try (fangraphs/zipr are preseason-only)
_PROJ_SYSTEMS = ['steamer', 'steamerr', 'atc', 'zips', 'thebat', 'thebatx']

_BAT_STAT_COLS = ['G', 'PA', 'AB', 'H', 'HR', 'RBI', 'R', 'SB', 'AVG', 'OBP', 'SLG', 'OPS', 'wRC+', 'WAR', 'BB%', 'K%', 'EV', 'Barrel%', 'HardHit%']
_PIT_STAT_COLS = ['G', 'GS', 'IP', 'W', 'L', 'SV', 'HLD', 'SO', 'BB', 'ERA', 'WHIP', 'FIP', 'xERA', 'K/9', 'BB/9', 'HR/9']
_BAT_PROJ_COLS = ['PA', 'AB', 'H', 'HR', 'RBI', 'R', 'SB', 'AVG', 'OBP', 'SLG', 'OPS', 'wRC+', 'BB%', 'K%']
_PIT_PROJ_COLS = ['IP', 'W', 'L', 'SV', 'HLD', 'SO', 'BB', 'ERA', 'WHIP', 'FIP', 'K/9', 'BB/9']


# ── OAuth / API helpers ────────────────────────────────────────────────────────

def _oauth():
    if _token_is_expired(CREDS_FILE):
        _refresh_tokens(CREDS_FILE)
    return OAuth2(None, None, from_file=CREDS_FILE)


def _api_get(oauth, path: str) -> dict:
    if not oauth.token_is_valid():
        _refresh_tokens(CREDS_FILE)
    resp = oauth.session.get(f'{BASE}{path}?format=json')
    resp.raise_for_status()
    return resp.json()


def _resolve_game_key(oauth) -> str:
    data = _api_get(oauth, f'/games;game_codes=mlb;seasons={SEASON}')
    return data['fantasy_content']['games']['0']['game'][0]['game_key']


# ── Player search ──────────────────────────────────────────────────────────────

def _search_players(oauth, league_key: str, name: str, count: int = 10) -> list[dict]:
    """Search players by name, return up to `count` results."""
    data = _api_get(oauth, f'/league/{league_key}/players;search={quote_plus(name)};count={count}')
    players_data = data['fantasy_content']['league'][1]['players']
    if not isinstance(players_data, dict):
        return []
    results = []
    for i in range(min(players_data.get('count', 0), count)):
        flat = Yahoo._flat(players_data[str(i)]['player'][0])
        results.append({
            'name':       Yahoo._name(flat.get('name', '')),
            'team':       flat.get('editorial_team_abbr', ''),
            'positions':  flat.get('display_position', ''),
            'status':     flat.get('status', '') or '',
            'player_key': flat.get('player_key', ''),
            'headshot_url': flat.get('image_url', '') or '',
        })
    return results


# ── Ownership ─────────────────────────────────────────────────────────────────

def _get_ownership(oauth, league_key: str, player_key: str) -> dict:
    try:
        data = _api_get(oauth, f'/league/{league_key}/players;player_keys={player_key};out=ownership')
        players = data['fantasy_content']['league'][1]['players']
        if not isinstance(players, dict) or not players.get('count', 0):
            return {'ownership_type': 'freeagents', 'owner_team_name': None}
        p = players['0']['player']
        ownership_raw = {}
        if len(p) > 1 and isinstance(p[1], dict):
            ownership_raw = p[1].get('ownership', {})
            if isinstance(ownership_raw, list):
                ownership_raw = Yahoo._flat(ownership_raw)
        otype = ownership_raw.get('ownership_type', 'freeagents')
        owner_name = ownership_raw.get('owner_team_name') or None
        return {'ownership_type': otype, 'owner_team_name': owner_name}
    except Exception:
        return {'ownership_type': 'unknown', 'owner_team_name': None}


# ── Stats helpers ──────────────────────────────────────────────────────────────

def _row_to_dict(r, cols: list[str]) -> dict:
    return {c: _clean(r[c]) for c in cols if c in r.index}


def _fetch_season_stats(name: str, season: int, is_pitcher: bool) -> dict | None:
    """Fetch actual stats for a given season. Returns None if unavailable."""
    norm = Yahoo._norm_name(name)
    try:
        if is_pitcher:
            from baseball import Pitchers
            df = Pitchers(season).fetch().all
            cols = _PIT_STAT_COLS
        else:
            from baseball import Batters
            df = Batters(season).fetch().all
            cols = _BAT_STAT_COLS
        if 'Name' not in df.columns:
            return None
        df['_norm'] = df['Name'].map(Yahoo._norm_name)
        row = df[df['_norm'] == norm]
        if row.empty:
            row = df[df['_norm'].str.contains(norm[:6], na=False)]
        if row.empty:
            return None
        r = row.iloc[0]
        result = _row_to_dict(r, cols)
        return result if any(v is not None for v in result.values()) else None
    except Exception:
        return None


def _fetch_proj_for_system(name: str, system: str, is_pitcher: bool) -> dict | None:
    """Fetch projections for one system. Returns None if player not found."""
    norm = Yahoo._norm_name(name)
    stats_type = 'pit' if is_pitcher else 'bat'
    cols = _PIT_PROJ_COLS if is_pitcher else _BAT_PROJ_COLS
    try:
        df = _fetch_fg_projections(stats_type, system)
        if df.empty or 'Name' not in df.columns:
            return None
        df['_norm'] = df['Name'].map(Yahoo._norm_name)
        row = df[df['_norm'] == norm]
        if row.empty:
            row = df[df['_norm'].str.contains(norm[:6], na=False)]
        if row.empty:
            return None
        r = row.iloc[0]
        result = _row_to_dict(r, cols)
        return result if any(v is not None for v in result.values()) else None
    except Exception:
        return None


def _composite_projection(proj_by_system: dict[str, dict], is_pitcher: bool) -> dict:
    """Average numeric values across all systems that returned data."""
    cols = _PIT_PROJ_COLS if is_pitcher else _BAT_PROJ_COLS
    result = {}
    for col in cols:
        vals = []
        for sys_data in proj_by_system.values():
            if sys_data and col in sys_data and sys_data[col] is not None:
                try:
                    v = float(sys_data[col])
                    if not math.isnan(v) and not math.isinf(v):
                        vals.append(v)
                except (TypeError, ValueError):
                    pass
        if vals:
            avg = mean(vals)
            result[col] = round(avg, 3)
    return result


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get('/autocomplete')
def autocomplete(q: str = Query(..., min_length=1)):
    """Return up to 10 player suggestions for typeahead."""
    try:
        oauth = _oauth()
        leagues_df = _get_leagues_df()
        game_key = _resolve_game_key(oauth)
        league_key = f"{game_key}.l.{leagues_df['league_id'].iloc[0]}"
        players = _search_players(oauth, league_key, q, count=10)
        return {'players': players}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/lookup')
def lookup_player(q: str = Query(..., min_length=2)):
    """
    Full player profile:
    - Availability across all your leagues
    - Current + historical season stats (last 3 seasons)
    - Projections from each system (steamer, steamerr, atc, zips, thebat, thebatx)
    - Composite (average) projection
    """
    try:
        oauth = _oauth()
        leagues_df = _get_leagues_df()
        game_key = _resolve_game_key(oauth)

        # Find player in first league that returns a result
        player_info = None
        for _, lrow in leagues_df.iterrows():
            lk = f"{game_key}.l.{lrow['league_id']}"
            results = _search_players(oauth, lk, q, count=1)
            if results:
                player_info = results[0]
                break

        if not player_info:
            return JSONResponse(status_code=404, content={'error': f'Player not found: {q!r}'})

        player_key = player_info['player_key']
        positions = player_info['positions']
        is_pitcher = bool(set(str(positions).split(',')) & {'SP', 'RP', 'P'})

        # Availability per league
        availability = []
        for _, lrow in leagues_df.iterrows():
            lk = f"{game_key}.l.{lrow['league_id']}"
            own = _get_ownership(oauth, lk, player_key)
            otype = own['ownership_type']
            if otype == 'team':
                label = own['owner_team_name'] or 'Owned'
                avail_status = 'mine' if own['owner_team_name'] == lrow['team_name'] else 'owned'
            elif otype == 'waivers':
                label = 'Waivers'
                avail_status = 'waivers'
            else:
                label = 'Free Agent'
                avail_status = 'fa'
            availability.append({
                'league_id':    lrow['league_id'],
                'league_name':  lrow['name'],
                'my_team':      lrow['team_name'],
                'avail_status': avail_status,
                'label':        label,
                'available':    avail_status in ('fa', 'waivers'),
            })

        # Current season stats
        current_stats = _fetch_season_stats(player_info['name'], SEASON, is_pitcher) or {}

        # Historical stats — last 3 completed seasons
        historical_stats = []
        for yr in range(SEASON - 1, SEASON - 4, -1):
            s = _fetch_season_stats(player_info['name'], yr, is_pitcher)
            if s:
                historical_stats.append({'season': yr, 'stats': s})

        # Per-system projections
        projections_by_system: dict[str, dict] = {}
        for system in _PROJ_SYSTEMS:
            proj = _fetch_proj_for_system(player_info['name'], system, is_pitcher)
            if proj:
                projections_by_system[system] = proj

        composite = _composite_projection(projections_by_system, is_pitcher)

        return {
            'player':                player_info,
            'is_pitcher':            is_pitcher,
            'availability':          availability,
            'current_stats':         current_stats,
            'historical_stats':      historical_stats,
            'projections_by_system': projections_by_system,
            'composite_projection':  composite,
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})
