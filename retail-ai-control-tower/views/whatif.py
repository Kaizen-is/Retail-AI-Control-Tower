import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import metrics, ui
from core.config import ALIGN, MUTED
from views.common import period_text, retail_context

c = retail_context()
if c is None:
    st.stop()

ui.hero("What-if — test a decision before you act", "Change one lever and see the effect on customers, supply and revenue through the impact links.", period_text(c))
L = metrics.impact_links(c.slug, c.sig)

with st.container(border=True):
    a, b, d = st.columns(3)
    red = a.slider("Fix late deliveries (%)", 0, 100, 30, 5, help="Share of today's late deliveries that become on time (e.g. backup sellers, better carriers).")
    dem = b.slider("Demand change (%)", -30, 60, 0, 5, help="For example a promotion that brings more orders.")
    stress = d.slider("Extra late-rate per +10% demand (pts)", 0.0, 3.0, 1.0, 0.25, help="Assumption: more orders put pressure on sellers and delivery.")
    with st.expander("Health Score weights"):
        w1, w2, w3 = st.columns(3)
        w = {"on_time": w1.slider("On-time", 0.0, 1.0, 0.4, 0.05), "review": w2.slider("Reviews", 0.0, 1.0, 0.3, 0.05),
             "healthy": w3.slider("Healthy GMV share", 0.0, 1.0, 0.3, 0.05)}

base = metrics.kpis(c.cur, w)
sc = metrics.Scenario(late_reduction=red / 100, demand_change=dem / 100, stress_per_10pct=stress / 100)
new = metrics.what_if(base, L, sc, w)

rows = [("Ecosystem Health Score", "health_score", lambda v: f"{v:.1f}", True),
        ("Healthy GMV", "healthy_gmv", ui.fmt_money, True),
        ("On-time delivery", "on_time", ui.fmt_pct, True),
        ("Average review", "avg_review", lambda v: f"{v:.2f}★", True),
        ("1–2★ review share", "bad_share", ui.fmt_pct, False),
        ("GMV", "gmv", ui.fmt_money, True),
        ("Revenue at risk", "revenue_at_risk", ui.fmt_money, False)]
cols = st.columns(4)
for i, (lab, key, f, up) in enumerate(rows[:4]):
    with cols[i]:
        kind = "pts" if key in ("on_time",) else ("abs" if key in ("avg_review", "health_score") else "pct_change")
        ui.kpi(lab, f(new[key]), ui.delta_html(new[key], base[key], kind, good_up=up).replace("vs previous", "vs today"), ALIGN, f"today: {f(base[key])}")

st.write("")
l, r = st.columns([1.2, 1])
with l:
    tbl = pd.DataFrame([{"KPI": lab, "Today": f(base[key]), "Scenario": f(new[key]),
                         "Change": (f"{(new[key] - base[key]) * 100:+.1f} pts" if key in ("on_time", "bad_share") else
                                    f"{new[key] - base[key]:+.2f}" if key in ("avg_review", "health_score") else
                                    f"{(new[key] / base[key] - 1):+.1%}" if base[key] else "–")} for lab, key, f, up in rows])
    st.dataframe(tbl, hide_index=True, width="stretch")
with r:
    keys = ["healthy_gmv", "revenue_at_risk"]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=["Healthy GMV", "Revenue at risk"], y=[base[k_] for k_ in keys], name="Today", marker=dict(color="#C4B5FD", cornerradius=4),
                         hovertemplate="R$ %{y:,.0f}<extra>Today</extra>"))
    fig.add_trace(go.Bar(x=["Healthy GMV", "Revenue at risk"], y=[new[k_] for k_ in keys], name="Scenario", marker=dict(color=ALIGN, cornerradius=4),
                         hovertemplate="R$ %{y:,.0f}<extra>Scenario</extra>"))
    fig = ui.base_layout(fig, 420, "Money view (R$)")
    fig.update_layout(barmode="group", hovermode="closest")
    st.plotly_chart(fig, width="stretch")

with st.expander("How the scenario is calculated (impact links from the data)"):
    st.markdown(f"""
- New late rate = today's late rate × (1 − fixed %) + demand increase × stress  → **{base['late_rate']:.1%} → {new['late_rate']:.1%}**
- Average review moves with the mix of on-time and late orders: on-time orders average **{L['review_on']:.2f}★**, late orders **{L['review_late']:.2f}★**.
- 1–2★ share: **{L['p_bad_on']:.1%}** for on-time orders vs **{L['p_bad_late']:.1%}** for late orders.
- Healthy GMV share moves with the on-time rate × the share of on-time orders that get 4–5★ (**{L['p_good_on']:.1%}**).
- GMV and revenue at risk scale with demand; revenue at risk also moves with the share of bad-experience orders.
- Long-term effect not counted here: after a good first order **{L['repeat_good']:.1%}** of customers buy again, after a bad one **{L['repeat_bad']:.1%}**.
""")
    st.markdown("_This is a simple, explainable model for decision support — not a guarantee. All links are measured from this dataset._")
