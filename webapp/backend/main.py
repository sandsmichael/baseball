"""
Fantasy Baseball API — FastAPI application entry point.
"""
import sys
import os

# Project root on path so yahoo / baseball modules are importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CREDS_FILE
from .routers import dashboard, league, players

app = FastAPI(
    title='Fantasy Baseball Control Panel',
    description='API for managing Yahoo Fantasy Baseball teams',
    version='1.0.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(dashboard.router)
app.include_router(league.router)
app.include_router(players.router)


@app.on_event('startup')
def on_startup():
    """Pre-refresh OAuth token on startup so the first request is fast."""
    import yahoo as _yahoo_mod
    try:
        from yahoo import _refresh_tokens, _token_is_expired
        if _token_is_expired(CREDS_FILE):
            print('[startup] Refreshing Yahoo OAuth token...')
            ok = _refresh_tokens(CREDS_FILE)
            print(f'[startup] Token refresh: {"OK" if ok else "FAILED"}')
        else:
            print('[startup] Yahoo OAuth token is valid.')
    except Exception as e:
        print(f'[startup] Token check failed: {e}')


@app.get('/api/health')
def health():
    return {'status': 'ok'}
