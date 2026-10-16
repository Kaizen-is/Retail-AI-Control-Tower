#!/usr/bin/env bash
# Retail AI Control Tower - start on macOS / Linux
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
if [ ! -d .venv ]; then
  python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt
else
  source .venv/bin/activate
fi
streamlit run app.py
