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

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import textwrap
import threading
import time
import unicodedata
from datetime import date
from urllib.parse import quote_plus, urlencode

import pandas as pd
import requests as _requests
from yahoo_oauth import OAuth2

BASE = 'https://fantasysports.yahooapis.com/fantasy/v2'
_FANTASY_BASE = 'https://baseball.fantasysports.yahoo.com/b1'
_BROWSER_STATE = 'browser/yahoo_browser_state.json'
_BROWSER_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/122.0.0.0 Safari/537.36'
)
MLB_CODE = 'mlb'

# Slots that count as inactive (bench / injured list variants)
_BENCH_SLOTS = {'BN', 'IL', 'IL+', 'NA', 'IR', 'DL'}


# ── Module-level OAuth helpers ─────────────────────────────────────────────────

def load_env(path: str = '.env') -> dict:
    """Parse .env file (Key: "Value" format) and return as dict."""
    out = {}
    with open(path) as f:
        for line in f:
            m = re.match(r'([\w]+):\s*"?([^"\n]+)"?', line.strip())
            if m:
                out[m.group(1)] = m.group(2).strip()
    return out


def _has_refresh_token(creds_file: str) -> bool:
    """Return True if creds_file contains a non-empty refresh_token."""
    if not os.path.exists(creds_file):
        return False
    with open(creds_file) as f:
        data = json.load(f)
    return bool(data.get('refresh_token'))


def _is_2fa_page(url: str) -> bool:
    """Return True only for 2FA challenge pages (not the password-entry page)."""
    return 'challenge-selector' in url or 'challenge/verify' in url


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE OAuth flow."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return code_verifier, code_challenge


def _get_oauth_code(consumer_key: str, email: str, password: str) -> tuple[str, str]:
    """
    Launch Playwright in a background thread to complete Yahoo OAuth flow.
    Tries saved browser state (headless) first; falls back to visible browser for 2FA.
    Returns (auth_code, code_verifier) for PKCE token exchange.
    """
    state_file = 'browser/yahoo_browser_state.json'
    code_verifier, code_challenge = _pkce_pair()
    auth_url = 'https://api.login.yahoo.com/oauth2/request_auth?' + urlencode({
        'client_id':             consumer_key,
        'redirect_uri':          'https://localhost',
        'response_type':         'code',
        'code_challenge':        code_challenge,
        'code_challenge_method': 'S256',
    })
    result: dict = {'verifier': None, 'error': None}

    def _task():
        asyncio.set_event_loop(asyncio.new_event_loop())
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                configs = []
                if os.path.exists(state_file):
                    configs.append({'headless': True,  'state': state_file})
                configs.append({'headless': False, 'state': None})

                for cfg in configs:
                    print(f'  Browser: headless={cfg["headless"]}  '
                          f'saved_state={cfg["state"] is not None}')
                    browser = pw.chromium.launch(
                        headless=cfg['headless'],
                        args=['--disable-blink-features=AutomationControlled'],
                    )
                    ctx = browser.new_context(
                        storage_state=cfg['state'],
                        user_agent=(
                            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                            'AppleWebKit/537.36 (KHTML, like Gecko) '
                            'Chrome/122.0.0.0 Safari/537.36'
                        ),
                        locale='en-US',
                    )
                    page = ctx.new_page()

                    try:
                        # Capture auth code from the https://localhost redirect URL
                        code_holder: dict = {}

                        def _on_request(request):
                            from urllib.parse import urlparse, parse_qs
                            url = request.url
                            if 'localhost' in url and 'code=' in url:
                                params = parse_qs(urlparse(url).query)
                                code = params.get('code', [None])[0]
                                if code:
                                    code_holder['code'] = code

                        def _on_nav(frame):
                            from urllib.parse import urlparse, parse_qs
                            url = frame.url
                            if 'localhost' in url and 'code=' in url:
                                params = parse_qs(urlparse(url).query)
                                code = params.get('code', [None])[0]
                                if code:
                                    code_holder['code'] = code

                        page.on('request', _on_request)
                        page.on('framenavigated', _on_nav)

                        page.goto(auth_url, wait_until='domcontentloaded', timeout=30000)
                        page.wait_for_timeout(2000)
                        print(f'  Page URL after goto: {page.url}')

                        # ── Email ──────────────────────────────────────────────
                        email_sel = None
                        for sel in ['#login-username', 'input[name="username"]',
                                    'input[type="email"]', 'input[name="login"]']:
                            try:
                                page.wait_for_selector(sel, timeout=3000)
                                email_sel = sel
                                break
                            except Exception:
                                pass

                        if email_sel:
                            print(f'  Found email field: {email_sel}')
                            page.fill(email_sel, email)
                            page.keyboard.press('Enter')
                            page.wait_for_url(
                                lambda u: 'challenge/password' in u or 'consent' in u or _is_2fa_page(u),
                                timeout=15000,
                            )
                            page.wait_for_timeout(1500)
                        else:
                            print(f'  No email field found, current URL: {page.url}')

                        # ── Password ───────────────────────────────────────────
                        passwd_sel = None
                        for sel in ['#login-passwd', 'input[name="passwd"]',
                                    'input[type="password"]', 'input[name="password"]']:
                            try:
                                page.wait_for_selector(sel, timeout=3000)
                                passwd_sel = sel
                                break
                            except Exception:
                                pass

                        if passwd_sel:
                            print(f'  Found password field: {passwd_sel}')
                            page.fill(passwd_sel, password)
                            page.keyboard.press('Enter')
                            try:
                                page.wait_for_url(
                                    lambda u: 'challenge/password' not in u,
                                    timeout=15000,
                                )
                            except Exception as nav_err:
                                # ERR_CONNECTION_REFUSED means Yahoo redirected straight
                                # to https://localhost — code captured by _on_request
                                if 'ERR_CONNECTION' not in str(nav_err):
                                    raise
                                print('  Redirected directly to localhost (connection refused — expected)')
                            page.wait_for_timeout(1000)
                            if code_holder.get('code'):
                                print('  Code captured from redirect.')
                        else:
                            print(f'  No password field found, current URL: {page.url}')

                        # ── 2FA challenge ──────────────────────────────────────
                        if _is_2fa_page(page.url):
                            if cfg['headless']:
                                print('  Headless hit 2FA — retrying with visible browser')
                                browser.close()
                                continue

                            iphone_btn = page.query_selector('button[name="index"][value="1"]')
                            if iphone_btn:
                                iphone_btn.click()
                                print('  iPhone push sent — approve on your device...')
                            else:
                                print('  2FA required — complete it in the browser window...')

                            for _ in range(300):
                                if not _is_2fa_page(page.url):
                                    break
                                time.sleep(1)
                            else:
                                raise RuntimeError('2FA timed out after 5 minutes')
                            print('  2FA cleared')

                        # ── Consent (Agree button starts disabled) ─────────────
                        if 'consent' in page.url or 'authorize' in page.url:
                            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                            page.wait_for_timeout(1500)
                            page.evaluate("""() => {
                                const b = document.querySelector('button[name="agree"]')
                                       || document.querySelector('input[name="agree"]')
                                       || document.querySelector('[value="agree"]');
                                if (b) { b.removeAttribute('disabled'); b.click(); }
                            }""")
                            page.wait_for_timeout(3000)

                        # ── Wait for localhost redirect (code intercepted via route) ──
                        print(f'  Waiting for localhost redirect. Current URL: {page.url}')
                        deadline = time.time() + 15
                        while time.time() < deadline:
                            if 'code' in code_holder:
                                break
                            page.wait_for_timeout(500)
                        verifier = code_holder.get('code')

                        if verifier:
                            ctx.storage_state(path=state_file)
                            result['verifier'] = verifier
                            browser.close()
                            return
                        else:
                            page.screenshot(path='browser/yahoo_auth_debug.png')
                            raise RuntimeError(
                                'Could not extract OAuth code — '
                                'screenshot saved to browser/yahoo_auth_debug.png'
                            )

                    except Exception as inner_e:
                        if cfg['headless']:
                            print(f'  Headless failed: {inner_e}')
                            try:
                                browser.close()
                            except Exception:
                                pass
                            continue
                        raise
                    finally:
                        if not result['verifier']:
                            try:
                                browser.close()
                            except Exception:
                                pass

        except Exception as e:
            import traceback
            traceback.print_exc()
            result['error'] = e

    t = threading.Thread(target=_task, daemon=True)
    t.start()
    t.join(timeout=400)

    if t.is_alive():
        raise RuntimeError('Auth timed out after 400 seconds')
    if result['error']:
        raise result['error']
    return result['verifier'], code_verifier


def _yahoo_auto_auth(
    consumer_key: str,
    email: str,
    password: str,
    creds_file: str,
) -> None:
    """Run browser OAuth (PKCE) and save tokens to creds_file."""
    print('Launching browser for Yahoo OAuth...')
    auth_code, code_verifier = _get_oauth_code(consumer_key, email, password)
    print('Authorization code obtained.')

    resp = _requests.post(
        'https://api.login.yahoo.com/oauth2/get_token',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'grant_type':    'authorization_code',
            'code':          auth_code,
            'redirect_uri':  'https://localhost',
            'client_id':     consumer_key,
            'code_verifier': code_verifier,
        },
        timeout=30,
    )
    resp.raise_for_status()
    tokens = resp.json()

    with open(creds_file) as f:
        existing = json.load(f)
    existing.update({
        'access_token':      tokens['access_token'],
        'refresh_token':     tokens.get('refresh_token', ''),
        'token_type':        tokens.get('token_type', 'bearer'),
        'token_expires_in':  tokens.get('expires_in', 3600),
        'token_time':        time.time(),
        'xoauth_yahoo_guid': tokens.get('xoauth_yahoo_guid', ''),
    })
    with open(creds_file, 'w') as f:
        json.dump(existing, f, indent=2)
    print(f'Tokens saved to {creds_file}.')


def init_auth(
    env_path: str = '.env',
    creds_file: str = 'browser/yahoo_oauth.json',
) -> str:
    """
    Full one-call setup: parse .env, write credentials, run OAuth if needed.

    On first run, opens a browser to complete Yahoo OAuth.
    On subsequent runs, reuses saved tokens — no browser needed.

    Args:
        env_path:   Path to .env file (Key: "Value" format).
        creds_file: Path where OAuth credentials/tokens are stored.

    Returns the creds_file path for passing to Yahoo() and Yahoo.list_leagues().
    """
    logging.getLogger('yahoo_oauth').setLevel(logging.WARNING)

    env = load_env(env_path)
    consumer_key    = env['Client_ID']
    consumer_secret = env.get('Client_Secret', '')
    email    = env.get('Yahoo_Email', '')
    password = env.get('Yahoo_Password', '')

    os.makedirs(os.path.dirname(creds_file) or '.', exist_ok=True)
    existing: dict = {}
    if os.path.exists(creds_file):
        with open(creds_file) as f:
            existing = json.load(f)
    existing['consumer_key'] = consumer_key
    if consumer_secret:
        existing['consumer_secret'] = consumer_secret
    with open(creds_file, 'w') as f:
        json.dump(existing, f, indent=2)

    has_token = 'access_token' in existing
    print(f'Credentials written to {creds_file} — '
          f'{"tokens present" if has_token else "no tokens yet"}')

    if _has_refresh_token(creds_file):
        print('Refresh token found — no browser needed.')
    else:
        _yahoo_auto_auth(consumer_key, email, password, creds_file)

    oauth = OAuth2(None, None, from_file=creds_file)
    if not oauth.token_is_valid():
        oauth.refresh_access_token()
    print('OAuth OK — session ready')
    return creds_file


def top_available_all_leagues(
    leagues_df: pd.DataFrame,
    creds_file: str,
    season: int = None,
    n: int = 3,
) -> pd.DataFrame:
    """
    Fetch top available batters and pitchers across all of the user's leagues.

    Args:
        leagues_df: DataFrame from Yahoo.list_leagues().
        creds_file: Path to yahoo_oauth.json.
        season:     Season year (defaults to current calendar year).
        n:          Number of top batters + pitchers to return per league.

    Returns:
        DataFrame with columns:
            league, my_team, type, rank, name, team, positions, status, pct_owned
    """
    _PITCHER_POS = {'SP', 'RP', 'P'}
    season = season or date.today().year

    def _is_pitcher(positions: str) -> bool:
        return bool(set(str(positions).split(',')) & _PITCHER_POS)

    def _parse_pct(p1) -> float:
        if not isinstance(p1, dict):
            return 0.0
        po = p1.get('percent_owned', [])
        if isinstance(po, list):
            flat: dict = {}
            for item in po:
                if isinstance(item, dict):
                    flat.update(item)
            return float(flat.get('value', 0))
        if isinstance(po, dict):
            return float(po.get('value', 0))
        return float(po)

    oauth = OAuth2(None, None, from_file=creds_file)
    if not oauth.token_is_valid():
        oauth.refresh_access_token()

    def _api_get(path: str) -> dict:
        if not oauth.token_is_valid():
            oauth.refresh_access_token()
        resp = oauth.session.get(f'{BASE}{path}?format=json')
        resp.raise_for_status()
        return resp.json()

    def _fetch_league(league_key: str) -> pd.DataFrame:
        data = _api_get(
            f'/league/{league_key}/players;status=W;count=100;out=percent_owned;sort=AR'
        )
        players = data['fantasy_content']['league'][1]['players']
        if not isinstance(players, dict):
            return pd.DataFrame(columns=['name', 'team', 'positions', 'status', 'pct_owned'])
        rows = []
        for i in range(players.get('count', 0)):
            p = players[str(i)]['player']
            flat = Yahoo._flat(p[0])
            name_raw = flat.get('name', '')
            name = name_raw.get('full', '') if isinstance(name_raw, dict) else str(name_raw)
            rows.append({
                'name':      name,
                'team':      flat.get('editorial_team_abbr', ''),
                'positions': flat.get('display_position', ''),
                'status':    flat.get('status', ''),
                'pct_owned': _parse_pct(p[1] if len(p) > 1 else {}),
            })
        return (
            pd.DataFrame(rows)
            .sort_values('pct_owned', ascending=False)
            .reset_index(drop=True)
        )

    results = []
    for _, row in leagues_df.iterrows():
        league_key  = row['league_key']
        league_name = row['name']
        team_name   = row['team_name']
        print(f'  {league_name}...')
        try:
            df = _fetch_league(league_key)
            batters  = df[~df['positions'].apply(_is_pitcher)].head(n)
            pitchers = df[ df['positions'].apply(_is_pitcher)].head(n)
            for rank, (_, p) in enumerate(batters.iterrows(),  1):
                results.append({'league': league_name, 'my_team': team_name,
                                'type': 'batter',  'rank': rank, **p})
            for rank, (_, p) in enumerate(pitchers.iterrows(), 1):
                results.append({'league': league_name, 'my_team': team_name,
                                'type': 'pitcher', 'rank': rank, **p})
        except Exception as e:
            print(f'    Error: {e}')

    if not results:
        return pd.DataFrame(
            columns=['league', 'my_team', 'type', 'rank', 'name', 'team', 'positions', 'status', 'pct_owned']
        )
    return (
        pd.DataFrame(results)
        [['league', 'my_team', 'type', 'rank', 'name', 'team', 'positions', 'status', 'pct_owned']]
    )


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
        league_id: str = None,
        season: int = None,
        creds_file: str = 'yahoo_oauth.json',
    ):
        self.league_id = str(league_id) if league_id is not None else None
        self.season = season or date.today().year
        self._oauth = OAuth2(None, None, from_file=creds_file)
        self._game_key: str | None = None
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

    # ── Playwright browser helpers (write operations) ─────────────────────────

    def _browser_write(self, fn, timeout: int = 120):
        """Run fn(page) in a Playwright browser using saved session state."""
        result: dict = {'value': None, 'error': None}

        def _task():
            asyncio.set_event_loop(asyncio.new_event_loop())
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(
                        headless=False,
                        args=['--disable-blink-features=AutomationControlled'],
                    )
                    state = _BROWSER_STATE if os.path.exists(_BROWSER_STATE) else None
                    ctx = browser.new_context(
                        storage_state=state,
                        user_agent=_BROWSER_UA,
                        locale='en-US',
                    )
                    page = ctx.new_page()
                    try:
                        self._pw_ensure_login(page)
                        result['value'] = fn(page)
                        ctx.storage_state(path=_BROWSER_STATE)
                    except Exception:
                        os.makedirs('browser', exist_ok=True)
                        page.screenshot(path='browser/yahoo_action_debug.png')
                        raise
                    finally:
                        browser.close()
            except Exception as e:
                import traceback
                traceback.print_exc()
                result['error'] = e

        t = threading.Thread(target=_task, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            raise RuntimeError(f'Browser action timed out after {timeout}s')
        if result['error']:
            raise result['error']
        return result['value']

    def _pw_ensure_login(self, page):
        """Navigate to the league page. Logs in with .env credentials if session expired."""
        env = load_env()
        email = env.get('Yahoo_Email', '')
        password = env.get('Yahoo_Password', '')

        page.goto(
            f'{_FANTASY_BASE}/{self.league_id}',
            wait_until='domcontentloaded',
            timeout=30000,
        )
        page.wait_for_timeout(2000)

        for sel in ['#login-username', 'input[name="username"]', 'input[type="email"]']:
            el = page.query_selector(sel)
            if el:
                el.fill(email)
                page.keyboard.press('Enter')
                page.wait_for_timeout(2000)
                break

        for sel in ['#login-passwd', 'input[name="passwd"]', 'input[type="password"]']:
            el = page.query_selector(sel)
            if el:
                el.fill(password)
                page.keyboard.press('Enter')
                page.wait_for_timeout(3000)
                break

        print(f'  Session: {page.url}')

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

    def _resolve_game_key(self):
        if self._game_key:
            return
        data = self._get(f'/games;game_codes={MLB_CODE};seasons={self.season}')
        self._game_key = data['fantasy_content']['games']['0']['game'][0]['game_key']

    def _resolve(self):
        # Game key for the target season
        self._resolve_game_key()
        self._league_key = f'{self._game_key}.l.{self.league_id}'

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
        Add a free agent or waiver player to your roster via browser automation.

        Args:
            player: Player name to add.
            drop:   Player on your roster to simultaneously drop.
            faab:   Ignored (FAAB bids not supported via browser automation).

        Examples:
            yf.add('Pete Alonso')
            yf.add('Pete Alonso', drop='Nathaniel Lowe')
        """
        self._require()
        add_key, add_name = self._find_player(player)
        add_id = add_key.split('.')[-1]
        drop_key = drop_id = drop_name = None
        if drop is not None:
            drop_key, _, _ = self._roster_slot(drop)
            drop_id = drop_key.split('.')[-1]
            drop_name = drop

        def _do_add(page):
            url = f'{_FANTASY_BASE}/{self.league_id}/addplayer?apid={add_id}'
            if drop_id:
                url += f'&spid={drop_id}'
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)

            # Click the primary Add button
            for sel in [
                'button:has-text("Add")', 'a:has-text("Add")',
                'input[value="Add Player"]', '[data-action="add"]',
            ]:
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    page.wait_for_timeout(2000)
                    break

            # Confirm if a dialog appears
            for sel in [
                'button:has-text("Add Player")', 'button:has-text("Confirm")',
                'button:has-text("Submit")', 'input[value="Confirm"]',
            ]:
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    page.wait_for_timeout(2000)
                    break

            msg = f'Added {add_name}'
            if drop_name:
                msg += f', dropped {drop_name}'
            print(msg)

        self._browser_write(_do_add)

    def drop(self, player: str) -> None:
        """
        Drop a player from your roster via browser automation.

            yf.drop('Nathaniel Lowe')
        """
        self._require()
        key, _, _ = self._roster_slot(player)
        player_id = key.split('.')[-1]

        def _do_drop(page):
            url = f'{_FANTASY_BASE}/{self.league_id}/addplayer?apid=&spid={player_id}'
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)

            for sel in [
                'button:has-text("Drop")', 'a:has-text("Drop Player")',
                'input[value="Drop Player"]', '[data-action="drop"]',
            ]:
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    page.wait_for_timeout(2000)
                    break

            for sel in [
                'button:has-text("Confirm")', 'button:has-text("Submit")',
                'input[value="Confirm"]',
            ]:
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    page.wait_for_timeout(2000)
                    break

            print(f'Dropped {player}')

        self._browser_write(_do_drop)

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
        Move a player to a specific roster slot via browser automation.

        Common positions: 'C', '1B', '2B', '3B', 'SS', 'OF', 'Util', 'SP', 'RP',
                          'P', 'BN', 'IL', 'IL+'

        Examples:
            yf.move('Aaron Judge', 'OF')
            yf.move('Aaron Judge', 'BN')
            yf.move('Jacob deGrom', 'IL')
        """
        self._require()
        key, _, _ = self._roster_slot(player)
        player_id = key.split('.')[-1]
        team_num = self._team_key.split('.')[-1]

        def _do_move(page):
            url = f'{_FANTASY_BASE}/{self.league_id}/{team_num}'
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)

            result = page.evaluate(f"""() => {{
                var sel = document.querySelector('select[name="{player_id}"]');
                if (!sel) return 'select_not_found';
                var opts = Array.from(sel.options).map(o => o.value);
                if (!opts.includes('{position}')) return 'invalid_position:' + opts.join(',');
                sel.value = '{position}';
                var form = document.getElementById('roster-edit-form');
                if (!form) return 'form_not_found';
                form.submit();
                return 'ok';
            }}""")
            if result != 'ok':
                raise RuntimeError(
                    f'Move {player!r} → {position!r} failed: {result}'
                )
            try:
                page.wait_for_load_state('domcontentloaded', timeout=15000)
            except Exception:
                pass
            print(f'Moved {player} → {position}')

        self._browser_write(_do_move)

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

        for pos in active_eligibles:
            try:
                self.move(player, pos, for_date)
                print(f'Started {player} at {pos}')
                return
            except Exception:
                continue

        raise ValueError(
            f'No open active slot for {player!r} (tried: {active_eligibles}). '
            f'Use swap() to displace a bench player, or move() to pick a slot.'
        )

    def swap(self, player1: str, player2: str, for_date: str = None) -> None:
        """
        Swap two players' roster slots via browser automation.

            yf.swap('Aaron Judge', 'Bench Guy')      # Judge → BN, Bench Guy → OF
            yf.swap('Starter', 'IL Player')          # move starter to IL slot
        """
        self._require()
        key1, slot1, _ = self._roster_slot(player1)
        key2, slot2, _ = self._roster_slot(player2)
        if slot1 == slot2:
            print(f'Both players are already in the same slot ({slot1}) — no change.')
            return

        id1 = key1.split('.')[-1]
        id2 = key2.split('.')[-1]
        team_num = self._team_key.split('.')[-1]

        def _do_swap(page):
            url = f'{_FANTASY_BASE}/{self.league_id}/{team_num}'
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)

            result = page.evaluate(f"""() => {{
                var sel1 = document.querySelector('select[name="{id1}"]');
                var sel2 = document.querySelector('select[name="{id2}"]');
                if (!sel1) return 'not_found:{player1}';
                if (!sel2) return 'not_found:{player2}';
                var opts1 = Array.from(sel1.options).map(o => o.value);
                var opts2 = Array.from(sel2.options).map(o => o.value);
                if (!opts1.includes('{slot2}')) return 'invalid_slot:{slot2} for {player1}, valid:' + opts1.join(',');
                if (!opts2.includes('{slot1}')) return 'invalid_slot:{slot1} for {player2}, valid:' + opts2.join(',');
                sel1.value = '{slot2}';
                sel2.value = '{slot1}';
                var form = document.getElementById('roster-edit-form');
                if (!form) return 'form_not_found';
                form.submit();
                return 'ok';
            }}""")
            if result != 'ok':
                raise RuntimeError(f'Swap {player1!r} ↔ {player2!r} failed: {result}')
            try:
                page.wait_for_load_state('domcontentloaded', timeout=15000)
            except Exception:
                pass
            print(f'Swapped: {player1} ({slot1} → {slot2}), {player2} ({slot2} → {slot1})')

        self._browser_write(_do_swap)

    # ── Auth & league discovery ───────────────────────────────────────────────

    @classmethod
    def list_leagues(cls, creds_file: str, season: int = None) -> pd.DataFrame:
        """
        List all MLB fantasy leagues the authenticated user is enrolled in.

        Args:
            creds_file: Path to yahoo_oauth.json.
            season:     Season year (defaults to current calendar year).

        Returns:
            DataFrame with columns:
                league_id, team_name, name, scoring_method, num_teams, draft_status, league_key
        """
        _SCORING_LABEL = {'head': 'categories', 'headpoint': 'points', 'roto': 'roto'}
        season = season or date.today().year

        oauth = OAuth2(None, None, from_file=creds_file)
        if not oauth.token_is_valid():
            oauth.refresh_access_token()

        def _api_get(path: str) -> dict:
            resp = oauth.session.get(f'{BASE}{path}?format=json')
            resp.raise_for_status()
            return resp.json()

        def _team_name(league_key: str) -> str:
            data = _api_get(f'/league/{league_key}/teams')
            teams = data['fantasy_content']['league'][1]['teams']
            for i in range(teams['count']):
                t = cls._flat(teams[str(i)]['team'][0])
                if t.get('is_owned_by_current_login') == 1:
                    return t.get('name', '')
            return ''

        data = _api_get(
            f'/users;use_login=1/games;game_codes={MLB_CODE};seasons={season}/leagues'
        )
        users = data['fantasy_content']['users']
        games = users['0']['user'][1]['games']
        leagues_raw = games['0']['game'][1]['leagues']

        rows = []
        for i in range(leagues_raw['count']):
            lg = cls._flat(leagues_raw[str(i)]['league'][0])
            league_key   = lg.get('league_key', '')
            scoring_type = lg.get('scoring_type', '')
            rows.append({
                'league_id':      lg.get('league_id', ''),
                'team_name':      _team_name(league_key),
                'name':           lg.get('name', ''),
                'scoring_method': _SCORING_LABEL.get(scoring_type, scoring_type),
                'num_teams':      lg.get('num_teams', ''),
                'draft_status':   lg.get('draft_status', ''),
                'league_key':     league_key,
            })
        return pd.DataFrame(rows)

    # ── Top available ─────────────────────────────────────────────────────────

    def top_available(self, n: int = 100, position: str = None) -> pd.DataFrame:
        """
        Top available waiver players sorted by % rostered (descending).

        Args:
            n:        Number of players to fetch (pre-sorted by Yahoo average rank).
            position: Optional Yahoo position code filter (e.g. 'SP', 'OF', 'C').

        Returns:
            DataFrame with columns: name, team, positions, status, pct_owned
        """
        self._require()
        pos = f';position={position}' if position else ''
        data = self._get(
            f'/league/{self._league_key}/players'
            f';status=W{pos};count={n};out=percent_owned;sort=AR'
        )
        players = data['fantasy_content']['league'][1]['players']
        if not isinstance(players, dict):
            return pd.DataFrame(columns=['name', 'team', 'positions', 'status', 'pct_owned'])
        rows = []
        for i in range(players.get('count', 0)):
            p = players[str(i)]['player']
            flat = self._flat(p[0])
            rows.append({
                'name':      self._name(flat.get('name', '')),
                'team':      flat.get('editorial_team_abbr', ''),
                'positions': flat.get('display_position', ''),
                'status':    flat.get('status', ''),
                'pct_owned': self._parse_pct_owned(p[1] if len(p) > 1 else {}),
            })
        return (
            pd.DataFrame(rows)
            .sort_values('pct_owned', ascending=False)
            .reset_index(drop=True)
        )

    @staticmethod
    def _parse_pct_owned(p1) -> float:
        """Extract percent_owned value from a player[1] sub-resource dict."""
        if not isinstance(p1, dict):
            return 0.0
        po = p1.get('percent_owned', [])
        if isinstance(po, list):
            flat: dict = {}
            for item in po:
                if isinstance(item, dict):
                    flat.update(item)
            return float(flat.get('value', 0))
        if isinstance(po, dict):
            return float(po.get('value', 0))
        return float(po)

    # ── ADP / Draft value ─────────────────────────────────────────────────────

    @staticmethod
    def _norm_name(name: str) -> str:
        """Lowercase, strip accents, strip Yahoo '(Batter)'/'(Pitcher)' suffix."""
        s = str(name).lower()
        s = re.sub(r'\s*\((batter|pitcher)\)', '', s)
        s = unicodedata.normalize('NFKD', s)
        return ''.join(c for c in s if not unicodedata.combining(c)).strip()

    def adp(self, n: int = 300) -> pd.DataFrame:
        """
        Fetch Yahoo Average Draft Position for the top n players.

        Uses the game-level draft_analysis endpoint — no league_id required.

        Returns:
            DataFrame with columns: name, team, positions, adp, avg_round, pct_drafted.
            Sorted by adp ascending with a 1-based rank index.
        """
        self._resolve_game_key()
        rows = []
        for start in range(0, n, 25):
            data = self._get(
                f'/game/{self._game_key}/players'
                f';sort=DA_AR;start={start};count=25;out=draft_analysis'
            )
            players = data['fantasy_content']['game'][1]['players']
            if not isinstance(players, dict) or players.get('count', 0) == 0:
                break
            for i in range(players['count']):
                p = players[str(i)]['player']
                info = self._flat(p[0])
                da = self._flat((p[1] if len(p) > 1 else {}).get('draft_analysis', []))
                rows.append({
                    'name':        self._name(info.get('name', '')),
                    'team':        info.get('editorial_team_abbr', ''),
                    'positions':   info.get('display_position', ''),
                    'adp':         float(da.get('average_pick', 999)),
                    'avg_round':   float(da.get('average_round', 999)),
                    'pct_drafted': round(float(da.get('percent_drafted', 0)) * 100, 1),
                })
        df = pd.DataFrame(rows).sort_values('adp').reset_index(drop=True)
        df.index = range(1, len(df) + 1)
        df.index.name = 'rank'
        return df

    def draft_value(self, rankings_df: pd.DataFrame, n: int = 300) -> pd.DataFrame:
        """
        Compare Yahoo ADP against a Fantasy.rank() result to surface undervalued players.

        Args:
            rankings_df: Output of Fantasy.rank() — must have Name, fantasy_score, player_type.
            n:           Number of ADP players to fetch (default 300).

        Returns:
            DataFrame sorted by value descending. value = adp_rank - fantasy_rank;
            positive means drafted later than rankings suggest (undervalued).
        """
        adp_df = self.adp(n).reset_index().rename(columns={'rank': 'adp_rank'})
        adp_df['_key'] = adp_df['name'].apply(self._norm_name)

        rnk = (
            rankings_df.reset_index()
            .rename(columns={'rank': 'fantasy_rank'})
            [['fantasy_rank', 'Name', 'fantasy_score', 'player_type']]
        )
        rnk['_key'] = rnk['Name'].apply(self._norm_name)

        merged = adp_df.merge(rnk, on='_key').drop(columns='_key')
        merged['value'] = merged['adp_rank'] - merged['fantasy_rank']

        result = (
            merged[['name', 'player_type', 'positions', 'adp', 'adp_rank',
                     'fantasy_rank', 'fantasy_score', 'value']]
            .sort_values('value', ascending=False)
            .reset_index(drop=True)
        )
        result.index = range(1, len(result) + 1)
        result.index.name = 'rank'
        return result

    # ── Dunder ────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        if self._fetched:
            return f'Yahoo(league={self._league_key}, team={self._team_key})'
        return f'Yahoo(league_id={self.league_id!r}, season={self.season}, not fetched)'
