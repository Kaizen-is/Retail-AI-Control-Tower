import io

import pandas as pd
import streamlit as st

from core import ai, store, ui
from core.config import DEFAULT_DATASET

ui.hero("Data manager", "Upload any dataset (CSV, Excel, Parquet, JSON), review it like a spreadsheet, edit it, and use it in Explorer and Ask AI.")


def set_active(slug):
    st.session_state.ds = slug


tab_ds, tab_up, tab_view, tab_sql = st.tabs(["📚 Datasets", "⬆️ Upload data", "🔍 Review & edit", "🧮 SQL"])

# ---------------------------------------------------------------- datasets
with tab_ds:
    for d in store.list_datasets():
        with st.container(border=True):
            a, b, c_ = st.columns([3, 2, 1.4])
            active = d["slug"] == st.session_state.get("ds")
            a.markdown(f"**{d.get('name', d['slug'])}** {'· 🟢 active' if active else ''}  \n"
                       f"<span class='note'>{d.get('description', '') or ''}</span>", unsafe_allow_html=True)
            kind = "Retail (Olist format) — all Control Tower pages work" if d.get("kind") == "olist" else "Custom — Explorer and Ask AI"
            rows = sum(d.get("tables", {}).values())
            b.markdown(f"{len(d.get('tables', {}))} tables · {rows:,} rows  \n<span class='note'>{kind}</span>", unsafe_allow_html=True)
            if not active:
                c_.button("Make active", key=f"act_{d['slug']}", on_click=set_active, args=(d["slug"],), width="stretch")
            if d["slug"] != DEFAULT_DATASET:
                with c_.popover("Delete", width="stretch"):
                    st.write(f"Delete **{d.get('name')}** and all its tables?")
                    if st.button("Yes, delete", key=f"del_{d['slug']}", type="primary"):
                        if active:
                            st.session_state.pop("ds", None)
                        store.delete_dataset(d["slug"])
                        store.clear_caches()
                        st.rerun()

# ---------------------------------------------------------------- upload
with tab_up:
    st.markdown("Upload one or more files. **Excel**: every sheet becomes a table. **CSV**: separator and encoding are detected automatically.")
    mode = st.radio("Where to put the data", ["Create a new dataset", "Add tables to an existing dataset"], horizontal=True)
    all_ds = store.list_datasets()
    if mode == "Create a new dataset":
        name = st.text_input("Dataset name", placeholder="e.g. Sales 2025, Shop orders, HR survey")
        desc = st.text_input("Short description (optional — helps the AI understand the data)")
        target = None
    else:
        target = st.selectbox("Dataset", [d["slug"] for d in all_ds if d["slug"] != DEFAULT_DATASET] or ["—"],
                              format_func=lambda s: store.read_meta(s).get("name", s) if s != "—" else "No uploaded datasets yet")
        name = desc = ""
    files = st.file_uploader("Files", type=["csv", "txt", "tsv", "xlsx", "xlsm", "xls", "parquet", "json"], accept_multiple_files=True,
                             help="Tip: upload the 9 Olist CSV files from Kaggle (or another shop export with the same columns) and the dataset is "
                                  "detected as retail data — then all Control Tower pages work with it.")
    if st.button("Import", type="primary", disabled=not files or (mode == "Create a new dataset" and not name) or target == "—"):
        try:
            with st.spinner("Importing…"):
                slug = target or store.create_dataset(name, desc)
                created = store.import_files(slug, [(f.name, f.getvalue()) for f in files])
                store.clear_caches()
            meta = store.read_meta(slug)
            st.success(f"Imported {len(created)} table(s) into **{meta['name']}**: {', '.join(created)}"
                       + (" — detected as **retail (Olist format)** data." if meta.get("kind") == "olist" else "."))
            st.button("Make it the active dataset", on_click=set_active, args=(slug,), type="primary")
        except Exception as e:
            st.error(f"Import failed: {e}")

# ---------------------------------------------------------------- review & edit
with tab_view:
    slug = st.session_state.get("ds")
    if not slug:
        st.info("No dataset.")
    else:
        meta = store.read_meta(slug)
        sch = store.schema(slug)
        tables = list(sch)
        c1, c2, c3 = st.columns([2, 2, 1])
        table = c1.selectbox("Table", tables, index=tables.index("order_facts") if "order_facts" in tables else 0)
        search = c2.text_input("Search in all text columns", placeholder="type to filter rows…")
        limit = c3.selectbox("Rows to show", [1000, 10000, 100000, "All"], index=1)
        cols = [c for c, _ in sch[table]]
        show_cols = st.multiselect("Columns", cols, default=cols[: min(len(cols), 25)])
        where = ""
        if search:
            txt = [f'CAST("{c}" AS VARCHAR) ILIKE ?' for c in cols]
            where = "WHERE " + " OR ".join(txt)
        params = [f"%{search}%"] * len(cols) if search else []
        total = int(store.q(slug, f'SELECT count(*) AS n FROM "{table}" {where}', params).n[0])
        lim = "" if limit == "All" else f"LIMIT {limit}"
        sel = ", ".join(f'"{c}"' for c in (show_cols or cols))
        df = store.q(slug, f'SELECT {sel} FROM "{table}" {where} {lim}', params)
        st.markdown(f"**{total:,}** rows match · showing **{len(df):,}** · {len(cols)} columns", help="Click a column header to sort. Use the search box to filter rows.")
        editable = slug != DEFAULT_DATASET and total <= 50000 and not search
        edit = st.toggle("✏️ Edit mode", value=False, disabled=not editable,
                         help="Edit cells, add or delete rows, then save. Available for uploaded tables up to 50,000 rows (no search filter)."
                         if editable else "The default dataset is read-only. Upload your own data to edit it.")
        if edit:
            full = store.q(slug, f'SELECT * FROM "{table}"')
            edited = st.data_editor(full, num_rows="dynamic", width="stretch", height=620, key=f"ed_{slug}_{table}")
            if st.button("💾 Save changes", type="primary"):
                store.save_table(slug, table, edited)
                store.clear_caches()
                st.success("Saved.")
                st.rerun()
        else:
            st.dataframe(df, width="stretch", height=620, hide_index=True)
        d1, d2, d3 = st.columns([1, 1, 2])
        d1.download_button("⬇ Download CSV", df.to_csv(index=False).encode("utf-8-sig"), f"{table}.csv", "text/csv", width="stretch")
        if d2.button("Prepare Excel file", width="stretch"):
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                df.head(1_000_000).to_excel(w, index=False, sheet_name=table[:31])
            st.session_state["xlsx"] = (table, buf.getvalue())
        if st.session_state.get("xlsx", (None,))[0] == table:
            d3.download_button("⬇ Download Excel", st.session_state["xlsx"][1], f"{table}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        with st.expander("📋 Column profile (types, missing values, min / max, unique values)"):
            prof = store.q(slug, f'SUMMARIZE "{table}"')
            keep = [c for c in ["column_name", "column_type", "min", "max", "approx_unique", "avg", "null_percentage", "count"] if c in prof]
            st.dataframe(prof[keep], hide_index=True, width="stretch")
        if slug != DEFAULT_DATASET:
            with st.popover("🗑 Delete this table"):
                if st.button(f"Yes, delete table {table}", type="primary"):
                    store.delete_table(slug, table)
                    store.clear_caches()
                    st.rerun()

# ---------------------------------------------------------------- SQL
with tab_sql:
    slug = st.session_state.get("ds")
    if slug:
        sch = store.schema(slug)
        first = next(iter(sch)) if sch else "table"
        sql = st.text_area("SQL", value=f'SELECT * FROM "{first}" LIMIT 100', height=160,
                           help="Read-only SQL (DuckDB dialect) on the active dataset. Tables: " + ", ".join(sch))
        if st.button("Run", type="primary"):
            try:
                res = ai.run_sql(slug, sql)
                st.markdown(f"**{len(res):,} rows**")
                st.dataframe(res, width="stretch", hide_index=True, height=520)
                st.download_button("⬇ CSV", res.to_csv(index=False).encode("utf-8-sig"), "query.csv", "text/csv")
            except Exception as e:
                st.error(str(e))
