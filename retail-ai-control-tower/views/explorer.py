import plotly.graph_objects as go
import streamlit as st

from core import ai, store, ui
from core.config import ALIGN, CATEGORICAL

ui.hero("Explorer — an instant dashboard for any table", "Pick a table and a measure; the charts adapt to your data. Works with every uploaded dataset.")
slug = st.session_state.get("ds")
if not slug:
    st.info("No dataset yet. Open Data manager to upload one.")
    st.stop()

sch = store.schema(slug)
tables = list(sch)
NUM = ("INT", "DOUBLE", "DECIMAL", "FLOAT", "REAL", "NUMERIC", "HUGEINT")
with st.container(border=True):
    r1 = st.columns([1.4, 1.4, 1, 1.4, 1, 1.4, 0.8])
    table = r1[0].selectbox("Table", tables, index=tables.index("order_facts") if "order_facts" in tables else 0)
    cols = sch[table]
    num = [c for c, t in cols if any(k in t.upper() for k in NUM)]
    dates = [c for c, t in cols if any(k in t.upper() for k in ("DATE", "TIMESTAMP"))]
    cats = [c for c, t in cols if t.upper() in ("VARCHAR", "BOOLEAN") or t.upper().startswith("VARCHAR")]
    def pick(options, prefer):
        for p_ in prefer:
            for i, o in enumerate(options):
                if p_ in o.lower():
                    return i
        return 0
    m_opts = ["Row count"] + num
    m_def = (1 + pick(num, ["gmv", "revenue", "sales", "amount", "price", "value", "total", "qty", "quantity"])) if num else 0
    measure = r1[1].selectbox("Measure", m_opts, index=m_def, key=f"ex_m_{slug}_{table}")
    agg = r1[2].selectbox("Aggregation", ["sum", "avg", "min", "max", "median"], disabled=measure == "Row count", key=f"ex_a_{slug}_{table}")
    d_opts = ["(none)"] + dates
    date_col = r1[3].selectbox("Date column", d_opts, index=(1 + pick(dates, ["purchase", "order", "date", "created"])) if dates else 0, key=f"ex_d_{slug}_{table}")
    grain = r1[4].selectbox("Time grain", ["month", "week", "day", "quarter", "year"], disabled=date_col == "(none)", key=f"ex_g_{slug}_{table}")
    good_dims = []
    for c_ in cats:
        try:
            nu = int(store.q(slug, f'SELECT count(DISTINCT "{c_}") AS n FROM "{table}"').n[0])
            if 2 <= nu <= 60:
                good_dims.append(c_)
        except Exception:
            pass
    dim_opts = ["(none)"] + cats
    dim_def = dim_opts.index(good_dims[pick(good_dims, ["category", "state", "region", "city", "type", "status", "segment", "product"])]) if good_dims else 0
    dim = r1[5].selectbox("Break down by", dim_opts, index=dim_def, key=f"ex_b_{slug}_{table}")
    top_n = r1[6].number_input("Top", 3, 50, 10)

expr = "count(*)" if measure == "Row count" else f'{agg}("{measure}")'
label = "Rows" if measure == "Row count" else f"{agg} of {measure}"
n_rows = int(store.q(slug, f'SELECT count(*) AS n FROM "{table}"').n[0])
tot = store.q(slug, f'SELECT {expr} AS v FROM "{table}"').v[0]
missing = store.q(slug, f'SUMMARIZE "{table}"')
miss_pct = float(missing["null_percentage"].astype(str).str.rstrip("%").astype(float).mean()) if "null_percentage" in missing else 0.0

k = st.columns(4)
with k[0]:
    ui.kpi("Rows", ui.fmt_num(n_rows), "", ALIGN, f"{len(cols)} columns")
with k[1]:
    ui.kpi(label.capitalize(), ui.fmt_num(float(tot), 2) if tot is not None else "–", "", CATEGORICAL[0])
with k[2]:
    if dim != "(none)":
        nd = int(store.q(slug, f'SELECT count(DISTINCT "{dim}") AS n FROM "{table}"').n[0])
        ui.kpi(f"Distinct {dim}", ui.fmt_num(nd), "", CATEGORICAL[1])
    else:
        ui.kpi("Numeric columns", str(len(num)), "", CATEGORICAL[1], f"{len(dates)} date · {len(cats)} text")
with k[3]:
    ui.kpi("Missing values", f"{miss_pct:.1f}%", "", CATEGORICAL[2], "average share of empty cells")

st.write("")
left, right = st.columns(2)
with left:
    if date_col != "(none)":
        if dim != "(none)":
            topv = store.q(slug, f'SELECT "{dim}" AS d FROM "{table}" GROUP BY 1 ORDER BY {expr} DESC NULLS LAST LIMIT 5')["d"].tolist()
            tdf = store.q(slug, f'''SELECT date_trunc('{grain}', "{date_col}") AS t, CASE WHEN "{dim}" IN (SELECT UNNEST(?)) THEN CAST("{dim}" AS VARCHAR) ELSE 'Other' END AS d,
                                   {expr} AS v FROM "{table}" WHERE "{date_col}" IS NOT NULL GROUP BY 1, 2 ORDER BY 1''', [[str(x) for x in topv]])
            fig = go.Figure()
            for i, dv in enumerate([str(x) for x in topv] + ["Other"]):
                s = tdf[tdf["d"] == dv]
                if len(s):
                    fig.add_trace(go.Scatter(x=s["t"], y=s["v"], name=dv, mode="lines", line=dict(color=CATEGORICAL[i % 8] if dv != "Other" else "#8a8a85", width=2)))
            st.plotly_chart(ui.base_layout(fig, 460, f"{label} by {grain} — top 5 {dim}"), width="stretch")
        else:
            tdf = store.q(slug, f'SELECT date_trunc(\'{grain}\', "{date_col}") AS t, {expr} AS v FROM "{table}" WHERE "{date_col}" IS NOT NULL GROUP BY 1 ORDER BY 1')
            st.plotly_chart(ui.line(tdf, "t", {"v": (label, CATEGORICAL[0])}, 460, f"{label} by {grain}"), width="stretch")
    elif measure != "Row count":
        h = store.q(slug, f'SELECT "{measure}" AS v FROM "{table}" WHERE "{measure}" IS NOT NULL AND "{measure}" <= (SELECT quantile_cont("{measure}", 0.99) FROM "{table}") USING SAMPLE 50000 ROWS')
        fig = go.Figure(go.Histogram(x=h["v"], nbinsx=40, marker=dict(color=CATEGORICAL[0], line=dict(color="white", width=1))))
        st.plotly_chart(ui.base_layout(fig, 460, f"Distribution of {measure} (top 1% of values hidden)", legend=False), width="stretch")
    else:
        st.info("Choose a **date column** for a trend, or a numeric **measure** for its distribution.")
with right:
    if dim != "(none)":
        bdf = store.q(slug, f'SELECT CAST("{dim}" AS VARCHAR) AS d, {expr} AS v FROM "{table}" GROUP BY 1 ORDER BY v DESC NULLS LAST LIMIT {int(top_n)}')
        st.plotly_chart(ui.hbar(bdf, "d", "v", CATEGORICAL[1], height=460, title=f"Top {int(top_n)} {dim} by {label}", xfmt=",.2f", text_fmt="{:,.0f}", tickfmt="~s"), width="stretch")
    elif cats:
        st.info("Choose a column in **Break down by** to see the top values.")
    else:
        st.info("This table has no text columns to break down by.")

if measure != "Row count" and date_col != "(none)":
    h = store.q(slug, f'SELECT "{measure}" AS v FROM "{table}" WHERE "{measure}" IS NOT NULL AND "{measure}" <= (SELECT quantile_cont("{measure}", 0.99) FROM "{table}") USING SAMPLE 50000 ROWS')
    fig = go.Figure(go.Histogram(x=h["v"], nbinsx=40, marker=dict(color=CATEGORICAL[2], line=dict(color="white", width=1))))
    st.plotly_chart(ui.base_layout(fig, 360, f"Distribution of {measure} (top 1% of values hidden)", legend=False), width="stretch")

with st.expander("📋 Column profile"):
    keep = [c for c in ["column_name", "column_type", "min", "max", "approx_unique", "avg", "null_percentage"] if c in missing]
    st.dataframe(missing[keep], hide_index=True, width="stretch")

with st.container(border=True):
    b1, b2 = st.columns([4, 1])
    b1.markdown("**🤖 AI insights** — the AI reads the column profile and the charts above and writes what stands out.")
    if b2.button("Find insights", type="primary", disabled=not ai.available(), width="stretch", help=None if ai.available() else "Add OPENAIKEY to the .env file"):
        facts = {"table": table, "rows": n_rows, "selected_measure": label, "total": float(tot) if tot is not None else None,
                 "profile": missing[keep].head(40).astype(str).to_dict("records")}
        if date_col != "(none)":
            facts["trend"] = tdf.tail(24).astype(str).to_dict("records")
        if dim != "(none)":
            facts["top_values"] = bdf.astype(str).to_dict("records")
        with st.spinner("Thinking…"):
            try:
                st.session_state["insights"] = ai.insights(store.read_meta(slug).get("name", slug), facts)
            except Exception as e:
                st.error(str(e))
    if st.session_state.get("insights"):
        st.markdown(st.session_state["insights"])
