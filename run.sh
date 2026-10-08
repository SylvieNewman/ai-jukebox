#!/usr/bin/env bash
# AI Jukebox launcher: activates the venv and starts the server.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "No .venv found — run: python3 -m venv .venv && pip install -r requirements.txt"
  exit 1
fi

if [ ! -f .env ]; then
  echo "No .env found — copy .env.example to .env and fill in your class credentials."
  exit 1
fi

exec .venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port "${PORT:-8000}" "$@"
