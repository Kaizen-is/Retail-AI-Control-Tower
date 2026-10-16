import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import models, ui
from core.config import SUPPLY, INK
from views.common import period_text, retail_context

c = retail_context()
if c is None:
    st.stop()

ui.hero("Supply — can we deliver what customers will want, on time?", "Demand forecast, late-delivery risk and seller performance.", period_text(c))
k, kp = c.k, c.kp or {}
a, b, d, e = st.columns(4)
with a:
    ui.kpi("On-time delivery", ui.fmt_pct(k["on_time"]), ui.delta_html(k["on_time"], kp.get("on_time"), "pts"), SUPPLY)
with b:
    ui.kpi("Average delivery time", f"{k['avg_delivery_days']:.1f} days", ui.delta_html(k["avg_delivery_days"], kp.get("avg_delivery_days"), "pct_change", good_up=False), SUPPLY)
with d:
    deliv = c.cur[(~c.cur["is_canceled"]) & c.cur["is_delivered"]]
    late_days = deliv.loc[deliv["is_late"], "delay_days"].mean()
    ui.kpi("Average delay of late orders", f"{late_days:.1f} days" if late_days == late_days else "–", "", SUPPLY)
with e:
    open_orders = c.cur[(~c.cur["is_canceled"]) & (~c.cur["is_delivered"])]
    ui.kpi("Orders not delivered yet", ui.fmt_num(len(open_orders)), "", SUPPLY, "excluding cancelled")

st.write("")
hist, fc, met = models.demand_forecast(c.slug, c.sig, c.end)
ui.section("Demand forecast (weekly orders)",
           "Three models are back-tested on the last 8 weeks: naive (last week), 4-week moving average and Holt-Winters with damped trend. "
           "The model with the lowest WAPE (weighted absolute percentage error) is used. Shaded band = 80% range.")
left, right = st.columns([3, 1])
with right:
    sel = st.selectbox("Series", met["series"].tolist(), index=0)
    row = met[met["series"] == sel].iloc[0]
    ui.kpi("Next 4 weeks", f"{row.next4:,.0f} orders", f'<span class="{"up" if row.change >= 0 else "down"}">{"▲" if row.change >= 0 else "▼"} {row.change:+.0%} vs last 4 weeks</span>', SUPPLY)
    st.write("")
    ui.kpi("Forecast error (WAPE)", f"{row.wape:.1%}", f'<span class="flat">baseline {row.baseline_wape:.1%}</span>', SUPPLY, row.best_model)
with left:
    h = hist[hist["series"] == sel].tail(40)
    f = fc[fc["series"] == sel]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.concat([f["week"], f["week"][::-1]]), y=pd.concat([f["hi"], f["lo"][::-1]]), fill="toself",
                             fillcolor="rgba(217,119,6,0.12)", line=dict(width=0), mode="lines", hoverinfo="skip", name="80% range"))
    fig.add_trace(go.Scatter(x=h["week"], y=h["orders"], name="Actual", mode="lines", line=dict(color=INK, width=2),
                             hovertemplate="%{x|%d %b %Y}: %{y:,.0f} orders<extra>Actual</extra>"))
    fig.add_trace(go.Scatter(x=f["week"], y=f["forecast"], name="Forecast", mode="lines+markers", line=dict(color=SUPPLY, width=2, dash="dash"),
                             marker=dict(size=6), hovertemplate="%{x|%d %b %Y}: %{y:,.0f} orders<extra>Forecast</extra>"))
    st.plotly_chart(ui.base_layout(fig, 430, f"Weekly orders — {sel}"), width="stretch")
with st.expander("Forecast accuracy for all series"):
    st.dataframe(met[["series", "best_model", "wape", "baseline_wape", "last4", "next4", "change", "late_rate"]], hide_index=True, width="stretch",
                 column_config={"wape": st.column_config.NumberColumn("WAPE", format="percent"),
                                "baseline_wape": st.column_config.NumberColumn("Baseline WAPE", format="percent"),
                                "last4": st.column_config.NumberColumn("Last 4 weeks", format="%d"),
                                "next4": st.column_config.NumberColumn("Next 4 weeks", format="%d"),
                                "change": st.column_config.NumberColumn("Change", format="percent"),
                                "late_rate": st.column_config.NumberColumn("Late rate", format="percent")})

lm = models.late_model(c.slug, c.sig)
sc = models.seller_scorecard(c.cur, lm["scores"])
ui.section("Late-delivery risk and seller scorecard",
           f"Gradient-boosting model on facts known at purchase time (distance, promised days, freight, weight, category, states, seller history). "
           f"Trained before {lm['split']:%d %b %Y}, tested after: ROC-AUC {lm['auc']:.2f}; in the 10% riskiest orders {lm['precision_top10']:.0%} were really late "
           f"(base rate {lm['base_rate']:.1%}). Risky seller = at least 10 orders and predicted risk ≥ 2× average, or actual late rate ≥ 20%.")
l, r = st.columns([1, 1.6])
with l:
    bystate = c.cur[(~c.cur["is_canceled"]) & c.cur["is_delivered"]].groupby("seller_state").agg(orders=("order_id", "size"), late=("is_late", "mean")).reset_index()
    bystate = bystate[bystate["orders"] >= 30].sort_values("late", ascending=False).head(10)
    st.plotly_chart(ui.hbar(bystate, "seller_state", "late", SUPPLY, 440, title="Late rate by seller state", xfmt=".0%", text_fmt="{:.0%}"), width="stretch")
with r:
    t1, t2 = st.columns([2, 1])
    t1.markdown(f"**{int(sc['risky'].sum())} risky sellers** · model AUC {lm['auc']:.2f}")
    only_risky = t2.toggle("Only risky sellers", value=True)
    view = sc[sc["risky"]] if only_risky else sc
    st.dataframe(view.head(300), hide_index=True, width="stretch", height=400, column_config={
        "seller_id": st.column_config.TextColumn("Seller", width="small"), "state": "State",
        "orders": st.column_config.NumberColumn("Orders", format="%d"), "gmv": st.column_config.NumberColumn("GMV (R$)", format="%.0f"),
        "late_rate": st.column_config.ProgressColumn("Late rate", format="percent", min_value=0, max_value=1),
        "predicted_risk": st.column_config.ProgressColumn("Predicted risk", format="percent", min_value=0, max_value=1),
        "avg_review": st.column_config.NumberColumn("Avg review", format="%.2f ★"),
        "avg_delivery_days": st.column_config.NumberColumn("Delivery days", format="%.1f"),
        "main_category": "Main category", "risky": st.column_config.CheckboxColumn("Risky")})

ui.section("Restock suggestion (simulated stock)",
           "Olist has no stock data, so current stock is SIMULATED as N weeks of recent demand. "
           "Suggested order = forecast during lead time + safety stock − current stock. Safety stock = z × weekly demand std × √lead time.")
cc = st.columns(3)
lead = cc[0].slider("Lead time (weeks)", 1, 4, 2)
z = cc[1].select_slider("Service level", options=[0.80, 0.90, 0.95, 0.98], value=0.95, format_func=lambda v: f"{v:.0%}")
cover = cc[2].slider("Simulated current stock (weeks of demand)", 0.0, 6.0, 2.0, 0.5)
zval = {0.80: 0.84, 0.90: 1.28, 0.95: 1.65, 0.98: 2.05}[z]
rows = []
for s in met["series"]:
    if s == "All orders":
        continue
    hs = hist[hist["series"] == s]["orders"].tail(12)
    fs = fc[fc["series"] == s]["forecast"].head(lead)
    stock = cover * hs.tail(4).mean()
    safety = zval * hs.std() * (lead ** 0.5)
    rows.append(dict(category=s, demand_lead_time=fs.sum(), safety_stock=safety, simulated_stock=stock,
                     suggested_order=max(0.0, fs.sum() + safety - stock)))
rs = pd.DataFrame(rows).sort_values("suggested_order", ascending=False)
l, r = st.columns([1, 1.3])
with l:
    st.plotly_chart(ui.hbar(rs, "category", "suggested_order", SUPPLY, 360, title="Suggested order (units = orders)", xfmt=",.0f", text_fmt="{:,.0f}"), width="stretch")
with r:
    st.dataframe(rs, hide_index=True, width="stretch", column_config={
        "category": "Category", "demand_lead_time": st.column_config.NumberColumn("Forecast during lead time", format="%.0f"),
        "safety_stock": st.column_config.NumberColumn("Safety stock", format="%.0f"),
        "simulated_stock": st.column_config.NumberColumn("Simulated stock", format="%.0f"),
        "suggested_order": st.column_config.NumberColumn("Suggested order", format="%.0f")})
