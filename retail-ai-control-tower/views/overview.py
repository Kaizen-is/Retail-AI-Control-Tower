import pandas as pd
import streamlit as st

from core import ai, metrics, models, ui
from core.config import ALIGN, CX, REVENUE, SUPPLY, MUTED
from views.common import period_text, retail_context

c = retail_context()
if c is None:
    st.stop()

ui.hero("Overview — is the ecosystem healthy?", "Customers, supply and revenue on one screen, linked by the North Star “Healthy GMV”.", period_text(c))
k, kp = c.k, c.kp or {}

cols = st.columns([1.25, 1, 1, 1, 1])
with cols[0]:
    ui.kpi("Ecosystem Health Score", f"{k['health_score']:.0f} / 100", ui.delta_html(k["health_score"], kp.get("health_score"), "abs"),
           ALIGN, "40% on-time · 30% reviews · 30% healthy GMV share", bar=k["health_score"])
with cols[1]:
    ui.kpi("Healthy GMV (North Star)", ui.fmt_money(k["healthy_gmv"]), ui.delta_html(k["healthy_gmv"], kp.get("healthy_gmv")),
           ALIGN, f"{ui.fmt_pct(k['healthy_share'])} of delivered & reviewed GMV")
with cols[2]:
    ui.kpi("Average review", f"{k['avg_review']:.2f}★", ui.delta_html(k["avg_review"], kp.get("avg_review"), "abs"),
           CX, f"{ui.fmt_pct(k['bad_share'])} of reviews are 1–2★")
with cols[3]:
    ui.kpi("On-time delivery", ui.fmt_pct(k["on_time"]), ui.delta_html(k["on_time"], kp.get("on_time"), "pts"),
           SUPPLY, f"avg {k['avg_delivery_days']:.1f} days to deliver")
with cols[4]:
    ui.kpi("GMV", ui.fmt_money(k["gmv"]), ui.delta_html(k["gmv"], kp.get("gmv")),
           REVENUE, f"{ui.fmt_num(k['orders'])} orders · AOV {ui.fmt_money(k['aov'])}")

st.write("")
win_start = min(c.s, c.e - pd.DateOffset(months=12))
m = metrics.monthly(metrics.slice_period(c.df, win_start, c.e))


def shade(fig):
    fig.add_vrect(x0=c.s.to_period("M").start_time - pd.Timedelta(days=15), x1=c.e + pd.Timedelta(days=15),
                  fillcolor=ALIGN, opacity=0.06, line_width=0, annotation_text="selected period",
                  annotation_position="top left", annotation_font_color=MUTED, annotation_font_size=10)
    return fig


H = 380
left, right = st.columns([3, 1.1])
with left:
    a, b, d = st.columns(3)
    with a:
        st.plotly_chart(shade(ui.line(m, "month", {"avg_review": ("Average review", CX)}, H, title="Customers · average review", hover_fmt=".2f")), width="stretch")
    with b:
        st.plotly_chart(shade(ui.line(m, "month", {"on_time": ("On-time rate", SUPPLY)}, H, title="Supply · on-time delivery", yfmt=".0%", hover_fmt=".1%")), width="stretch")
    with d:
        st.plotly_chart(shade(ui.line(m, "month", {"gmv": ("GMV", REVENUE), "healthy_gmv": ("Healthy GMV", ALIGN)}, H, title="Revenue · GMV vs Healthy GMV", hover_fmt=",.0f")), width="stretch")

with right:
    ui.section("Cross-pillar alerts", "Rules that connect the three parts: demand forecast vs seller late-risk, review drops by state, "
                                      "on-time trend and revenue at risk, for the selected period.")
    with st.spinner("Checking risks…"):
        _, _, fc_met = models.demand_forecast(c.slug, c.sig, c.end)
        lm = models.late_model(c.slug, c.sig)
        sellers = models.seller_scorecard(c.cur, lm["scores"])
    al = metrics.alerts(c.cur, k, c.kp, fc_met, sellers)
    if not al:
        st.success("No cross-pillar risks found for this period.")
    for x in al[:5]:
        ui.alert(x["pillar"], x["text"], x["level"])

# ---------------------------------------------------------------- impact links
ui.section("Impact links — how one part affects the others",
           "Measured from all delivered and reviewed orders in the dataset. These links drive the What-if simulator.")
L = metrics.impact_links(c.slug, c.sig)
cards = [
    (SUPPLY, "Supply", CX, "Customers", f"{L['slope_per_day']:+.3f}★ per day", "Each extra day of delay changes the review score of late orders by this much."),
    (SUPPLY, "Supply", CX, "Customers", f"{L['p_bad_late']:.0%} vs {L['p_bad_on']:.0%}", "Share of 1–2★ reviews for late orders vs on-time orders."),
    (CX, "Customers", REVENUE, "Revenue", f"{L['repeat_good']:.1%} vs {L['repeat_bad']:.1%}", "Customers who buy again after a good vs a bad first order."),
    (REVENUE, "Revenue", CX, "Customers", f"{L['by_freight']['avg_review'].iloc[0]:.2f}★ → {L['by_freight']['avg_review'].iloc[-1]:.2f}★", "Average review with low vs high freight share of order value."),
]
for col, (c1, l1, c2, l2, v, t) in zip(st.columns(4), cards):
    with col:
        st.markdown(f'<div class="link-card"><span class="pill" style="background:{c1}">{l1}</span>→<span class="pill" style="background:{c2};margin-left:6px">{l2}</span>'
                    f'<div class="v">{v}</div><div class="t">{t}</div></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- AI brief
st.write("")
with st.container(border=True):
    b1, b2 = st.columns([4, 1])
    b1.markdown("**🤖 AI management brief** — a short summary with actions, written by the AI from the numbers on this page.")
    go_ = b2.button("Write the brief", type="primary", disabled=not ai.available(), width="stretch",
                    help=None if ai.available() else "Add OPENAIKEY to the .env file")
    if go_:
        facts = {"period": f"{c.s:%Y-%m-%d} to {c.e:%Y-%m-%d}", "kpis": {kk: round(v, 4) if isinstance(v, float) else v for kk, v in k.items()},
                 "previous_period_kpis": {kk: round(v, 4) if isinstance(v, float) else v for kk, v in kp.items()},
                 "alerts": [a_["text"] for a_ in al],
                 "impact_links": {kk: v for kk, v in L.items() if isinstance(v, float)}}
        with st.spinner("Writing…"):
            try:
                st.session_state["brief"] = ai.brief("Retail marketplace — Control Tower brief", facts)
            except Exception as e:
                st.error(str(e))
    if st.session_state.get("brief"):
        st.markdown(st.session_state["brief"])
