"""OpenAI-powered assistant: question -> SQL (DuckDB) -> result -> plain-English answer + chart."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime

import pandas as pd

from core import store
from core.config import LOG_DIR, openai_key, openai_model
from core.olist import KPI_GUIDE

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|export|import|install|load|pragma|set|reset|call|checkpoint|vacuum|grant|revoke|use)\b", re.I)
FILE_FUNCS = re.compile(r"\b(read_csv\w*|read_parquet|read_json\w*|read_text|read_blob|parquet_scan|glob|sniff_csv)\s*\(", re.I)
MAX_ROWS = 5000


class AIError(Exception):
    pass


def available() -> bool:
    return bool(openai_key())


def _client():
    from openai import OpenAI
    if not openai_key():
        raise AIError("No OpenAI key. Put your key in the .env file as OPENAIKEY=... and restart the app.")
    return OpenAI(api_key=openai_key())


def _chat(messages, json_mode=True, temperature=0.1) -> str:
    kw = dict(model=openai_model(), messages=messages)
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    try:
        r = _client().chat.completions.create(temperature=temperature, **kw)
    except Exception as e:  # some newer models do not accept temperature
        if "temperature" in str(e).lower():
            r = _client().chat.completions.create(**kw)
        else:
            raise AIError(f"OpenAI error: {e}") from e
    return r.choices[0].message.content or ""


# ---------------------------------------------------------------- schema context

def schema_context(slug: str, max_tables: int = 40) -> str:
    meta = store.read_meta(slug)
    sch = store.schema(slug)
    lines = [f"Dataset: {meta.get('name', slug)}. {meta.get('description', '')}".strip(),
             "Database: DuckDB. Tables (row counts) and columns (type, example values):"]
    for t, cols in list(sch.items())[:max_tables]:
        n = int(store.q(slug, f'SELECT count(*) AS n FROM "{t}"').n[0])
        lines.append(f'\nTABLE "{t}" ({n:,} rows)')
        sample = store.q(slug, f'SELECT * FROM "{t}" USING SAMPLE 200 ROWS') if n > 0 else pd.DataFrame()
        for c, typ in cols:
            ex = ""
            if c in sample:
                vals = sample[c].dropna().astype(str).unique()[:4]
                ex = ", ".join(v[:30] for v in vals)
            lines.append(f"  - {c} ({typ}){': e.g. ' + ex if ex else ''}")
    if meta.get("kind") == "olist":
        lines.append(KPI_GUIDE)
    return "\n".join(lines)


SQL_SYSTEM = """You are a senior data analyst. You answer questions about the user's dataset by writing ONE DuckDB SQL query.
Rules:
- Only a single SELECT (or WITH ... SELECT) statement. Never modify data. No file functions.
- Use only the tables and columns listed in the schema. Quote identifiers with double quotes if they have special characters.
- Return a small, readable result: aggregate, round numbers (round(x, 2)), give clear column aliases in snake_case, ORDER BY something meaningful, LIMIT 50 unless the user asks for all rows.
- Percentages: return them as 0–100 numbers with a _pct suffix.
- Dates: use date_trunc('month', col) for monthly trends; strftime for labels if needed.
- If the question is not about the data (greeting, definition, how-to), set "sql" to null and answer directly.
Return JSON: {"sql": "... or null", "direct_answer": "text if sql is null else null",
 "chart": {"type": "bar|line|pie|scatter|table|none", "x": "column", "y": "column or [columns]", "color": "column or null"},
 "title": "short title for the result"}"""

ANSWER_SYSTEM = """You are a data analyst explaining results to a business manager in simple, clear English.
Use only the numbers in the result. Lead with the direct answer in one sentence, then 2–4 short bullet points with the key numbers
and one practical insight or next step. Use **bold** for key numbers. Currency in this retail dataset is Brazilian real (R$) when relevant.
If the result is empty, say so and suggest how to rephrase. Do not show SQL. Keep it under 150 words."""


def check_sql(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    s = re.sub(r"^```(sql)?|```$", "", s, flags=re.I).strip()
    if ";" in s:
        raise AIError("Only one SQL statement is allowed.")
    if not re.match(r"^(select|with|from)\b", s, re.I):
        raise AIError("Only SELECT queries are allowed.")
    body = re.sub(r"'[^']*'", "''", s)  # ignore words inside string literals
    if FORBIDDEN.search(body) or FILE_FUNCS.search(body):
        raise AIError("This query uses a command that is not allowed (the assistant is read-only).")
    return s


def run_sql(slug: str, sql: str) -> pd.DataFrame:
    s = check_sql(sql)
    df = store.q(slug, f"SELECT * FROM ({s}) AS _q LIMIT {MAX_ROWS}")
    return df


def _log(entry: dict):
    try:
        with open(LOG_DIR / "assistant.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def ask(slug: str, question: str, history: list[dict] | None = None, max_attempts: int = 3) -> dict:
    """Returns dict(answer, sql, df, chart, title, attempts, error)."""
    t0 = time.time()
    ctx = schema_context(slug)
    msgs = [{"role": "system", "content": SQL_SYSTEM + "\n\nSCHEMA:\n" + ctx}]
    for h in (history or [])[-4:]:
        msgs.append({"role": "user", "content": h["question"]})
        msgs.append({"role": "assistant", "content": json.dumps({"sql": h.get("sql"), "title": h.get("title")})})
    msgs.append({"role": "user", "content": question})
    out = dict(question=question, answer="", sql=None, df=None, chart=None, title="", attempts=0, error=None)
    for attempt in range(1, max_attempts + 1):
        out["attempts"] = attempt
        raw = _chat(msgs)
        try:
            plan = json.loads(raw)
        except json.JSONDecodeError:
            plan = {"sql": None, "direct_answer": raw}
        if not plan.get("sql"):
            out["answer"] = plan.get("direct_answer") or "I could not find a way to answer this from the data."
            break
        try:
            df = run_sql(slug, plan["sql"])
            out.update(sql=check_sql(plan["sql"]), df=df, chart=plan.get("chart"), title=plan.get("title") or "")
            break
        except Exception as e:  # feed the error back so the model can fix its SQL
            out["error"] = str(e)
            msgs.append({"role": "assistant", "content": raw})
            msgs.append({"role": "user", "content": f"The SQL failed with this error: {e}\nFix the query and return the same JSON format."})
    if out["df"] is not None:
        preview = out["df"].head(40).to_csv(index=False)
        out["answer"] = _chat([
            {"role": "system", "content": ANSWER_SYSTEM},
            {"role": "user", "content": f"Question: {question}\nResult ({len(out['df'])} rows, first rows as CSV):\n{preview}"},
        ], json_mode=False, temperature=0.2)
        out["error"] = None
    elif not out["answer"]:
        out["answer"] = f"Sorry, I could not answer this. Last error: {out['error']}"
    _log(dict(ts=datetime.now().isoformat(timespec="seconds"), dataset=slug, question=question, sql=out["sql"],
              rows=None if out["df"] is None else len(out["df"]), attempts=out["attempts"], error=out["error"],
              seconds=round(time.time() - t0, 1), answer=out["answer"]))
    return out


def brief(title: str, facts: dict) -> str:
    """Short management brief from pre-computed numbers (no raw rows are sent)."""
    return _chat([
        {"role": "system", "content": "You are the analyst of a retail marketplace. Write a short weekly brief for managers in simple English: "
                                      "3–5 bullet points, each with a number and a concrete action. Then one line 'Top priority:'. Max 160 words."},
        {"role": "user", "content": f"{title}\nNumbers (JSON):\n{json.dumps(facts, default=str, indent=1)}"},
    ], json_mode=False, temperature=0.3)


def suggested_questions(slug: str) -> list[str]:
    meta = store.read_meta(slug)
    if meta.get("kind") == "olist":
        return ["What is the on-time delivery rate by month in 2018?",
                "Which 10 product categories have the highest GMV?",
                "How does delivery delay affect the average review score?",
                "Which customer states have the worst average review?",
                "What share of customers bought more than once?",
                "Which sellers have the most late deliveries in the last 6 months?"]
    sch = store.schema(slug)
    if not sch:
        return []
    t, cols = next(iter(sch.items()))
    num = [c for c, ty in cols if any(k in ty.upper() for k in ("INT", "DOUBLE", "DECIMAL", "FLOAT", "BIGINT"))]
    cat = [c for c, ty in cols if "VARCHAR" in ty.upper()]
    dt = [c for c, ty in cols if any(k in ty.upper() for k in ("DATE", "TIMESTAMP"))]
    qs = [f"Give me a short summary of the table {t}."]
    if num and cat:
        qs.append(f"What is the total {num[0]} by {cat[0]}? Show the top 10.")
    if num and dt:
        qs.append(f"How did {num[0]} change by month?")
    if cat:
        qs.append(f"How many rows are there for each {cat[0]}?")
    return qs


def insights(dataset_name: str, facts: dict) -> str:
    return _chat([
        {"role": "system", "content": "You are a data analyst. From the table profile and aggregates, write 4–6 short bullet points in simple English: "
                                      "what stands out (with numbers), data-quality issues, and 1–2 questions worth asking next. Max 170 words."},
        {"role": "user", "content": f"Dataset: {dataset_name}\n{json.dumps(facts, default=str)[:12000]}"},
    ], json_mode=False, temperature=0.3)
