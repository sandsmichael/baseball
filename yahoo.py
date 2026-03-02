"""
Yahoo Fantasy Baseball API client.

One-time setup
--------------
1. Create a Yahoo Developer app at https://developer.yahoo.com/apps/create/
      App type:     Installed Application
      Callback URI: oob
      Permissions:  Fantasy Sports (Read/Write)

2. Create yahoo_oauth.json in this directory:
      {"consumer_key": "YOUR_CLIENT_ID", "consumer_secret": "YOUR_CLIENT_SECRET"}

3. On first run Yahoo will print an authorization URL.  Open it, approve access,
   then paste the verification code back at the prompt.  Tokens are saved to
   yahoo_oauth.json and auto-refreshed on every subsequent run.

Usage
-----
    from yahoo import Yahoo

    yf = Yahoo(league_id='12345').fetch()

    # Read
    print(yf.roster)
    print(yf.standings)
    print(yf.matchup)
    print(yf.free_agents(position='SP'))

    # Transactions
    yf.add('Pete Alonso')
    yf.add('Pete Alonso', drop='Nathaniel Lowe')
    yf.drop('Nathaniel Lowe')
    yf.trade(give=['Player A'], receive=['Player B', 'Player C'], team='Rival Team')

    # Lineup
    yf.bench('Cody Bellinger')
    yf.start('Cody Bellinger')
    yf.move('Jacob deGrom', 'IL')
    yf.swap('Aaron Judge', 'Bench Guy')   # swaps their slots
"""

import textwrap
from datetime import date
from urllib.parse import quote_plus

import pandas as pd
import requests as _requests
from yahoo_oauth import OAuth2

BASE = 'https://fantasysports.yahooapis.com/fantasy/v2'
MLB_CODE = 'mlb'

# Slots that count as inactive (bench / injured list variants)
_BENCH_SLOTS = {'BN', 'IL', 'IL+', 'NA', 'IR', 'DL'}


class Yahoo:
    """
    Yahoo Fantasy Baseball client.

    Args:
        league_id:  Numeric league ID from the Yahoo URL
                    (e.g. '12345' from baseball.fantasysports.yahoo.com/b1/12345).
        season:     Season year.  Defaults to current calendar year.
        creds_file: Path to yahoo_oauth.json credentials file.
    """

    def __init__(
        self,
        league_id: str,
        season: int = None,
        creds_file: str = 'yahoo_oauth.json',
    ):
        self.league_id = str(league_id)
        self.season = season or date.today().year
        self._oauth = OAuth2(None, None, from_file=creds_file)
        self._league_key: str | None = None
        self._team_key: str | None = None
        self._fetched = False

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _get(self, path: str) -> dict:
        self._refresh()
        resp = self._oauth.session.get(f'{BASE}{path}?format=json')
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, xml: str) -> dict:
        self._refresh()
        resp = self._oauth.session.post(
            f'{BASE}{path}?format=json',
            data=xml.encode(),
            headers={'Content-Type': 'application/xml'},
        )
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, xml: str) -> dict:
        self._refresh()
        resp = self._oauth.session.put(
            f'{BASE}{path}?format=json',
            data=xml.encode(),
            headers={'Content-Type': 'application/xml'},
        )
        resp.raise_for_status()
        return resp.json()

    def _refresh(self):
        if not self._oauth.token_is_valid():
            self._oauth.refresh_access_token()

    # ── JSON parsing helpers ──────────────────────────────────────────────────

    @staticmethod
    def _flat(data) -> dict:
        """
        Collapse Yahoo's list-of-single-key-dicts into one flat dict.
        Also accepts a plain dict (pass-through) for endpoints that skip the pattern.
        """
        if isinstance(data, dict):
            return data
        out = {}
        for item in data:
            if isinstance(item, dict):
                out.update(item)
        return out

    @staticmethod
    def _name(val) -> str:
        if isinstance(val, dict):
            return val.get('full') or (
                f"{val.get('first', '')} {val.get('last', '')}".strip()
            )
        return str(val)

    @staticmethod
    def _eligible(ep) -> list[str]:
        """Normalize eligible_positions to a plain list of position strings."""
        if isinstance(ep, list):
            return [x for x in ep if isinstance(x, str)]
        if isinstance(ep, dict):
            p = ep.get('position', [])
            return [p] if isinstance(p, str) else list(p)
        return []

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def _resolve(self):
        # Game key for the target season
        data = self._get(f'/games;game_codes={MLB_CODE};seasons={self.season}')
        game_key = data['fantasy_content']['games']['0']['game'][0]['game_key']
        self._league_key = f'{game_key}.l.{self.league_id}'

        # Find our team in the league
        data = self._get(f'/league/{self._league_key}/teams')
        teams = data['fantasy_content']['league'][1]['teams']
        for i in range(teams['count']):
            flat = self._flat(teams[str(i)]['team'][0])
            if flat.get('is_owned_by_current_login') == 1:
                self._team_key = flat['team_key']
                return

        raise RuntimeError(
            f"No team owned by you found in league {self.league_id}. "
            "Check that league_id is correct and you have authorized this app."
        )

    def fetch(self) -> 'Yahoo':
        """Authenticate and resolve league/team keys. Returns self for chaining."""
        self._resolve()
        self._fetched = True
        return self

    def _require(self):
        if not self._fetched:
            self.fetch()

    # ── Player / team lookup ──────────────────────────────────────────────────

    def _find_player(self, name: str) -> tuple[str, str]:
        """
        League-wide player search by name.
        Returns (player_key, full_name).  Raises ValueError if not found.
        """
        self._require()
        data = self._get(
            f'/league/{self._league_key}/players;search={quote_plus(name)}'
        )
        players = data['fantasy_content']['league'][1]['players']
        if not players.get('count', 0):
            raise ValueError(f'Player not found: {name!r}')
        flat = self._flat(players['0']['player'][0])
        return flat['player_key'], self._name(flat.get('name', name))

    def _find_team(self, name: str) -> str:
        """Return team_key for the first league team whose name contains `name`."""
        self._require()
        data = self._get(f'/league/{self._league_key}/teams')
        teams = data['fantasy_content']['league'][1]['teams']
        for i in range(teams['count']):
            flat = self._flat(teams[str(i)]['team'][0])
            if name.lower() in flat.get('name', '').lower():
                return flat['team_key']
        raise ValueError(f'Team not found: {name!r}')

    def _roster_slot(self, name: str) -> tuple[str, str, list[str]]:
        """
        Find a player on your current roster by name.
        Returns (player_key, current_slot, eligible_positions).
        Raises ValueError if the player is not on your roster.
        """
        self._require()
        data = self._get(
            f'/team/{self._team_key}/roster;date={date.today().isoformat()}'
        )
        players = data['fantasy_content']['team'][1]['roster']['0']['players']
        name_lower = name.lower()
        for i in range(players['count']):
            p = players[str(i)]['player']
            flat = self._flat(p[0])
            full = self._name(flat.get('name', ''))
            if name_lower in full.lower():
                pos_flat = self._flat(p[1].get('selected_position', []))
                eligibles = self._eligible(flat.get('eligible_positions', {}))
                return flat['player_key'], pos_flat.get('position', ''), eligibles
        raise ValueError(f'{name!r} is not on your roster')

    # ── Read properties ───────────────────────────────────────────────────────

    @property
    def roster(self) -> pd.DataFrame:
        """Your current roster sorted by slot."""
        self._require()
        data = self._get(
            f'/team/{self._team_key}/roster;date={date.today().isoformat()}'
        )
        players = data['fantasy_content']['team'][1]['roster']['0']['players']
        rows = []
        for i in range(players['count']):
            p = players[str(i)]['player']
            flat = self._flat(p[0])
            pos_flat = self._flat(p[1].get('selected_position', []))
            rows.append({
                'slot':       pos_flat.get('position', ''),
                'name':       self._name(flat.get('name', '')),
                'team':       flat.get('editorial_team_abbr', ''),
                'positions':  flat.get('display_position', ''),
                'status':     flat.get('status', ''),
                'player_key': flat.get('player_key', ''),
            })
        return (
            pd.DataFrame(rows)
            .sort_values('slot')
            .reset_index(drop=True)
            [['slot', 'name', 'team', 'positions', 'status', 'player_key']]
        )

    @property
    def standings(self) -> pd.DataFrame:
        """Current league standings."""
        self._require()
        data = self._get(f'/league/{self._league_key}/standings')
        teams = data['fantasy_content']['league'][1]['standings'][0]['teams']
        rows = []
        for i in range(teams['count']):
            t = teams[str(i)]['team']
            flat = self._flat(t[0])
            s = t[2].get('team_standings', {})
            ot = s.get('outcome_totals', {})

            def _int(v, default=0):
                try: return int(v)
                except (TypeError, ValueError): return default

            def _float(v, default=0.0):
                try: return float(v)
                except (TypeError, ValueError): return default

            rows.append({
                'rank':   _int(s.get('rank'), i + 1),
                'team':   flat.get('name', ''),
                'wins':   _int(ot.get('wins')),
                'losses': _int(ot.get('losses')),
                'ties':   _int(ot.get('ties')),
                'pct':    _float(ot.get('percentage')),
                'gb':     s.get('games_back', '-'),
            })
        return pd.DataFrame(rows).sort_values('rank').reset_index(drop=True)

    @property
    def matchup(self) -> dict:
        """Your current week's matchup info."""
        self._require()
        data = self._get(f'/team/{self._team_key}/matchups')
        matchups = data['fantasy_content']['team'][1]['matchups']
        for i in range(matchups['count']):
            m = matchups[str(i)]['matchup']
            # 'midevent' = current week; also accept first non-past matchup
            if m.get('status') in ('midevent', 'preevent'):
                t = m['0']['teams']
                result = {
                    'week':  m.get('week'),
                    'start': m.get('week_start'),
                    'end':   m.get('week_end'),
                }
                for j in range(2):
                    flat = self._flat(t[str(j)]['team'][0])
                    if flat.get('team_key') == self._team_key:
                        result['you'] = flat.get('name', '')
                    else:
                        result['opponent'] = flat.get('name', '')
                        result['opponent_key'] = flat.get('team_key', '')
                return result
        return {}

    @property
    def opponent_roster(self) -> pd.DataFrame:
        """Roster of your current week's opponent."""
        self._require()
        m = self.matchup
        opp_key = m.get('opponent_key', '')
        if not opp_key:
            return pd.DataFrame(columns=['slot', 'name', 'team', 'positions', 'status', 'player_key'])
        data = self._get(f'/team/{opp_key}/roster;date={date.today().isoformat()}')
        players = data['fantasy_content']['team'][1]['roster']['0']['players']
        rows = []
        for i in range(players['count']):
            p = players[str(i)]['player']
            flat = self._flat(p[0])
            pos_flat = self._flat(p[1].get('selected_position', []))
            rows.append({
                'slot':       pos_flat.get('position', ''),
                'name':       self._name(flat.get('name', '')),
                'team':       flat.get('editorial_team_abbr', ''),
                'positions':  flat.get('display_position', ''),
                'status':     flat.get('status', ''),
                'player_key': flat.get('player_key', ''),
            })
        return (
            pd.DataFrame(rows)
            .sort_values('slot')
            .reset_index(drop=True)
            [['slot', 'name', 'team', 'positions', 'status', 'player_key']]
        )

    def _fetch_all_players(self, status: str, position: str = None) -> pd.DataFrame:
        """Paginate through all players with a given status (FA or W)."""
        pos = f';position={position}' if position else ''
        frames, start, per_page = [], 0, 25
        while True:
            data = self._get(
                f'/league/{self._league_key}/players'
                f';status={status}{pos};count={per_page};start={start};sort=AR'
            )
            df = self._parse_players(data)
            frames.append(df)
            if len(df) < per_page:
                break
            start += per_page
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
            columns=['name', 'team', 'positions', 'status', 'player_key']
        )

    def free_agents(self, position: str = None, count: int = None) -> pd.DataFrame:
        """
        Available free agents ranked by average draft position.
        Pass count=N to limit results; omit (or None) to fetch all.

            yf.free_agents()
            yf.free_agents(position='SP', count=10)
        """
        self._require()
        if count is None:
            return self._fetch_all_players('FA', position)
        pos = f';position={position}' if position else ''
        data = self._get(
            f'/league/{self._league_key}/players;status=FA{pos};count={count};sort=AR'
        )
        return self._parse_players(data)

    def waivers(self, position: str = None, count: int = None) -> pd.DataFrame:
        """
        Players currently on waivers.
        Pass count=N to limit results; omit (or None) to fetch all.

            yf.waivers()
            yf.waivers(position='OF')
        """
        self._require()
        if count is None:
            return self._fetch_all_players('W', position)
        pos = f';position={position}' if position else ''
        data = self._get(
            f'/league/{self._league_key}/players;status=W{pos};count={count};sort=AR'
        )
        return self._parse_players(data)

    def search(self, name: str) -> pd.DataFrame:
        """
        Search all players (any ownership status) by name.

            yf.search('Pete Alonso')
        """
        self._require()
        data = self._get(
            f'/league/{self._league_key}/players;search={quote_plus(name)}'
        )
        return self._parse_players(data)

    def _parse_players(self, data: dict) -> pd.DataFrame:
        """Shared parser for league-level player list responses."""
        players = data['fantasy_content']['league'][1]['players']
        if not isinstance(players, dict):  # API returns [] when no results
            return pd.DataFrame(columns=['name', 'team', 'positions', 'status', 'player_key'])
        rows = []
        for i in range(players.get('count', 0)):
            flat = self._flat(players[str(i)]['player'][0])
            rows.append({
                'name':       self._name(flat.get('name', '')),
                'team':       flat.get('editorial_team_abbr', ''),
                'positions':  flat.get('display_position', ''),
                'status':     flat.get('status', ''),
                'player_key': flat.get('player_key', ''),
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=['name', 'team', 'positions', 'status', 'player_key']
        )

    # ── Transactions ──────────────────────────────────────────────────────────

    def add(self, player: str, *, drop: str = None, faab: int = None) -> None:
        """
        Add a free agent or waiver player to your roster.

        Args:
            player: Player name to add.
            drop:   Player on your roster to simultaneously drop.
            faab:   FAAB bid amount (for FAAB leagues; omit for waiver-priority leagues).

        Examples:
            yf.add('Pete Alonso')
            yf.add('Pete Alonso', drop='Nathaniel Lowe')
            yf.add('Pete Alonso', drop='Nathaniel Lowe', faab=15)
        """
        self._require()
        add_key, add_name = self._find_player(player)

        faab_xml = f'    <faab_bid>{faab}</faab_bid>\n' if faab is not None else ''

        if drop is not None:
            drop_key, _, _ = self._roster_slot(drop)
            xml = textwrap.dedent(f"""\
                <?xml version="1.0"?>
                <fantasy_content>
                  <transaction>
                    <type>add/drop</type>
                {faab_xml}    <players>
                      <player>
                        <player_key>{add_key}</player_key>
                        <transaction_data>
                          <type>add</type>
                          <destination_team_key>{self._team_key}</destination_team_key>
                        </transaction_data>
                      </player>
                      <player>
                        <player_key>{drop_key}</player_key>
                        <transaction_data>
                          <type>drop</type>
                          <source_team_key>{self._team_key}</source_team_key>
                        </transaction_data>
                      </player>
                    </players>
                  </transaction>
                </fantasy_content>""")
            self._post(f'/league/{self._league_key}/transactions', xml)
            print(f'Added {add_name}, dropped {drop}')
        else:
            xml = textwrap.dedent(f"""\
                <?xml version="1.0"?>
                <fantasy_content>
                  <transaction>
                    <type>add</type>
                {faab_xml}    <player>
                      <player_key>{add_key}</player_key>
                      <transaction_data>
                        <type>add</type>
                        <destination_team_key>{self._team_key}</destination_team_key>
                      </transaction_data>
                    </player>
                  </transaction>
                </fantasy_content>""")
            self._post(f'/league/{self._league_key}/transactions', xml)
            print(f'Added {add_name}')

    def drop(self, player: str) -> None:
        """
        Drop a player from your roster.

            yf.drop('Nathaniel Lowe')
        """
        self._require()
        key, _, _ = self._roster_slot(player)
        xml = textwrap.dedent(f"""\
            <?xml version="1.0"?>
            <fantasy_content>
              <transaction>
                <type>drop</type>
                <player>
                  <player_key>{key}</player_key>
                  <transaction_data>
                    <type>drop</type>
                    <source_team_key>{self._team_key}</source_team_key>
                  </transaction_data>
                </player>
              </transaction>
            </fantasy_content>""")
        self._post(f'/league/{self._league_key}/transactions', xml)
        print(f'Dropped {player}')

    def trade(self, give: list[str], receive: list[str], team: str) -> None:
        """
        Propose a trade to another team.

        Args:
            give:    Players from your roster to send.
            receive: Players from the other team to receive.
            team:    Opponent team name (case-insensitive substring match).

        Example:
            yf.trade(
                give=['Aaron Judge'],
                receive=['Julio Rodriguez', 'Gerrit Cole'],
                team='Rival Squad',
            )
        """
        self._require()
        their_key = self._find_team(team)

        give_keys    = [self._roster_slot(p)[0] for p in give]
        receive_keys = [self._find_player(p)[0] for p in receive]

        blocks = []
        for k in give_keys:
            blocks.append(textwrap.dedent(f"""\
                      <player>
                        <player_key>{k}</player_key>
                        <transaction_data>
                          <type>pending_trade</type>
                          <source_team_key>{self._team_key}</source_team_key>
                          <destination_team_key>{their_key}</destination_team_key>
                        </transaction_data>
                      </player>"""))
        for k in receive_keys:
            blocks.append(textwrap.dedent(f"""\
                      <player>
                        <player_key>{k}</player_key>
                        <transaction_data>
                          <type>pending_trade</type>
                          <source_team_key>{their_key}</source_team_key>
                          <destination_team_key>{self._team_key}</destination_team_key>
                        </transaction_data>
                      </player>"""))

        xml = textwrap.dedent(f"""\
            <?xml version="1.0"?>
            <fantasy_content>
              <transaction>
                <type>pending_trade</type>
                <trader_team_key>{self._team_key}</trader_team_key>
                <tradee_team_key>{their_key}</tradee_team_key>
                <players>
            {chr(10).join(blocks)}
                </players>
              </transaction>
            </fantasy_content>""")
        self._post(f'/league/{self._league_key}/transactions', xml)
        print(f'Trade proposed to {team}: {give} → them | {receive} → you')

    # ── Lineup management ─────────────────────────────────────────────────────

    def _lineup_xml(self, moves: list[tuple[str, str]], for_date: str) -> str:
        """Build the PUT /roster XML payload for one or more position changes."""
        player_blocks = '\n'.join(
            f'      <player>\n'
            f'        <player_key>{k}</player_key>\n'
            f'        <position>{p}</position>\n'
            f'      </player>'
            for k, p in moves
        )
        return textwrap.dedent(f"""\
            <?xml version="1.0"?>
            <fantasy_content>
              <roster>
                <coverage_type>date</coverage_type>
                <date>{for_date}</date>
                <players>
            {player_blocks}
                </players>
              </roster>
            </fantasy_content>""")

    def move(self, player: str, position: str, for_date: str = None) -> None:
        """
        Move a player to a specific roster slot.

        Common positions: 'C', '1B', '2B', '3B', 'SS', 'OF', 'Util', 'SP', 'RP',
                          'P', 'BN', 'IL', 'IL+'

        Examples:
            yf.move('Aaron Judge', 'OF')
            yf.move('Aaron Judge', 'BN')
            yf.move('Jacob deGrom', 'IL')
        """
        self._require()
        key, _, _ = self._roster_slot(player)
        d = for_date or date.today().isoformat()
        self._put(f'/team/{self._team_key}/roster', self._lineup_xml([(key, position)], d))
        print(f'Moved {player} → {position}')

    def bench(self, player: str, for_date: str = None) -> None:
        """
        Move a player to the bench (BN).

            yf.bench('Cody Bellinger')
        """
        self.move(player, 'BN', for_date)

    def il(self, player: str, for_date: str = None) -> None:
        """
        Move a player to the IL slot.

            yf.il('Jacob deGrom')
        """
        self.move(player, 'IL', for_date)

    def start(self, player: str, for_date: str = None) -> None:
        """
        Move a player from BN/IL to the first available eligible active slot.

        Tries each of the player's eligible positions in order.  Raises ValueError
        if the player is already active or no eligible slot is available (use
        swap() to displace another player, or move() to target a specific slot).

            yf.start('Pete Alonso')
        """
        self._require()
        d = for_date or date.today().isoformat()
        key, current_slot, eligibles = self._roster_slot(player)

        if current_slot not in _BENCH_SLOTS:
            print(f'{player} is already active at {current_slot}')
            return

        active_eligibles = [p for p in eligibles if p not in _BENCH_SLOTS]
        if not active_eligibles:
            raise ValueError(
                f'{player!r} has no active eligible positions (only: {eligibles})'
            )

        last_err = None
        for pos in active_eligibles:
            try:
                self._put(
                    f'/team/{self._team_key}/roster',
                    self._lineup_xml([(key, pos)], d),
                )
                print(f'Started {player} at {pos}')
                return
            except _requests.exceptions.HTTPError as exc:
                last_err = exc
                continue

        raise ValueError(
            f'No open active slot for {player!r} (tried: {active_eligibles}). '
            f'Use swap() to displace a bench player, or move() to pick a slot.\n'
            f'Last API error: {last_err}'
        )

    def swap(self, player1: str, player2: str, for_date: str = None) -> None:
        """
        Swap two players' roster slots.  Useful to bench one player and
        start another in a single API call.

            yf.swap('Aaron Judge', 'Bench Guy')      # Judge → BN, Bench Guy → OF
            yf.swap('Starter', 'IL Player')          # move starter to IL slot
        """
        self._require()
        d = for_date or date.today().isoformat()
        key1, slot1, _ = self._roster_slot(player1)
        key2, slot2, _ = self._roster_slot(player2)
        if slot1 == slot2:
            print(f'Both players are already in the same slot ({slot1}) — no change.')
            return
        self._put(
            f'/team/{self._team_key}/roster',
            self._lineup_xml([(key1, slot2), (key2, slot1)], d),
        )
        print(f'Swapped: {player1} ({slot1} → {slot2}), {player2} ({slot2} → {slot1})')

    # ── Dunder ────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        if self._fetched:
            return f'Yahoo(league={self._league_key}, team={self._team_key})'
        return f'Yahoo(league_id={self.league_id!r}, season={self.season}, not fetched)'
