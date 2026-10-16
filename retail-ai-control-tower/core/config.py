from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "datasets"
LOG_DIR = ROOT / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env", override=True)


def openai_key() -> str:
    return (os.getenv("OPENAIKEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def openai_model() -> str:
    return (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()


DEFAULT_DATASET = "olist"

# Colours (validated for colour-blind separation; pillars always also carry a text label)
CX = "#2563EB"       # customer experience
SUPPLY = "#D97706"   # supply chain
REVENUE = "#059669"  # revenue
ALIGN = "#7C3AED"    # alignment layer / brand
AI = "#0891B2"       # AI assistant
INK = "#0F172A"
MUTED = "#64748B"
GRID = "#E2E8F0"
GOOD, WARN, BAD = "#15803D", "#B45309", "#B91C1C"
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#8a8a85"]
