"""
Cross-league dashboard endpoints.
All reads are cached. Pass ?refresh=true to force a fresh fetch.
"""
import sys
import os

# Ensure project root is on sys.path so yahoo / baseball modules are importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

import yahoo as _yahoo_mod
from yahoo import (
    Yahoo,
    all_rosters,
    top_available_all_leagues,
    top_available_with_stats,
    upgrade_candidates,
    il_candidates,
    dtd_candidates,
    il_overflow,
    benched_starters,
    all_matchup_scores,
)

from ..config import CREDS_FILE, SEASON, DEFAULT_PROJ_SYSTEM
from ..cache import cache, TTL_LEAGUES, TTL_ALL_ROSTERS, TTL_IL, TTL_DTD, TTL_TOP_AVAIL, TTL_TOP_STATS, TTL_UPGRADES, TTL_MATCHUP_SCORES
from ..serializers import df_to_records

router = APIRouter(prefix='/api', tags=['dashboard'])


def _get_leagues_df(refresh: bool = False):
    key = 'leagues'
    if not refresh:
        cached = cache.get(key, TTL_LEAGUES)
        if cached is not None:
            return cached
    df = Yahoo.list_leagues(CREDS_FILE, SEASON)
    cache.set(key, df)
    return df


@router.get('/leagues')
def list_leagues(refresh: bool = Query(False)):
    try:
        df = _get_leagues_df(refresh)
        return {'leagues': df_to_records(df), 'cached_age': cache.age('leagues')}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/rosters')
def get_all_rosters(refresh: bool = Query(False)):
    key = 'all_rosters'
    if not refresh:
        cached = cache.get(key, TTL_ALL_ROSTERS)
        if cached is not None:
            return {'rosters': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        df = all_rosters(leagues_df, CREDS_FILE, SEASON)
        # Wide format: columns = team names, index = slot names
        # Convert to {team_name: {slot: player_name}}
        result = {}
        for col in df.columns:
            result[col] = {str(idx): (val if val and str(val) != 'nan' else None)
                           for idx, val in df[col].items()}
        # Also return ordered slot list
        slots = list(df.index)
        cache.set(key, {'teams': result, 'slots': slots})
        return {'rosters': {'teams': result, 'slots': slots}, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/il-candidates')
def get_il_candidates(refresh: bool = Query(False)):
    key = 'il_candidates'
    if not refresh:
        cached = cache.get(key, TTL_IL)
        if cached is not None:
            return {'candidates': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        df = il_candidates(leagues_df, CREDS_FILE, SEASON)
        records = df_to_records(df)
        cache.set(key, records)
        return {'candidates': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/dtd-candidates')
def get_dtd_candidates(refresh: bool = Query(False)):
    key = 'dtd_candidates'
    if not refresh:
        cached = cache.get(key, TTL_DTD)
        if cached is not None:
            return {'candidates': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        df = dtd_candidates(leagues_df, CREDS_FILE, SEASON)
        records = df_to_records(df)
        cache.set(key, records)
        return {'candidates': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/il-overflow')
def get_il_overflow(refresh: bool = Query(False)):
    key = 'il_overflow'
    if not refresh:
        cached = cache.get(key, TTL_IL)
        if cached is not None:
            return {'candidates': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        df = il_overflow(leagues_df, CREDS_FILE, SEASON)
        records = df_to_records(df)
        cache.set(key, records)
        return {'candidates': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/top-available')
def get_top_available(
    n: int = Query(5, ge=1, le=20),
    refresh: bool = Query(False),
):
    key = f'top_available_{n}'
    if not refresh:
        cached = cache.get(key, TTL_TOP_AVAIL)
        if cached is not None:
            return {'players': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        df = top_available_all_leagues(leagues_df, CREDS_FILE, SEASON, n=n)
        records = df_to_records(df)
        cache.set(key, records)
        return {'players': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/top-available-with-stats')
def get_top_available_with_stats(
    n: int = Query(5, ge=1, le=20),
    refresh: bool = Query(False),
):
    key = f'top_available_stats_{n}'
    if not refresh:
        cached = cache.get(key, TTL_TOP_STATS)
        if cached is not None:
            return {'players': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        df = top_available_with_stats(leagues_df, CREDS_FILE, SEASON, n=n)
        records = df_to_records(df)
        cache.set(key, records)
        return {'players': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/empty-slots')
def get_empty_slots(refresh: bool = Query(False)):
    key = 'empty_slots'
    if not refresh:
        cached = cache.get(key, 300)
        if cached is not None:
            return {'empty_slots': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        results = []
        for _, lrow in leagues_df.iterrows():
            try:
                yf = Yahoo(lrow['league_id'], season=SEASON, creds_file=CREDS_FILE).fetch()

                # Get expected slot counts from league settings
                settings_data = yf._get(f'/league/{yf._league_key}/settings')
                settings_raw = settings_data['fantasy_content']['league'][1]['settings']
                flat = Yahoo._flat(settings_raw)
                rp_list = flat.get('roster_positions', [])
                expected: dict[str, int] = {}
                for entry in rp_list:
                    rp = entry.get('roster_position', {}) if isinstance(entry, dict) else {}
                    pos = rp.get('position', '')
                    cnt = rp.get('count', 0)
                    if pos:
                        try:
                            expected[pos] = expected.get(pos, 0) + int(cnt)
                        except (TypeError, ValueError):
                            pass

                # Count actual filled slots
                actual: dict[str, int] = {}
                for _, p in yf.roster.iterrows():
                    slot = p['slot']
                    actual[slot] = actual.get(slot, 0) + 1

                _IL_SLOTS = {'IL', 'IL+', 'IL10', 'IL15', 'IL60', 'DL', 'DL15', 'DL60', 'NA', 'NA+'}

                # Find empty slots (skip IL/DL slots)
                for slot, exp_count in expected.items():
                    if slot in _IL_SLOTS:
                        continue
                    filled = actual.get(slot, 0)
                    if filled < exp_count:
                        results.append({
                            'league': lrow['name'],
                            'league_id': lrow['league_id'],
                            'my_team': lrow['team_name'],
                            'slot': slot,
                            'empty_count': exp_count - filled,
                            'filled': filled,
                            'expected': exp_count,
                        })
            except Exception as e:
                print(f'empty-slots error ({lrow["name"]}): {e}')
        cache.set(key, results)
        return {'empty_slots': results, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/benched-starters')
def get_benched_starters(refresh: bool = Query(False)):
    key = 'benched_starters'
    if not refresh:
        cached = cache.get(key, TTL_DTD)
        if cached is not None:
            return {'candidates': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        df = benched_starters(leagues_df, CREDS_FILE, SEASON)
        records = df_to_records(df)
        cache.set(key, records)
        return {'candidates': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/matchup-scores')
def get_matchup_scores(refresh: bool = Query(False)):
    key = 'matchup_scores'
    if not refresh:
        cached = cache.get(key, TTL_MATCHUP_SCORES)
        if cached is not None:
            return {'matchups': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        results = all_matchup_scores(leagues_df, CREDS_FILE, SEASON)
        cache.set(key, results)
        return {'matchups': results, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/dashboard/upgrades')
def get_upgrades(
    n: int = Query(5, ge=1, le=20),
    proj_system: str = Query(DEFAULT_PROJ_SYSTEM),
    refresh: bool = Query(False),
):
    key = f'upgrades_{n}_{proj_system}'
    if not refresh:
        cached = cache.get(key, TTL_UPGRADES)
        if cached is not None:
            return {'upgrades': cached, 'cached_age': cache.age(key)}
    try:
        leagues_df = _get_leagues_df()
        df = upgrade_candidates(leagues_df, CREDS_FILE, SEASON, n=n, proj_system=proj_system)
        records = df_to_records(df)
        cache.set(key, records)
        return {'upgrades': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})
