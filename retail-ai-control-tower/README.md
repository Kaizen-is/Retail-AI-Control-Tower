# Retail AI Control Tower

MVP for the master's thesis **"Platform Strategy for an AI-Powered Retail Ecosystem: Aligning Customer Experience, Supply Chain Intelligence, and Revenue Optimization"** (Farkhod Shonazarov, ITPU / EPAM).

One web app that connects **customers, supply and revenue** with AI:

| Page | What it does |
|---|---|
| Overview | Ecosystem Health Score, Healthy GMV (North Star), KPIs, cross-pillar alerts, impact links, AI brief |
| Customers | Customer segments (RFM + K-Means), drivers of 1–2★ reviews (ML model), reviews by state |
| Supply | Weekly demand forecast (3 models, back-tested), late-delivery risk model, seller scorecard, restock suggestion (simulated stock) |
| Revenue | GMV vs Healthy GMV, categories, cross-sell pairs, freight check |
| What-if | Change a lever (fix late deliveries, demand change) and see the effect on all KPIs |
| Data manager | Upload any CSV / Excel / Parquet / JSON, review it like a spreadsheet, search, edit, download, column profile, read-only SQL |
| Explorer | Instant dashboard for any table (trend, top values, distribution) + AI insights |
| Ask AI | Ask questions in plain English — OpenAI writes SQL, the app runs it (read-only) and explains the result with a table and chart |

## Start (Windows)

1. Install **Python 3.10 or newer** from python.org (tick "Add Python to PATH").
2. Double-click **run.bat**. The first start creates `.env` and installs the packages (a few minutes). The app opens at http://localhost:8501
3. For the AI features, open `.env` and put your OpenAI key: `OPENAIKEY=sk-...` (optional: `OPENAI_MODEL=gpt-4.1-mini`). No restart needed.

macOS / Linux: `./run.sh`. Manual start: `pip install -r requirements.txt` then `streamlit run app.py`.

## Data

* Default dataset: **Brazilian E-Commerce Public Dataset by Olist** (~100k orders, 2016–2018), stored as Parquet in `data/datasets/olist/`. `order_facts` is a prepared table with one row per order (GMV, delivery, delay, review, healthy flag …).
* Rebuild from the original Kaggle CSV files: `python scripts/build_olist.py <folder_with_csv_files>`
* Uploaded datasets are saved in `data/datasets/<name>/` (one Parquet file per table). If you upload Olist-format tables (orders, order_items, order_reviews, customers …), the dataset is detected as retail data and all Control Tower pages work with it.
* Limits of the Olist data: no stock levels (restock uses **simulated** stock), no costs/margins, data ends in 2018.

## AI and safety

* All AI features use the key in `.env` (`OPENAIKEY`). Without a key, everything except the AI features works.
* The AI sends the table schema, a few example values and the query result (first 40 rows) to OpenAI — never the full data.
* SQL is read-only: only one `SELECT` is allowed, write/file commands are blocked, and the database is locked (no file access).
* Every question, SQL, number of attempts and answer is logged to `logs/assistant.jsonl` (for the thesis evaluation).

## Project structure

```
app.py               entry point (navigation + sidebar)
core/config.py       paths, .env, colours
core/store.py        datasets: upload, Parquet storage, DuckDB, edit/delete
core/olist.py        retail schema detection, order_facts SQL, KPI definitions
core/metrics.py      KPIs, Health Score, impact links, alerts, what-if model
core/models.py       segments, review drivers, late-delivery risk, forecast, cross-sell
core/ai.py           OpenAI text-to-SQL assistant, briefs, insights
core/ui.py           KPI cards, charts, styles
views/*.py           one file per page
scripts/build_olist.py  builds the default dataset from Kaggle CSVs
```
