import plotly.graph_objects as go
import streamlit as st

from core import metrics, models, ui
from core.config import CX, REVENUE
from views.common import period_text, retail_context

c = retail_context()
if c is None:
    st.stop()

ui.hero("Customers — who they are and what makes them unhappy", "Customer segments, review drivers and reviews by region.", period_text(c))
k, kp = c.k, c.kp or {}
a, b, d, e = st.columns(4)
with a:
    ui.kpi("Customers", ui.fmt_num(k["customers"]), ui.delta_html(k["customers"], kp.get("customers")), CX)
with b:
    ui.kpi("Average review", f"{k['avg_review']:.2f}★", ui.delta_html(k["avg_review"], kp.get("avg_review"), "abs"), CX)
with d:
    ui.kpi("1–2★ reviews", ui.fmt_pct(k["bad_share"]), ui.delta_html(k["bad_share"], kp.get("bad_share"), "pts", good_up=False), CX)
with e:
    ui.kpi("Repeat buyers (in period)", ui.fmt_pct(k["repeat_rate"]), ui.delta_html(k["repeat_rate"], kp.get("repeat_rate"), "pts"), CX,
           "customers with 2+ orders")

st.write("")
ui.section("Customer segments",
           "RFM features (recency, frequency, money spent) + average review → K-Means clustering into 4 groups, using all orders up to the period end. "
           "Tip: “Unhappy customers” got late deliveries or gave low reviews — the first group to win back.")
seg, cust = models.segments(c.slug, c.sig, c.e)
l, r = st.columns([1.15, 1])
with l:
    fig = go.Figure()
    fig.add_trace(go.Bar(y=seg["segment"].astype(str), x=seg["customer_share"], name="Share of customers", orientation="h",
                         marker=dict(color=CX, cornerradius=4), hovertemplate="%{y}: %{x:.1%} of customers<extra></extra>"))
    fig.add_trace(go.Bar(y=seg["segment"].astype(str), x=seg["gmv_share"], name="Share of GMV", orientation="h",
                         marker=dict(color=REVENUE, cornerradius=4), hovertemplate="%{y}: %{x:.1%} of GMV<extra></extra>"))
    fig = ui.base_layout(fig, 420, "Share of customers vs share of GMV", xfmt=".0%")
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08, hovermode="closest")
    fig.update_yaxes(autorange="reversed", tickfont=dict(color="#0F172A", size=13))
    st.plotly_chart(fig, width="stretch")
with r:
    show = seg[["segment", "customers", "avg_orders", "avg_spend", "avg_recency_days", "avg_review", "late_share"]].copy()
    st.dataframe(show, hide_index=True, width="stretch", column_config={
        "segment": "Segment", "customers": st.column_config.NumberColumn("Customers", format="%d"),
        "avg_orders": st.column_config.NumberColumn("Orders / customer", format="%.2f"),
        "avg_spend": st.column_config.NumberColumn("Avg spend (R$)", format="%.0f"),
        "avg_recency_days": st.column_config.NumberColumn("Days since last order", format="%.0f"),
        "avg_review": st.column_config.NumberColumn("Avg review", format="%.2f ★"),
        "late_share": st.column_config.NumberColumn("Late orders", format="percent")})

rd = models.review_drivers(c.slug, c.sig)
L = metrics.impact_links(c.slug, c.sig)
imp = rd["importance"]
deliv_share = float(imp.loc[imp["feature"].isin(["delay_days", "delivery_days", "estimated_days"]), "share"].sum())
ui.section("What makes reviews bad?",
           f"Gradient-boosting model trained to predict a 1–2★ review. Test ROC-AUC {rd['auc']:.2f} on {rd['n_test']:,} orders; base rate of 1–2★ is {rd['base_rate']:.1%}. "
           f"Delivery factors (delay, delivery time, promised time) together explain {deliv_share:.0%} of the model's importance. "
           f"On-time orders get {L['p_bad_on']:.0%} bad reviews, late orders {L['p_bad_late']:.0%}.")
l, r = st.columns(2)
with l:
    st.plotly_chart(ui.hbar(imp.head(8), "driver", "share", CX, 420, title=f"Top drivers of 1–2★ reviews · model AUC {rd['auc']:.2f}",
                            xfmt=".0%", text_fmt="{:.0%}"), width="stretch")
with r:
    bd = L["by_delay"]
    st.plotly_chart(ui.vbar(bd, "delay_bucket", "bad_share", CX, 420, "Share of 1–2★ reviews by delivery delay", yfmt=".0%", text_fmt="{:.0%}"), width="stretch")

ui.section("Reviews by customer state", "Orders with a review in the selected period; states with at least 50 reviewed orders.")
live = c.cur[(~c.cur["is_canceled"]) & c.cur["has_review"]]
bys = live.groupby("customer_state").agg(orders=("order_id", "size"), avg_review=("review_score", "mean"),
                                         late=("is_late", "mean")).reset_index()
bys = bys[bys["orders"] >= 50].sort_values("avg_review")
l, r = st.columns([1.2, 1])
with l:
    st.plotly_chart(ui.hbar(bys.head(10), "customer_state", "avg_review", CX, 420, title="10 states with the lowest average review", xfmt=".2f", text_fmt="{:.2f}★"), width="stretch")
with r:
    st.dataframe(bys.sort_values("orders", ascending=False), hide_index=True, width="stretch", height=420, column_config={
        "customer_state": "State", "orders": st.column_config.NumberColumn("Orders", format="%d"),
        "avg_review": st.column_config.NumberColumn("Avg review", format="%.2f ★"),
        "late": st.column_config.NumberColumn("Late share", format="percent")})
