"""
Central config for the Fantasy Baseball API backend.
"""
import os

# Path to the Yahoo OAuth credentials file (relative to project root)
CREDS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'browser', 'yahoo_oauth.json',
)

# Current season
SEASON = 2026

# Default projection system for upgrade candidates
DEFAULT_PROJ_SYSTEM = 'steamerr'
