# Retail AI Control Tower

AI-powered retail control tower that aligns **customer experience, supply chain and revenue** on one dashboard. Built on ~100k real Olist orders with forecasting, risk models, a what-if simulator, data upload, and an AI assistant that turns plain-English questions into SQL.

**Stack:** Python · Streamlit · DuckDB · scikit-learn · statsmodels · Plotly · OpenAI

MVP for the master's thesis *"Platform Strategy for an AI-Powered Retail Ecosystem: Aligning Customer Experience, Supply Chain Intelligence, and Revenue Optimization"*.

## Repository

| Folder | Content |
|---|---|
| [`retail-ai-control-tower/`](retail-ai-control-tower/) | The web app: code, default Olist dataset (Parquet), start scripts |
| [`docs/`](docs/) | Project plan (Word) and architecture / data-model diagrams |

## Quick start

1. Install **Python 3.10+** (Windows: tick "Add Python to PATH").
2. Open `retail-ai-control-tower` and double-click **`run.bat`** (macOS / Linux: `./run.sh`).
   The first start creates a virtual environment and installs the packages (a few minutes).
3. The app opens at **http://localhost:8501**.
4. Optional — AI features: put your OpenAI key in `retail-ai-control-tower/.env` → `OPENAIKEY=sk-...`

The `.env` file is never committed; `.env.example` is the template.

## What the app does

| Page | What it shows |
|---|---|
| Overview | Ecosystem Health Score, Healthy GMV (North Star), KPIs, cross-pillar alerts, impact links, AI brief |
| Customers | RFM + K-Means segments, ML drivers of 1–2★ reviews, reviews by state |
| Supply | Weekly demand forecast (back-tested), late-delivery risk model, seller scorecard, restock suggestion |
| Revenue | GMV vs Healthy GMV, categories, cross-sell pairs, freight check |
| What-if | Change a lever and see the effect on all KPIs |
| Data manager | Upload CSV / Excel / Parquet / JSON, review and edit it like a spreadsheet, read-only SQL |
| Explorer | Instant dashboard for any table + AI insights |

More details: [`retail-ai-control-tower/README.md`](retail-ai-control-tower/README.md).

## Data

Default data: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (~100k orders, 2016–2018), licensed CC BY-NC-SA 4.0. Stored as Parquet in `retail-ai-control-tower/data/datasets/olist/`.
