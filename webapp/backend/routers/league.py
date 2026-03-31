"""
Per-league endpoints: read operations + mutation actions.

Mutations (add/drop/move/swap/etc.) use Playwright browser automation
and are run in a ThreadPoolExecutor to avoid blocking the FastAPI event loop.
"""
import asyncio
import sys
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from yahoo import Yahoo

from ..config import CREDS_FILE, SEASON
from ..cache import (
    cache,
    TTL_ROSTER, TTL_MATCHUP, TTL_STANDINGS, TTL_WAIVERS, TTL_ADP,
)
from ..serializers import df_to_records

router = APIRouter(prefix='/api/leagues', tags=['league'])
_executor = ThreadPoolExecutor(max_workers=4)


def _yf(league_id: str) -> Yahoo:
    return Yahoo(league_id=league_id, season=SEASON, creds_file=CREDS_FILE).fetch()


# ── Read endpoints ─────────────────────────────────────────────────────────────

@router.get('/{league_id}/roster')
def get_roster(league_id: str, refresh: bool = Query(False)):
    key = f'roster:{league_id}'
    if not refresh:
        cached = cache.get(key, TTL_ROSTER)
        if cached is not None:
            return {'roster': cached, 'cached_age': cache.age(key)}
    try:
        yf = _yf(league_id)
        records = df_to_records(yf.roster)
        cache.set(key, records)
        return {'roster': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/{league_id}/matchup')
def get_matchup(league_id: str, refresh: bool = Query(False)):
    key = f'matchup:{league_id}'
    if not refresh:
        cached = cache.get(key, TTL_MATCHUP)
        if cached is not None:
            return {'matchup': cached, 'cached_age': cache.age(key)}
    try:
        yf = _yf(league_id)
        m = yf.matchup
        cache.set(key, m)
        return {'matchup': m, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/{league_id}/opponent-roster')
def get_opponent_roster(league_id: str, refresh: bool = Query(False)):
    key = f'opp_roster:{league_id}'
    if not refresh:
        cached = cache.get(key, TTL_MATCHUP)
        if cached is not None:
            return {'roster': cached, 'cached_age': cache.age(key)}
    try:
        yf = _yf(league_id)
        records = df_to_records(yf.opponent_roster)
        cache.set(key, records)
        return {'roster': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/{league_id}/standings')
def get_standings(league_id: str, refresh: bool = Query(False)):
    key = f'standings:{league_id}'
    if not refresh:
        cached = cache.get(key, TTL_STANDINGS)
        if cached is not None:
            return {'standings': cached, 'cached_age': cache.age(key)}
    try:
        yf = _yf(league_id)
        records = df_to_records(yf.standings)
        cache.set(key, records)
        return {'standings': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/{league_id}/waivers')
def get_waivers(
    league_id: str,
    position: Optional[str] = Query(None),
    count: int = Query(50, ge=1, le=500),
    refresh: bool = Query(False),
):
    key = f'waivers:{league_id}:{position}:{count}'
    if not refresh:
        cached = cache.get(key, TTL_WAIVERS)
        if cached is not None:
            return {'players': cached, 'cached_age': cache.age(key)}
    try:
        yf = _yf(league_id)
        records = df_to_records(yf.waivers(position=position, count=count))
        cache.set(key, records)
        return {'players': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/{league_id}/free-agents')
def get_free_agents(
    league_id: str,
    position: Optional[str] = Query(None),
    count: int = Query(50, ge=1, le=500),
    refresh: bool = Query(False),
):
    key = f'fa:{league_id}:{position}:{count}'
    if not refresh:
        cached = cache.get(key, TTL_WAIVERS)
        if cached is not None:
            return {'players': cached, 'cached_age': cache.age(key)}
    try:
        yf = _yf(league_id)
        records = df_to_records(yf.free_agents(position=position, count=count))
        cache.set(key, records)
        return {'players': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/{league_id}/search')
def search_player(league_id: str, q: str = Query(..., min_length=2)):
    try:
        yf = _yf(league_id)
        records = df_to_records(yf.search(q))
        return {'players': records}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/{league_id}/available-with-projections')
def get_available_with_projections(
    league_id: str,
    mode: str = Query('waivers', pattern='^(waivers|fa)$'),
    position: Optional[str] = Query(None),
    proj_system: str = Query('steamer'),
    count: int = Query(50, ge=1, le=200),
    refresh: bool = Query(False),
):
    key = f'avail_proj:{league_id}:{mode}:{position}:{proj_system}:{count}'
    if not refresh:
        cached = cache.get(key, TTL_WAIVERS)
        if cached is not None:
            return {'players': cached, 'cached_age': cache.age(key)}
    try:
        import math
        from yahoo import _fetch_fg_projections

        yf = _yf(league_id)
        pos_param = f';position={position}' if position else ''
        status = 'W' if mode == 'waivers' else 'FA'
        data = yf._get(
            f'/league/{yf._league_key}/players'
            f';status={status}{pos_param};count={count};out=percent_owned;sort=AR'
        )
        players_raw = data['fantasy_content']['league'][1]['players']
        if not isinstance(players_raw, dict):
            cache.set(key, [])
            return {'players': [], 'cached_age': cache.age(key)}

        players = []
        for i in range(players_raw.get('count', 0)):
            p = players_raw[str(i)]['player']
            flat = Yahoo._flat(p[0])
            name = Yahoo._name(flat.get('name', ''))
            positions_str = flat.get('display_position', '')
            is_pitcher = bool(set(positions_str.split(',')) & {'SP', 'RP', 'P'})
            players.append({
                'name': name,
                'team': flat.get('editorial_team_abbr', ''),
                'positions': positions_str,
                'status': flat.get('status', '') or '',
                'player_key': flat.get('player_key', ''),
                'pct_owned': Yahoo._parse_pct_owned(p[1] if len(p) > 1 else {}),
                'is_pitcher': is_pitcher,
            })

        # Fetch projections in bulk
        _BAT_PROJ_COLS = ['PA', 'HR', 'RBI', 'R', 'SB', 'AVG', 'OBP', 'SLG', 'OPS', 'wRC+']
        _PIT_PROJ_COLS = ['IP', 'W', 'SV', 'HLD', 'SO', 'ERA', 'WHIP', 'K/9']

        try:
            bat_df = _fetch_fg_projections('bat', proj_system)
            if 'Name' in bat_df.columns:
                bat_df['_norm'] = bat_df['Name'].map(Yahoo._norm_name)
        except Exception:
            bat_df = None

        try:
            pit_df = _fetch_fg_projections('pit', proj_system)
            if 'Name' in pit_df.columns:
                pit_df['_norm'] = pit_df['Name'].map(Yahoo._norm_name)
        except Exception:
            pit_df = None

        def _get_proj(name: str, is_pitcher: bool) -> dict:
            df = pit_df if is_pitcher else bat_df
            cols = _PIT_PROJ_COLS if is_pitcher else _BAT_PROJ_COLS
            if df is None or df.empty or 'Name' not in df.columns:
                return {}
            norm = Yahoo._norm_name(name)
            row = df[df['_norm'] == norm]
            if row.empty:
                row = df[df['_norm'].str.contains(norm[:6], na=False)]
            if row.empty:
                return {}
            r = row.iloc[0]
            result = {}
            for c in cols:
                if c in r.index:
                    v = r[c]
                    try:
                        v = float(v)
                        if math.isnan(v) or math.isinf(v):
                            v = None
                        else:
                            v = round(v, 3)
                    except (TypeError, ValueError):
                        v = None
                    result[c] = v
            return result

        for p in players:
            p['projections'] = _get_proj(p['name'], p['is_pitcher'])

        cache.set(key, players)
        return {'players': players, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/{league_id}/transactions')
def get_transactions(league_id: str, refresh: bool = Query(False)):
    key = f'transactions:{league_id}'
    if not refresh:
        cached = cache.get(key, 60)
        if cached is not None:
            return {'transactions': cached, 'cached_age': cache.age(key)}
    try:
        yf = _yf(league_id)
        data = yf._get(
            f'/league/{yf._league_key}/transactions'
            f';types=pending_trade,waiver'
            f';team_key={yf._team_key}'
        )
        raw = data['fantasy_content']['league'][1]['transactions']
        count = raw.get('count', 0)
        txns = []
        for i in range(count):
            entry = raw[str(i)]['transaction']
            meta = entry[0]
            players_raw = entry[1].get('players', {}) if len(entry) > 1 else {}
            adds, drops = [], []
            p_count = players_raw.get('count', 0) if isinstance(players_raw, dict) else 0
            for j in range(p_count):
                p = players_raw[str(j)]['player']
                flat = Yahoo._flat(p[0])
                td = p[1].get('transaction_data', {}) if len(p) > 1 else {}
                name = Yahoo._name(flat.get('name', ''))
                team = flat.get('editorial_team_abbr', '')
                pos = flat.get('display_position', '')
                if td.get('type') == 'add':
                    adds.append({'name': name, 'team': team, 'positions': pos})
                elif td.get('type') == 'drop':
                    drops.append({'name': name, 'team': team, 'positions': pos})
            txns.append({
                'type': meta.get('type', ''),
                'status': meta.get('status', ''),
                'team_name': meta.get('waiver_team_name') or meta.get('trader_team_name', ''),
                'date': meta.get('waiver_date') or meta.get('trade_note_time', ''),
                'faab_bid': meta.get('faab_bid'),
                'waiver_priority': meta.get('waiver_priority'),
                'adds': adds,
                'drops': drops,
            })
        cache.set(key, txns)
        return {'transactions': txns, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get('/{league_id}/adp')
def get_adp(
    league_id: str,
    n: int = Query(300, ge=1, le=500),
    refresh: bool = Query(False),
):
    key = f'adp:{league_id}:{n}'
    if not refresh:
        cached = cache.get(key, TTL_ADP)
        if cached is not None:
            return {'players': cached, 'cached_age': cache.age(key)}
    try:
        yf = _yf(league_id)
        records = df_to_records(yf.adp(n=n))
        cache.set(key, records)
        return {'players': records, 'cached_age': cache.age(key)}
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


# ── Mutation request bodies ────────────────────────────────────────────────────

class AddRequest(BaseModel):
    player: str
    drop: Optional[str] = None
    faab: Optional[int] = None


class DropRequest(BaseModel):
    player: str


class TradeRequest(BaseModel):
    give: list[str]
    receive: list[str]
    team: str


class MoveRequest(BaseModel):
    player: str
    position: str
    date: Optional[str] = None


class PlayerRequest(BaseModel):
    player: str


class SwapRequest(BaseModel):
    player1: str
    player2: str


# ── Mutation helpers ───────────────────────────────────────────────────────────

def _invalidate_roster(league_id: str):
    cache.invalidate(
        f'roster:{league_id}',
        f'opp_roster:{league_id}',
        'all_rosters',
        'il_candidates',
        'dtd_candidates',
    )
    cache.invalidate_prefix(f'waivers:{league_id}')
    cache.invalidate_prefix(f'fa:{league_id}')


async def _run_mutation(fn, timeout: float = 120.0):
    loop = asyncio.get_event_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(_executor, fn),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise RuntimeError(f'Action timed out after {timeout:.0f}s')


# ── Mutation endpoints ─────────────────────────────────────────────────────────

@router.post('/{league_id}/add')
async def add_player(league_id: str, body: AddRequest):
    def _do():
        yf = _yf(league_id)
        yf.add(body.player, drop=body.drop, faab=body.faab)

    try:
        await _run_mutation(_do)
        _invalidate_roster(league_id)
        msg = f'Added {body.player}'
        if body.drop:
            msg += f', dropped {body.drop}'
        return {'success': True, 'message': msg}
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'message': str(e)})


@router.post('/{league_id}/drop')
async def drop_player(league_id: str, body: DropRequest):
    def _do():
        yf = _yf(league_id)
        yf.drop(body.player)

    try:
        await _run_mutation(_do)
        _invalidate_roster(league_id)
        return {'success': True, 'message': f'Dropped {body.player}'}
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'message': str(e)})


@router.post('/{league_id}/trade')
async def propose_trade(league_id: str, body: TradeRequest):
    def _do():
        yf = _yf(league_id)
        yf.trade(give=body.give, receive=body.receive, team=body.team)

    try:
        await _run_mutation(_do)
        return {'success': True, 'message': f'Trade proposal sent to {body.team}'}
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'message': str(e)})


@router.post('/{league_id}/move')
async def move_player(league_id: str, body: MoveRequest):
    def _do():
        yf = _yf(league_id)
        yf.move(body.player, body.position, body.date)

    try:
        await _run_mutation(_do)
        _invalidate_roster(league_id)
        return {'success': True, 'message': f'Moved {body.player} to {body.position}'}
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'message': str(e)})


@router.post('/{league_id}/bench')
async def bench_player(league_id: str, body: PlayerRequest):
    def _do():
        yf = _yf(league_id)
        yf.bench(body.player)

    try:
        await _run_mutation(_do)
        _invalidate_roster(league_id)
        return {'success': True, 'message': f'Benched {body.player}'}
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'message': str(e)})


@router.post('/{league_id}/start')
async def start_player(league_id: str, body: PlayerRequest):
    def _do():
        yf = _yf(league_id)
        yf.start(body.player)

    try:
        await _run_mutation(_do)
        _invalidate_roster(league_id)
        return {'success': True, 'message': f'Started {body.player}'}
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'message': str(e)})


@router.post('/{league_id}/il')
async def il_player(league_id: str, body: PlayerRequest):
    def _do():
        yf = _yf(league_id)
        yf.il(body.player)

    try:
        await _run_mutation(_do)
        _invalidate_roster(league_id)
        return {'success': True, 'message': f'Moved {body.player} to IL'}
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'message': str(e)})


@router.post('/{league_id}/swap')
async def swap_players(league_id: str, body: SwapRequest):
    def _do():
        yf = _yf(league_id)
        yf.swap(body.player1, body.player2)

    try:
        await _run_mutation(_do)
        _invalidate_roster(league_id)
        return {'success': True, 'message': f'Swapped {body.player1} ↔ {body.player2}'}
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'message': str(e)})
