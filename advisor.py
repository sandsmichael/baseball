"""
advisor.py — Interactive Fantasy Baseball AI Advisor

Claude claude-opus-4-6 calls your yahoo.py and baseball.py tools on demand.
No upfront data dump — Claude fetches exactly what it needs to answer your question.

Usage:
    conda run -n venv python advisor.py

Requirements:
    - .env file with Anthropic_API_Key (same file used for Yahoo credentials)
    - browser/yahoo_oauth.json with valid Yahoo tokens (run init_auth() once first)
"""

import json
import logging
import os
import sys
import traceback
from datetime import date

import anthropic

# Suppress DEBUG/INFO noise from yahoo_oauth and HTTP libraries globally.
# logging.disable() is a process-level override — it blocks records below
# the given level regardless of how individual loggers configure handlers.
logging.disable(logging.INFO)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yahoo import Yahoo, load_env
from baseball import League

# ---------------------------------------------------------------------------
# Season detection — use current year Jan–Oct, next year Nov–Dec
# (ensures we never target a completed/expired season)
# ---------------------------------------------------------------------------

def _active_season() -> int:
    today = date.today()
    return today.year if today.month <= 10 else today.year + 1

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

session: dict = {
    'leagues':    None,   # pd.DataFrame from Yahoo.list_leagues()
    'yahoo':      {},     # {league_id: Yahoo} — lazy, one per league
    'league_obj': None,   # baseball.League — lazy, for player stat lookups
    'history':    [],     # full Claude conversation history
    'season':     _active_season(),
}

CREDS_FILE = 'browser/yahoo_oauth.json'

# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _df_to_records(df, limit=None) -> list:
    if df is None or len(df) == 0:
        return []
    if limit:
        df = df.head(limit)
    return df.fillna('').to_dict('records')


def _get_yahoo(league_id: str) -> Yahoo:
    lid = str(league_id)
    if lid not in session['yahoo']:
        print(f"  [Connecting to league {lid}...]", flush=True)
        y = Yahoo(league_id=lid, season=session['season'], creds_file=CREDS_FILE).fetch()
        session['yahoo'][lid] = y
    return session['yahoo'][lid]


def _get_league_obj() -> League:
    if session['league_obj'] is None:
        print("  [Loading player stats database...]", flush=True)
        session['league_obj'] = League(session['season']).fetch()
    return session['league_obj']


def _confirm(description: str) -> bool:
    print(f"\n  Proposed action: {description}")
    try:
        ans = input("  Confirm? [y/N] ").strip().lower()
        return ans in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        return False


# ---------------------------------------------------------------------------
# Tool implementations — read (no confirmation needed)
# ---------------------------------------------------------------------------

def tool_list_leagues(_inp: dict) -> dict:
    if session['leagues'] is not None:
        return {'leagues': _df_to_records(session['leagues'])}
    leagues = Yahoo.list_leagues(CREDS_FILE, season=session['season'])
    session['leagues'] = leagues
    return {'leagues': _df_to_records(leagues)}


def tool_get_roster(inp: dict) -> dict:
    y = _get_yahoo(inp['league_id'])
    return {'roster': _df_to_records(y.roster)}


def tool_get_opponent_roster(inp: dict) -> dict:
    y = _get_yahoo(inp['league_id'])
    return {'opponent_roster': _df_to_records(y.opponent_roster)}


def tool_get_matchup(inp: dict) -> dict:
    y = _get_yahoo(inp['league_id'])
    m = y.matchup
    return {'matchup': {k: str(v) for k, v in m.items()}}


def tool_get_standings(inp: dict) -> dict:
    y = _get_yahoo(inp['league_id'])
    return {'standings': _df_to_records(y.standings)}


def tool_get_free_agents(inp: dict) -> dict:
    y = _get_yahoo(inp['league_id'])
    fa = y.free_agents(
        position=inp.get('position'),
        count=int(inp.get('count', 25)),
    )
    return {'free_agents': _df_to_records(fa)}


def tool_get_player_stats(inp: dict) -> dict:
    league = _get_league_obj()
    result = league.find(inp['name'])
    if result is None or len(result) == 0:
        return {'error': f"No stats found for \"{inp['name']}\""}
    return {'stats': _df_to_records(result, limit=3)}


def tool_get_player_projections(inp: dict) -> dict:
    name = inp['name']
    league = _get_league_obj()
    for obj in [league.batters, league.pitchers]:
        result = obj.find(name)
        if result is not None and len(result) > 0:
            proj = obj.projections
            mask = proj['Name'].str.contains(name, case=False, na=False)
            if mask.any():
                return {'projections': _df_to_records(proj[mask], limit=3)}
    return {'error': f'No projections found for "{name}"'}


# ---------------------------------------------------------------------------
# Tool implementations — write (confirmation required)
# ---------------------------------------------------------------------------

def tool_add_player(inp: dict) -> dict:
    player = inp['player']
    drop   = inp.get('drop')
    faab   = inp.get('faab')
    desc   = f"Add {player}" + (f", drop {drop}" if drop else "") + (f" (FAAB: ${faab})" if faab else "")
    if not _confirm(desc):
        return {'status': 'cancelled'}
    _get_yahoo(inp['league_id']).add(player, drop=drop, faab=faab)
    return {'status': 'success', 'action': desc}


def tool_drop_player(inp: dict) -> dict:
    player = inp['player']
    desc   = f"Drop {player}"
    if not _confirm(desc):
        return {'status': 'cancelled'}
    _get_yahoo(inp['league_id']).drop(player)
    return {'status': 'success', 'action': desc}


def tool_move_player(inp: dict) -> dict:
    player   = inp['player']
    position = inp['position']
    for_date = inp.get('date')
    desc     = f"Move {player} → {position}" + (f" on {for_date}" if for_date else "")
    if not _confirm(desc):
        return {'status': 'cancelled'}
    _get_yahoo(inp['league_id']).move(player, position, for_date=for_date)
    return {'status': 'success', 'action': desc}


def tool_start_player(inp: dict) -> dict:
    player   = inp['player']
    for_date = inp.get('date')
    desc     = f"Start {player}" + (f" on {for_date}" if for_date else "")
    if not _confirm(desc):
        return {'status': 'cancelled'}
    _get_yahoo(inp['league_id']).start(player, for_date=for_date)
    return {'status': 'success', 'action': desc}


def tool_bench_player(inp: dict) -> dict:
    player   = inp['player']
    for_date = inp.get('date')
    desc     = f"Bench {player}" + (f" on {for_date}" if for_date else "")
    if not _confirm(desc):
        return {'status': 'cancelled'}
    _get_yahoo(inp['league_id']).bench(player, for_date=for_date)
    return {'status': 'success', 'action': desc}


def tool_swap_players(inp: dict) -> dict:
    p1       = inp['player1']
    p2       = inp['player2']
    for_date = inp.get('date')
    desc     = f"Swap {p1} ↔ {p2}" + (f" on {for_date}" if for_date else "")
    if not _confirm(desc):
        return {'status': 'cancelled'}
    _get_yahoo(inp['league_id']).swap(p1, p2, for_date=for_date)
    return {'status': 'success', 'action': desc}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

TOOL_HANDLERS = {
    'list_leagues':           tool_list_leagues,
    'get_roster':             tool_get_roster,
    'get_opponent_roster':    tool_get_opponent_roster,
    'get_matchup':            tool_get_matchup,
    'get_standings':          tool_get_standings,
    'get_free_agents':        tool_get_free_agents,
    'get_player_stats':       tool_get_player_stats,
    'get_player_projections': tool_get_player_projections,
    'add_player':             tool_add_player,
    'drop_player':            tool_drop_player,
    'move_player':            tool_move_player,
    'start_player':           tool_start_player,
    'bench_player':           tool_bench_player,
    'swap_players':           tool_swap_players,
}


def tool_executor(name: str, inp: dict) -> dict:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {'error': f'Unknown tool: {name}'}
    try:
        return handler(inp)
    except Exception as e:
        traceback.print_exc()
        return {'error': str(e)}


# ---------------------------------------------------------------------------
# Claude tool schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "list_leagues",
        "description": "List all of the user's active Yahoo Fantasy Baseball leagues. Returns league_id, name, scoring_method, num_teams. Call this first if you don't know the user's league IDs.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_roster",
        "description": "Get the user's current roster for a league. Returns each player's slot, name, MLB team, eligible positions, and injury status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
            },
            "required": ["league_id"],
        },
    },
    {
        "name": "get_opponent_roster",
        "description": "Get the current week's opponent's roster. Useful for matchup analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
            },
            "required": ["league_id"],
        },
    },
    {
        "name": "get_matchup",
        "description": "Get this week's matchup: week number, start/end dates, your team name, and opponent's team name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
            },
            "required": ["league_id"],
        },
    },
    {
        "name": "get_standings",
        "description": "Get current league standings: rank, team name, wins, losses, ties, win%, games back.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
            },
            "required": ["league_id"],
        },
    },
    {
        "name": "get_free_agents",
        "description": "Get available free agents / waiver players in a league, optionally filtered by position. Returns name, MLB team, eligible positions, and injury status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
                "position": {
                    "type": "string",
                    "description": "Optional position filter: C, 1B, 2B, 3B, SS, OF, SP, RP",
                },
                "count": {
                    "type": "integer",
                    "description": "Number to return (default 25)",
                    "default": 25,
                },
            },
            "required": ["league_id"],
        },
    },
    {
        "name": "get_player_stats",
        "description": "Get a player's current season stats from FanGraphs + Statcast. Batters: PA, AVG, OBP, SLG, wRC+, xwOBA, HR, RBI, SB, etc. Pitchers: IP, ERA, FIP, xFIP, K%, BB%, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Player name (partial match OK, e.g. 'Judge' or 'Ohtani')"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_player_projections",
        "description": "Get rest-of-season Steamer projections for a player. Useful for comparing players or evaluating trade targets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Player name (partial match OK)"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "add_player",
        "description": "Add a free agent player to the roster. Optionally drop another in the same transaction. The user will be asked to confirm before this executes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
                "player":    {"type": "string", "description": "Name of player to add"},
                "drop":      {"type": "string", "description": "Optional: name of player to drop in the same move"},
                "faab":      {"type": "integer", "description": "Optional: FAAB bid amount (for FAAB waiver leagues)"},
            },
            "required": ["league_id", "player"],
        },
    },
    {
        "name": "drop_player",
        "description": "Drop a player from the user's roster. The user will be asked to confirm before this executes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
                "player":    {"type": "string", "description": "Name of player to drop"},
            },
            "required": ["league_id", "player"],
        },
    },
    {
        "name": "move_player",
        "description": "Move a player to a specific roster slot. The user will be asked to confirm before this executes. Valid slots: BN, IL, IL+, C, 1B, 2B, 3B, SS, OF, Util, DH, SP, RP, P.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
                "player":    {"type": "string", "description": "Player name"},
                "position":  {"type": "string", "description": "Target slot: BN, IL, IL+, C, 1B, 2B, 3B, SS, OF, Util, DH, SP, RP, P"},
                "date":      {"type": "string", "description": "Optional: YYYY-MM-DD date"},
            },
            "required": ["league_id", "player", "position"],
        },
    },
    {
        "name": "start_player",
        "description": "Move a benched player to their first available active slot. The user will be asked to confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
                "player":    {"type": "string", "description": "Player name"},
                "date":      {"type": "string", "description": "Optional: YYYY-MM-DD date"},
            },
            "required": ["league_id", "player"],
        },
    },
    {
        "name": "bench_player",
        "description": "Move an active player to the bench. The user will be asked to confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
                "player":    {"type": "string", "description": "Player name"},
                "date":      {"type": "string", "description": "Optional: YYYY-MM-DD date"},
            },
            "required": ["league_id", "player"],
        },
    },
    {
        "name": "swap_players",
        "description": "Swap two players' roster positions (e.g., bring a bench player active, bench an active player). The user will be asked to confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Yahoo league ID"},
                "player1":   {"type": "string", "description": "First player"},
                "player2":   {"type": "string", "description": "Second player"},
                "date":      {"type": "string", "description": "Optional: YYYY-MM-DD date"},
            },
            "required": ["league_id", "player1", "player2"],
        },
    },
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    today = date.today().strftime('%B %d, %Y')
    return f"""You are an expert fantasy baseball advisor managing the user's Yahoo Fantasy Baseball leagues.

Today is {today}. Season: {session['season']}.

Guidelines:
- Fetch only the data you need to answer the question — don't pull everything upfront.
- When recommending a transaction, lead with concrete reasoning: relevant stats, injury context, schedule.
- Before calling add_player / drop_player / move_player / swap_players, explain why in your response first. The tool will then prompt the user to confirm before executing.
- Prefer recent trends + projections over career stats for in-season decisions.
- Be direct — give a clear recommendation. If genuinely uncertain between options, explain the tradeoff briefly.
- If you don't know a league ID, call list_leagues first.
- For player questions, use get_player_stats for current production and get_player_projections for rest-of-season outlook."""


# ---------------------------------------------------------------------------
# Chat loop
# ---------------------------------------------------------------------------

def chat_loop(client: anthropic.Anthropic) -> None:
    system = build_system_prompt()
    print("Type your question, or 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ('quit', 'exit', 'q'):
            print("Goodbye!")
            break

        session['history'].append({"role": "user", "content": user_input})

        # Inner agentic loop — keep calling Claude until stop_reason == end_turn
        while True:
            try:
                printed_prefix = False

                with client.messages.stream(
                    model="claude-opus-4-6",
                    max_tokens=4096,
                    thinking={"type": "adaptive"},
                    system=system,
                    tools=TOOLS,
                    messages=session['history'],
                ) as stream:
                    for text in stream.text_stream:
                        if not printed_prefix:
                            print("\nAdvisor: ", end="", flush=True)
                            printed_prefix = True
                        print(text, end="", flush=True)

                    response = stream.get_final_message()

                if printed_prefix:
                    print()  # newline after streamed text

            except anthropic.APIError as e:
                print(f"\n[API error: {e}]")
                session['history'].pop()
                break

            if response.stop_reason == "end_turn":
                session['history'].append({
                    "role": "assistant",
                    "content": response.content,
                })
                break

            elif response.stop_reason == "tool_use":
                session['history'].append({
                    "role": "assistant",
                    "content": response.content,
                })

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"\n  [→ {block.name}({json.dumps(block.input, separators=(',', ':'))})]", flush=True)
                        result = tool_executor(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })

                session['history'].append({"role": "user", "content": tool_results})
                # Loop back: Claude processes results and either responds or calls more tools

            else:
                print(f"\n[Unexpected stop_reason: {response.stop_reason}]")
                session['history'].append({
                    "role": "assistant",
                    "content": response.content,
                })
                break


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def init_session() -> None:
    print("=" * 60)
    print("  Fantasy Baseball AI Advisor")
    print(f"  Season: {session['season']}  |  Model: claude-opus-4-6")
    print("=" * 60)
    print("\nDiscovering your Yahoo leagues...")
    try:
        leagues = Yahoo.list_leagues(CREDS_FILE, season=session['season'])
        session['leagues'] = leagues
        print(f"Found {len(leagues)} league(s):\n")
        for _, row in leagues.iterrows():
            scoring   = row.get('scoring_method', '')
            teams     = row.get('num_teams', '')
            team_name = row.get('team_name', '')
            print(f"  [{row['league_id']}]  {row['name']}  —  your team: {team_name}  ({scoring}, {teams} teams)")
        print()
    except Exception as e:
        print(f"Warning: Could not auto-discover leagues ({e}). You can still ask by league ID.\n")


def main() -> None:
    env = load_env()
    api_key = env.get("Anthropic_API_Key") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: Anthropic_API_Key not found in .env and ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    init_session()
    chat_loop(client)


if __name__ == "__main__":
    main()
