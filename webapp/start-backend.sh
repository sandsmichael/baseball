#!/usr/bin/env bash
# Start the Fantasy Baseball API backend
# Run from the project root: bash webapp/start-backend.sh

set -e
cd "$(dirname "$0")/.."

echo "Starting Fantasy Baseball API backend..."
echo "API: http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
echo ""

conda run -n venv uvicorn webapp.backend.main:app --reload --port 8000
