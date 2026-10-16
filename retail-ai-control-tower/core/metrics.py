"""KPIs, impact links, health score, alerts and the what-if model for retail (Olist-style) datasets."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import streamlit as st

from core import store

DEFAULT_WEIGHTS = {"on_time": 0.4, "review": 0.3, "healthy": 0.3}


@st.cache_data(show_spinner="Preparing order data…", max_entries=4)
def facts(slug: str, sig: str) -> pd.DataFrame:
    df = store.q(slug, "SELECT * FROM order_facts")
    df["purchase_date"] = pd.to_datetime(df["purchase_date"])
    df["purchase_month"] = pd.to_datetime(df["purchase_month"])
    for c in ("is_canceled", "is_delivered", "is_late", "has_review", "is_bad_review", "is_good_review", "is_healthy"):
        df[c] = df[c].fillna(False).astype(bool)
    return df


def data_end(df: pd.DataFrame) -> pd.Timestamp:
    """Last day with normal order volume (datasets often end with a few incomplete days)."""
    daily = df.groupby("purchase_date").size()
    if daily.empty:
        return pd.Timestamp.today().normalize()
    window = daily[daily.index >= daily.index.max() - pd.Timedelta(days=180)]
    med = window.median()
    roll = daily.rolling(3, min_periods=1).mean()
    good = roll[roll >= 0.6 * med]
    return good.index.max() if not good.empty else daily.index.max()


def period_bounds(df: pd.DataFrame, choice: str, custom=None):
    end = data_end(df)
    start_all = df["purchase_date"].min()
    months = {"Last 3 months": 3, "Last 6 months": 6, "Last 12 months": 12}.get(choice)
    if choice == "Custom" and custom:
        s, e = pd.Timestamp(custom[0]), pd.Timestamp(custom[1])
    elif months:
        e = end
        s = (e - pd.DateOffset(months=months)) + pd.Timedelta(days=1)
    else:
        s, e = start_all, end
    length = e - s
    ps, pe = s - length - pd.Timedelta(days=1), s - pd.Timedelta(days=1)
    return s, e, ps, pe


def slice_period(df, s, e):
    return df[(df["purchase_date"] >= s) & (df["purchase_date"] <= e)]


def kpis(df: pd.DataFrame, weights=None) -> dict:
    w = weights or DEFAULT_WEIGHTS
    live = df[~df["is_canceled"]]
    deliv = live[live["is_delivered"]]
    rev = live[live["has_review"]]
    dr = deliv[deliv["has_review"]]
    orders = len(live)
    gmv = float(live["gmv"].sum())
    on_time = float(1 - deliv["is_late"].mean()) if len(deliv) else np.nan
    avg_review = float(rev["review_score"].mean()) if len(rev) else np.nan
    bad_share = float(rev["is_bad_review"].mean()) if len(rev) else np.nan
    healthy_gmv = float(live.loc[live["is_healthy"], "gmv"].sum())
    healthy_share = healthy_gmv / float(dr["gmv"].sum()) if len(dr) and dr["gmv"].sum() else np.nan
    bad_exp = live[(live["is_late"]) | (live["is_bad_review"])]
    per_cust = live.groupby("customer_unique_id").size()
    out = dict(
        orders=orders, gmv=gmv, aov=gmv / orders if orders else np.nan,
        customers=int(live["customer_unique_id"].nunique()),
        on_time=on_time, late_rate=1 - on_time if not np.isnan(on_time) else np.nan,
        avg_delivery_days=float(deliv["delivery_days"].mean()) if len(deliv) else np.nan,
        avg_review=avg_review, bad_share=bad_share,
        healthy_gmv=healthy_gmv, healthy_share=healthy_share,
        revenue_at_risk=float(bad_exp["gmv"].sum()),
        repeat_rate=float((per_cust >= 2).mean()) if len(per_cust) else np.nan,
    )
    out["health_score"] = health_score(out, w)
    return out


def health_score(k: dict, w=None) -> float:
    w = w or DEFAULT_WEIGHTS
    parts = {"on_time": k.get("on_time"), "review": (k.get("avg_review", np.nan) - 1) / 4, "healthy": k.get("healthy_share")}
    tot = sum(w.values()) or 1
    vals = [w[n] * (v if v is not None and not np.isnan(v) else 0) for n, v in parts.items()]
    return float(100 * sum(vals) / tot)


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    live = df[~df["is_canceled"]]
    g = live.groupby("purchase_month")
    out = pd.DataFrame({
        "orders": g.size(), "gmv": g["gmv"].sum(),
        "healthy_gmv": live[live["is_healthy"]].groupby("purchase_month")["gmv"].sum(),
    })
    deliv = live[live["is_delivered"]].groupby("purchase_month")
    out["on_time"] = 1 - deliv["is_late"].mean()
    out["delivery_days"] = deliv["delivery_days"].mean()
    rev = live[live["has_review"]].groupby("purchase_month")
    out["avg_review"] = rev["review_score"].mean()
    out["bad_share"] = rev["is_bad_review"].mean()
    out = out.fillna({"healthy_gmv": 0}).reset_index().rename(columns={"purchase_month": "month"})
    return out[out["orders"] >= 50]


# ---------------------------------------------------------------- impact links

DELAY_BUCKETS = [(-999, 0, "On time / early"), (1, 3, "1–3 days late"), (4, 7, "4–7 days late"), (8, 14, "8–14 days late"), (15, 9999, "15+ days late")]


@st.cache_data(show_spinner=False, max_entries=4)
def impact_links(slug: str, sig: str) -> dict:
    df = facts(slug, sig)
    d = df[(~df["is_canceled"]) & df["is_delivered"] & df["has_review"]].copy()
    d["delay_pos"] = d["delay_days"].clip(lower=0, upper=30)

    def bucket(x):
        for lo, hi, lab in DELAY_BUCKETS:
            if lo <= x <= hi:
                return lab
        return DELAY_BUCKETS[-1][2]
    d["delay_bucket"] = d["delay_days"].apply(bucket)
    by_delay = d.groupby("delay_bucket").agg(orders=("order_id", "size"), avg_review=("review_score", "mean"),
                                            bad_share=("is_bad_review", "mean")).reindex([b[2] for b in DELAY_BUCKETS]).dropna().reset_index()
    late = d[d["is_late"]]
    slope = float(np.polyfit(late["delay_pos"], late["review_score"], 1)[0]) if len(late) > 30 else np.nan
    p_bad_late = float(late["is_bad_review"].mean()) if len(late) else np.nan
    p_bad_on = float(d.loc[~d["is_late"], "is_bad_review"].mean())
    p_good_on = float(d.loc[~d["is_late"], "is_good_review"].mean())
    p_good_late = float(late["is_good_review"].mean()) if len(late) else np.nan
    r_on = float(d.loc[~d["is_late"], "review_score"].mean())
    r_late = float(late["review_score"].mean()) if len(late) else np.nan

    # first-order experience -> repeat purchase
    live = df[~df["is_canceled"]].sort_values("purchase_ts")
    first = live.groupby("customer_unique_id").first()
    n_orders = live.groupby("customer_unique_id").size()
    first = first.assign(repeat=(n_orders >= 2).reindex(first.index).values)
    good = first[(first["is_delivered"]) & (~first["is_late"]) & (first["review_score"] >= 4)]
    bad = first[(first["is_late"]) | (first["review_score"] <= 2)]
    rep_good = float(good["repeat"].mean()) if len(good) else np.nan
    rep_bad = float(bad["repeat"].mean()) if len(bad) else np.nan

    # freight share -> review
    fr = d.dropna(subset=["freight_share"]).copy()
    fr["freight_band"] = pd.qcut(fr["freight_share"], 4, labels=["Low freight share", "Medium-low", "Medium-high", "High freight share"])
    by_freight = fr.groupby("freight_band", observed=True).agg(orders=("order_id", "size"), avg_review=("review_score", "mean"),
                                                              bad_share=("is_bad_review", "mean"), freight_share=("freight_share", "mean")).reset_index()
    # share of GMV from delivered + reviewed orders (used by what-if)
    live_gmv = float(df.loc[~df["is_canceled"], "gmv"].sum())
    return dict(by_delay=by_delay, slope_per_day=slope, p_bad_late=p_bad_late, p_bad_on=p_bad_on,
                p_good_on=p_good_on, p_good_late=p_good_late, review_on=r_on, review_late=r_late,
                repeat_good=rep_good, repeat_bad=rep_bad, n_first_good=len(good), n_first_bad=len(bad),
                by_freight=by_freight, gmv_reviewed_share=float(d["gmv"].sum()) / live_gmv if live_gmv else np.nan,
                late_rate=float(d["is_late"].mean()))


# ---------------------------------------------------------------- what-if

@dataclass
class Scenario:
    late_reduction: float = 0.0      # 0..1  (share of late deliveries fixed)
    demand_change: float = 0.0       # -0.5..+1 (e.g. promotion)
    stress_per_10pct: float = 0.01   # extra late rate per +10% demand (assumption)


def what_if(base: dict, links: dict, sc: Scenario, weights=None) -> dict:
    late0 = base["late_rate"]
    late1 = late0 * (1 - sc.late_reduction) + max(sc.demand_change, 0) * 10 * sc.stress_per_10pct
    late1 = float(min(max(late1, 0), 1))
    ro, rl = links["review_on"], links["review_late"]
    pbo, pbl, pgo = links["p_bad_on"], links["p_bad_late"], links["p_good_on"]
    k = dict(base)
    k["orders"] = base["orders"] * (1 + sc.demand_change)
    k["gmv"] = base["gmv"] * (1 + sc.demand_change)
    k["late_rate"], k["on_time"] = late1, 1 - late1
    # Calibrate to the base period so "no change" gives exactly the base values
    d_review = ((1 - late1) * ro + late1 * rl) - ((1 - late0) * ro + late0 * rl)
    d_bad = ((1 - late1) * pbo + late1 * pbl) - ((1 - late0) * pbo + late0 * pbl)
    d_healthy = (1 - late1) * pgo - (1 - late0) * pgo
    k["avg_review"] = base["avg_review"] + d_review
    k["bad_share"] = base["bad_share"] + d_bad
    k["healthy_share"] = base["healthy_share"] + d_healthy
    share_rev = base["healthy_gmv"] / base["healthy_share"] if base["healthy_share"] else 0
    k["healthy_gmv"] = k["healthy_share"] * share_rev * (1 + sc.demand_change)
    bad0 = late0 + (1 - late0) * pbo
    bad1 = late1 + (1 - late1) * pbo
    k["revenue_at_risk"] = base["revenue_at_risk"] * (1 + sc.demand_change) * (bad1 / bad0 if bad0 else 1)
    k["health_score"] = health_score(k, weights)
    return k


# ---------------------------------------------------------------- alerts

def alerts(df_p: pd.DataFrame, k: dict, k_prev: dict, fc_summary: pd.DataFrame | None, sellers: pd.DataFrame | None) -> list[dict]:
    out = []
    if k_prev and not np.isnan(k_prev.get("on_time", np.nan)) and k["on_time"] < k_prev["on_time"] - 0.01:
        out.append(dict(pillar="Supply", level="warning", text=f"On-time delivery fell to {k['on_time']:.1%} (from {k_prev['on_time']:.1%} in the previous period)."))
    if fc_summary is not None and not fc_summary.empty:
        hot = fc_summary[(fc_summary["change"] > 0.10)].sort_values("change", ascending=False).head(2)
        for r in hot.itertuples():
            msg = f"**{r.series}**: demand forecast {r.change:+.0%} for the next 4 weeks"
            if not np.isnan(r.late_rate) and r.late_rate > k["late_rate"]:
                msg += f" and its late rate ({r.late_rate:.1%}) is above average — check sellers before a promotion."
            out.append(dict(pillar="Supply", level="warning", text=msg))
    if sellers is not None and not sellers.empty:
        risky = sellers[sellers["risky"]]
        if len(risky):
            share = risky["gmv"].sum() / sellers["gmv"].sum()
            out.append(dict(pillar="Supply", level="serious", text=f"{len(risky)} sellers have high late-delivery risk; they handle {share:.0%} of seller GMV in this period."))
    live = df_p[(~df_p["is_canceled"]) & df_p["has_review"]]
    if len(live):
        st_rev = live.groupby("customer_state").agg(n=("order_id", "size"), r=("review_score", "mean"))
        worst = st_rev[st_rev["n"] >= 100].sort_values("r").head(1)
        for s, r in worst.iterrows():
            if r["r"] < k["avg_review"] - 0.15:
                out.append(dict(pillar="Customers", level="warning", text=f"Customers in **{s}** give the lowest reviews ({r['r']:.2f}★ vs {k['avg_review']:.2f}★ overall)."))
    if k_prev and k_prev.get("revenue_at_risk"):
        ch = k["revenue_at_risk"] / k_prev["revenue_at_risk"] - 1
        out.append(dict(pillar="Revenue", level="serious" if ch > 0.1 else "info",
                        text=f"Revenue at risk (GMV of late or 1–2★ orders): R$ {k['revenue_at_risk']:,.0f} ({ch:+.0%} vs previous period)."))
    return out
