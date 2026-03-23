#!/usr/bin/env bash
# Start the Fantasy Baseball frontend dev server
# Run from the project root: bash webapp/start-frontend.sh

set -e
cd "$(dirname "$0")/frontend"

echo "Starting Fantasy Baseball frontend..."
echo "UI: http://localhost:5173"
echo ""

conda run -n base npm run dev
