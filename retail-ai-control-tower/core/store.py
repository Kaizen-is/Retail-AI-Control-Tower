"""Dataset store: every dataset is a folder of parquet tables + meta.json.

The default Olist dataset lives in data/datasets/olist. Uploaded datasets get their own folder.
Each dataset is loaded into an in-memory DuckDB database (read-only for the AI: external access is
switched off after loading, so SQL cannot read or write files).
"""
from __future__ import annotations

import io
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from core.config import DATA_DIR, DEFAULT_DATASET
from core import olist

# ---------------------------------------------------------------- registry

def _meta_path(slug: str) -> Path:
    return DATA_DIR / slug / "meta.json"


def read_meta(slug: str) -> dict:
    p = _meta_path(slug)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"name": slug, "kind": "generic", "tables": {}}


def write_meta(slug: str, meta: dict):
    _meta_path(slug).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def list_datasets() -> list[dict]:
    out = []
    for d in sorted(DATA_DIR.iterdir()):
        if d.is_dir() and any(d.glob("*.parquet")):
            m = read_meta(d.name)
            m["slug"] = d.name
            out.append(m)
    out.sort(key=lambda m: (not m.get("default", False), m.get("created", "")))
    return out


def signature(slug: str) -> str:
    """Changes whenever a table file changes -> used to refresh caches."""
    parts = [f"{p.name}:{p.stat().st_mtime_ns}:{p.stat().st_size}" for p in sorted((DATA_DIR / slug).glob("*.parquet"))]
    return "|".join(parts)


def table_paths(slug: str) -> dict[str, Path]:
    return {p.stem: p for p in sorted((DATA_DIR / slug).glob("*.parquet"))}


# ---------------------------------------------------------------- DuckDB

@st.cache_resource(show_spinner="Loading dataset…", max_entries=4)
def _connection(slug: str, sig: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    for name, path in table_paths(slug).items():
        con.execute(f'CREATE TABLE "{name}" AS SELECT * FROM read_parquet(?)', [path.as_posix()])
    # Lock the database: no file access, no setting changes (protects against unsafe AI SQL)
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def connection(slug: str) -> duckdb.DuckDBPyConnection:
    return _connection(slug, signature(slug))


def q(slug: str, sql: str, params=None) -> pd.DataFrame:
    cur = connection(slug).cursor()
    try:
        return cur.execute(sql, params or []).df()
    finally:
        cur.close()


def schema(slug: str) -> dict[str, list[tuple[str, str]]]:
    df = q(slug, "SELECT table_name, column_name, data_type FROM information_schema.columns ORDER BY table_name, ordinal_position")
    out: dict[str, list[tuple[str, str]]] = {}
    for r in df.itertuples():
        out.setdefault(r.table_name, []).append((r.column_name, r.data_type))
    return out


def row_counts(slug: str) -> dict[str, int]:
    return {t: int(q(slug, f'SELECT count(*) AS n FROM "{t}"').n[0]) for t in schema(slug)}


@st.cache_data(show_spinner=False, max_entries=20)
def load_table(slug: str, table: str, sig: str) -> pd.DataFrame:
    return q(slug, f'SELECT * FROM "{table}"')


# ---------------------------------------------------------------- import

def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower()
    return s or "dataset"


def clean_columns(cols) -> list[str]:
    out, seen = [], {}
    for i, c in enumerate(cols):
        name = slugify(str(c)) if str(c).strip() else f"column_{i+1}"
        if name[0].isdigit():
            name = f"c_{name}"
        k = seen.get(name, 0)
        seen[name] = k + 1
        out.append(name if k == 0 else f"{name}_{k+1}")
    return out


def _fix_types(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = clean_columns(df.columns)
    for c in df.columns:
        s = df[c]
        if s.dtype == object:
            sample = s.dropna().astype(str).head(500)
            if sample.empty:
                continue
            looks_date = any(k in c for k in ("date", "time", "_at", "_ts", "day", "month"))
            # numbers stored as text (e.g. "1 200,50")
            num = pd.to_numeric(sample.str.replace(r"[\s ]", "", regex=True).str.replace(",", ".", regex=False), errors="coerce")
            if num.notna().mean() > 0.95 and not looks_date:
                df[c] = pd.to_numeric(s.astype(str).str.replace(r"[\s ]", "", regex=True).str.replace(",", ".", regex=False), errors="coerce")
                continue
            if looks_date or sample.str.match(r"^\d{4}-\d{2}-\d{2}").mean() > 0.9:
                parsed = pd.to_datetime(sample, errors="coerce")
                if parsed.notna().mean() > 0.9:
                    df[c] = pd.to_datetime(s, errors="coerce")
        elif str(s.dtype).startswith("datetime64") and getattr(s.dt, "tz", None) is not None:
            df[c] = s.dt.tz_localize(None)
    return df


def read_upload(name: str, data: bytes) -> dict[str, pd.DataFrame]:
    """Turn one uploaded file into {table_name: DataFrame}. Excel: one table per sheet."""
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    base = olist.FILE_ALIASES.get(stem.lower(), slugify(stem))
    if ext in (".csv", ".txt", ".tsv"):
        df = None
        for enc in ("utf-8-sig", "cp1251", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(data), sep=None, engine="python", encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        if df is None:
            raise ValueError("Could not read the CSV file (unknown text encoding).")
        return {base: _fix_types(df)}
    if ext in (".xlsx", ".xlsm", ".xls"):
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
        sheets = {k: v for k, v in sheets.items() if not v.dropna(how="all").empty}
        if len(sheets) == 1:
            return {base: _fix_types(next(iter(sheets.values())))}
        return {f"{base}_{slugify(k)}": _fix_types(v) for k, v in sheets.items()}
    if ext == ".parquet":
        return {base: _fix_types(pd.read_parquet(io.BytesIO(data)))}
    if ext == ".json":
        return {base: _fix_types(pd.read_json(io.BytesIO(data)))}
    raise ValueError(f"File type {ext} is not supported. Use CSV, Excel, Parquet or JSON.")


def create_dataset(name: str, description: str = "") -> str:
    slug = slugify(name)
    base, i = slug, 2
    while (DATA_DIR / slug).exists():
        slug, i = f"{base}_{i}", i + 1
    (DATA_DIR / slug).mkdir(parents=True)
    write_meta(slug, {"name": name.strip() or slug, "kind": "generic", "default": False,
                      "created": datetime.now().isoformat(timespec="seconds"),
                      "description": description, "tables": {}})
    return slug


def save_table(slug: str, table: str, df: pd.DataFrame):
    path = DATA_DIR / slug / f"{slugify(table)}.parquet"
    df = df.copy()
    for c in df.columns:  # parquet cannot store mixed object columns
        if df[c].dtype == object:
            df[c] = df[c].where(df[c].isna(), df[c].astype(str))
    df.to_parquet(path, index=False)
    refresh_meta(slug)


def refresh_meta(slug: str):
    meta = read_meta(slug)
    con = duckdb.connect()
    cols, counts = {}, {}
    for name, path in table_paths(slug).items():
        p = path.as_posix()
        counts[name] = con.execute("SELECT count(*) FROM read_parquet(?)", [p]).fetchone()[0]
        cols[name] = {r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [p]).fetchall()}
    meta["tables"] = counts
    if olist.is_olist(cols) and meta.get("kind") != "olist":
        meta["kind"] = "olist"
    write_meta(slug, meta)
    if meta.get("kind") == "olist" and "order_facts" not in counts:
        build_order_facts(slug, cols)


def build_order_facts(slug: str, cols: dict | None = None):
    """Create order_facts for an uploaded Olist-style dataset (missing optional tables are filled empty)."""
    con = duckdb.connect()
    paths = table_paths(slug)
    for name, path in paths.items():
        con.execute(f'CREATE VIEW "{name}" AS SELECT * FROM read_parquet(?)', [path.as_posix()])
    stubs = {
        "products": "SELECT NULL::VARCHAR AS product_id, NULL::VARCHAR AS product_category_name, NULL::DOUBLE AS product_weight_g WHERE false",
        "category_translation": "SELECT NULL::VARCHAR AS product_category_name, NULL::VARCHAR AS product_category_name_english WHERE false",
        "order_payments": "SELECT NULL::VARCHAR AS order_id, NULL::DOUBLE AS payment_value, NULL::VARCHAR AS payment_type, NULL::INT AS payment_installments WHERE false",
        "sellers": "SELECT NULL::VARCHAR AS seller_id, NULL::VARCHAR AS seller_state, NULL::INT AS seller_zip_code_prefix WHERE false",
    }
    for t, sql in stubs.items():
        if t not in paths:
            con.execute(f"CREATE VIEW {t} AS {sql}")
    geo_cols = {r[0] for r in con.execute("DESCRIBE geolocation").fetchall()} if "geolocation" in paths else set()
    con.execute("DROP VIEW IF EXISTS geolocation") if "geolocation" in paths else None
    if "geolocation_lat" in geo_cols:
        con.execute(f"""CREATE VIEW geolocation AS SELECT geolocation_zip_code_prefix AS zip_code_prefix,
            avg(geolocation_lat) AS lat, avg(geolocation_lng) AS lng FROM read_parquet('{paths['geolocation'].as_posix()}') GROUP BY 1""")
    elif "lat" in geo_cols:
        con.execute(f"CREATE VIEW geolocation AS SELECT * FROM read_parquet('{paths['geolocation'].as_posix()}')")
    else:
        con.execute("CREATE VIEW geolocation AS SELECT NULL::INT AS zip_code_prefix, NULL::DOUBLE AS lat, NULL::DOUBLE AS lng WHERE false")
    out = (DATA_DIR / slug / "order_facts.parquet").as_posix()
    con.execute(f"COPY ({olist.ORDER_FACTS_SQL}) TO '{out}' (FORMAT parquet)")
    meta = read_meta(slug)
    meta["tables"]["order_facts"] = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
    write_meta(slug, meta)


def import_files(slug: str, files: list[tuple[str, bytes]]) -> list[str]:
    created = []
    for fname, data in files:
        for table, df in read_upload(fname, data).items():
            path = DATA_DIR / slug / f"{table}.parquet"
            df.to_parquet(path, index=False)
            created.append(table)
    refresh_meta(slug)
    return created


def delete_table(slug: str, table: str):
    p = DATA_DIR / slug / f"{table}.parquet"
    if p.exists():
        p.unlink()
    refresh_meta(slug)


def delete_dataset(slug: str):
    if slug == DEFAULT_DATASET:
        raise ValueError("The default dataset cannot be deleted.")
    shutil.rmtree(DATA_DIR / slug, ignore_errors=True)


def clear_caches():
    st.cache_data.clear()
