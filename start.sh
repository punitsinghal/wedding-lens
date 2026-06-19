#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# --- preflight checks ---

if ! command -v pm2 &>/dev/null; then
  echo "Error: pm2 is not installed. Run: npm install -g pm2"
  exit 1
fi

if [ ! -f "$ROOT/backend/.env" ]; then
  echo "Error: backend/.env not found. Copy backend/.env.example → backend/.env and fill in values."
  exit 1
fi

if [ ! -f "$ROOT/frontend/.env.local" ] && [ ! -f "$ROOT/frontend/.env" ]; then
  echo "Error: frontend/.env.local not found. Copy frontend/.env.example → frontend/.env.local and fill in values."
  exit 1
fi

if [ ! -d "$ROOT/backend/venv" ]; then
  echo "Error: backend/venv not found. Run: cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# --- build frontend if needed ---

if [ ! -d "$ROOT/frontend/.next" ]; then
  echo "Building frontend..."
  cd "$ROOT/frontend" && npm run build
fi

# --- start / reload ---

cd "$ROOT"

if pm2 describe wl-backend &>/dev/null || pm2 describe wl-frontend &>/dev/null; then
  echo "Reloading existing pm2 processes..."
  pm2 reload ecosystem.config.js
else
  echo "Starting pm2 processes..."
  pm2 start ecosystem.config.js
fi

pm2 save
echo ""
echo "Done. Useful commands:"
echo "  pm2 logs          — tail all logs"
echo "  pm2 logs wl-backend  — backend logs only"
echo "  pm2 status        — process list"
echo "  pm2 stop all      — stop everything"
