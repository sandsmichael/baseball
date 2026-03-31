"""
Fantasy Baseball API — FastAPI application entry point.
"""
import sys
import os
import threading
import time
from contextlib import asynccontextmanager

# Project root on path so yahoo / baseball modules are importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CREDS_FILE
from .routers import dashboard, league, players


def _ensure_token():
    """Refresh the Yahoo token if expired or about to expire."""
    try:
        from yahoo import _refresh_tokens, _token_is_expired
        if _token_is_expired(CREDS_FILE):
            ok = _refresh_tokens(CREDS_FILE)
            print(f'[token] Refresh {"OK" if ok else "FAILED"}', flush=True)
    except Exception as e:
        print(f'[token] Refresh error: {e}', flush=True)


def _token_refresh_loop():
    """Background thread: refresh token every 50 minutes."""
    while True:
        time.sleep(50 * 60)
        _ensure_token()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refresh on startup, then spin up background refresh thread
    _ensure_token()
    t = threading.Thread(target=_token_refresh_loop, daemon=True)
    t.start()
    yield


app = FastAPI(
    title='Fantasy Baseball Control Panel',
    description='API for managing Yahoo Fantasy Baseball teams',
    version='1.0.0',
    lifespan=lifespan,
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


@app.get('/api/health')
def health():
    return {'status': 'ok'}
