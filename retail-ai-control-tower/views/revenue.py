import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import metrics, models, ui
from core.config import ALIGN, REVENUE, CX
from views.common import period_text, retail_context

c = retail_context()
if c is None:
    st.stop()

ui.hero("Revenue — where we earn more and where we lose money", "GMV, Healthy GMV, categories, cross-sell and freight.", period_text(c))
k, kp = c.k, c.kp or {}
a, b, d, e = st.columns(4)
with a:
    ui.kpi("GMV", ui.fmt_money(k["gmv"]), ui.delta_html(k["gmv"], kp.get("gmv")), REVENUE, f"{ui.fmt_num(k['orders'])} orders")
with b:
    ui.kpi("Average order value", ui.fmt_money(k["aov"]), ui.delta_html(k["aov"], kp.get("aov")), REVENUE)
with d:
    ui.kpi("Healthy GMV", ui.fmt_money(k["healthy_gmv"]), ui.delta_html(k["healthy_gmv"], kp.get("healthy_gmv")), ALIGN,
           f"{ui.fmt_pct(k['healthy_share'])} of delivered & reviewed GMV")
with e:
    ui.kpi("Revenue at risk", ui.fmt_money(k["revenue_at_risk"]), ui.delta_html(k["revenue_at_risk"], kp.get("revenue_at_risk"), good_up=False), REVENUE,
           "GMV of late or 1–2★ orders")

st.write("")
win_start = min(c.s, c.e - pd.DateOffset(months=12))
m = metrics.monthly(metrics.slice_period(c.df, win_start, c.e))
m["other"] = m["gmv"] - m["healthy_gmv"]
fig = go.Figure()
fig.add_trace(go.Bar(x=m["month"], y=m["healthy_gmv"], name="Healthy GMV", marker=dict(color=ALIGN), hovertemplate="R$ %{y:,.0f}<extra>Healthy GMV</extra>"))
fig.add_trace(go.Bar(x=m["month"], y=m["other"], name="Other GMV (late, low or no review, not delivered)", marker=dict(color="#C4B5FD", cornerradius=4),
                     hovertemplate="R$ %{y:,.0f}<extra>Other GMV</extra>"))
fig = ui.base_layout(fig, 420, "Monthly GMV: Healthy vs other")
fig.update_layout(barmode="stack", bargap=0.3)
st.plotly_chart(fig, width="stretch")

ui.section("Categories", "Product category = category of the most expensive item in the order. Healthy share = share of orders delivered on time with a 4–5★ review.")
live = c.cur[~c.cur["is_canceled"]]
cat = live.groupby("main_category").agg(orders=("order_id", "size"), gmv=("gmv", "sum"), aov=("gmv", "mean"),
                                        healthy=("is_healthy", "mean"), late=("is_late", "mean"),
                                        review=("review_score", "mean"), freight=("freight_share", "mean")).reset_index()
cat = cat.sort_values("gmv", ascending=False)
l, r = st.columns([1, 1.3])
with l:
    st.plotly_chart(ui.hbar(cat.head(10), "main_category", "gmv", REVENUE, 440, title="Top 10 categories by GMV", xfmt=",.0f", text_fmt="R$ {:,.0f}", tickfmt="~s"), width="stretch")
with r:
    st.dataframe(cat, hide_index=True, width="stretch", height=440, column_config={
        "main_category": "Category", "orders": st.column_config.NumberColumn("Orders", format="%d"),
        "gmv": st.column_config.NumberColumn("GMV (R$)", format="%.0f"), "aov": st.column_config.NumberColumn("AOV (R$)", format="%.0f"),
        "healthy": st.column_config.ProgressColumn("Healthy share", format="percent", min_value=0, max_value=1),
        "late": st.column_config.NumberColumn("Late", format="percent"), "review": st.column_config.NumberColumn("Review", format="%.2f ★"),
        "freight": st.column_config.NumberColumn("Freight share", format="percent")})

cs = models.cross_sell(c.slug, c.sig)
base_n = int(cs["base_customers"].iloc[0]) if not cs.empty else 0
ui.section("Cross-sell: customers who buy A also buy B",
           f"Based on the {base_n:,} customers who bought from 2 or more categories (most Olist customers buy only once). "
           "Confidence = share of A-buyers who also bought B. Lift > 1 means the pair happens more often than by chance.")
if cs.empty:
    st.info("Not enough repeat customers buying different categories to find reliable pairs.")
else:
    top = cs.drop(columns="base_customers").sort_values("customers", ascending=False).head(15)
    top["pair"] = top["if_customer_buys"] + " → " + top["they_also_buy"]
    l, r = st.columns([1, 1.3])
    with l:
        st.plotly_chart(ui.hbar(top.head(10), "pair", "lift", REVENUE, 440, title="Top pairs by customers (bar = lift)", xfmt=".2f", text_fmt="{:.1f}×"), width="stretch")
    with r:
        st.dataframe(top.drop(columns="pair"), hide_index=True, width="stretch", height=440, column_config={
            "if_customer_buys": "If a customer buys…", "they_also_buy": "…they also buy",
            "customers": st.column_config.NumberColumn("Customers", format="%d"),
            "confidence": st.column_config.NumberColumn("Confidence", format="percent"),
            "lift": st.column_config.NumberColumn("Lift", format="%.1f×")})

L = metrics.impact_links(c.slug, c.sig)
fb = L["by_freight"]
ui.section("Freight check", "Orders split into four equal groups by freight share of order value. When freight is a large part of the price, reviews are lower — "
                            "a lever for pricing and free-shipping thresholds.")
l, r = st.columns(2)
with l:
    st.plotly_chart(ui.vbar(fb.assign(band=fb["freight_band"].astype(str)), "band", "avg_review", CX, 400,
                            "Average review by freight share", yfmt=".2f", text_fmt="{:.2f}★"), width="stretch")
with r:
    st.plotly_chart(ui.vbar(fb.assign(band=fb["freight_band"].astype(str)), "band", "bad_share", CX, 400,
                            "Share of 1–2★ reviews by freight share", yfmt=".0%", text_fmt="{:.1%}"), width="stretch")
