"""AI engines: customer segments, review drivers, late-delivery risk, demand forecast, cross-sell."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from core import metrics, store

warnings.filterwarnings("ignore")

FRIENDLY = {
    "delay_days": "Delivery delay vs promise (days)", "delivery_days": "Total delivery time (days)",
    "estimated_days": "Promised delivery time (days)", "freight_share": "Freight share of order value",
    "products_value": "Order value (products)", "freight_value": "Freight cost", "items_count": "Items in order",
    "sellers_count": "Sellers in order", "distance_km": "Seller → customer distance",
    "weight_g_total": "Total weight", "installments": "Payment instalments", "customer_state": "Customer state",
    "seller_state": "Seller state", "main_category": "Product category", "payment_type": "Payment type",
    "purchase_month_num": "Month of purchase", "purchase_weekday": "Weekday of purchase",
    "seller_hist_late": "Seller's past late rate", "seller_hist_orders": "Seller's past order count",
}


def _codes(df, cols):
    out = df.copy()
    for c in cols:
        out[c] = out[c].fillna("unknown").astype("category").cat.codes.clip(upper=250)
    return out


# ---------------------------------------------------------------- segments

@st.cache_data(show_spinner="Finding customer segments…", max_entries=4)
def segments(slug: str, sig: str, end: pd.Timestamp):
    df = metrics.facts(slug, sig)
    live = df[(~df["is_canceled"]) & (df["purchase_date"] <= end)]
    c = live.groupby("customer_unique_id").agg(last=("purchase_date", "max"), frequency=("order_id", "size"),
                                               monetary=("gmv", "sum"), review=("review_score", "mean"),
                                               late=("is_late", "mean"), state=("customer_state", "first"))
    c["recency"] = (end - c["last"]).dt.days
    c["review"] = c["review"].fillna(c["review"].mean())
    X = np.column_stack([np.log1p(c["monetary"].fillna(0)), c["recency"], np.log1p(c["frequency"]), c["review"]])
    X = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=4, n_init=10, random_state=42).fit(X)
    c["cluster"] = km.labels_
    cen = c.groupby("cluster").agg(frequency=("frequency", "mean"), review=("review", "mean"), recency=("recency", "mean"), monetary=("monetary", "mean"))
    names, left = {}, list(cen.index)
    rep = cen.loc[left, "frequency"].idxmax(); names[rep] = "Repeat buyers"; left.remove(rep)
    unh = cen.loc[left, "review"].idxmin(); names[unh] = "Unhappy customers"; left.remove(unh)
    rec = cen.loc[left, "recency"].idxmin(); names[rec] = "Recent one-time buyers"; left.remove(rec)
    names[left[0]] = "Dormant one-time buyers"
    c["segment"] = c["cluster"].map(names)
    summary = c.groupby("segment").agg(customers=("frequency", "size"), avg_orders=("frequency", "mean"),
                                       avg_spend=("monetary", "mean"), gmv=("monetary", "sum"),
                                       avg_recency_days=("recency", "mean"), avg_review=("review", "mean"),
                                       late_share=("late", "mean")).reset_index()
    summary["customer_share"] = summary["customers"] / summary["customers"].sum()
    summary["gmv_share"] = summary["gmv"] / summary["gmv"].sum()
    order = ["Repeat buyers", "Recent one-time buyers", "Dormant one-time buyers", "Unhappy customers"]
    summary["segment"] = pd.Categorical(summary["segment"], order, ordered=True)
    return summary.sort_values("segment"), c.reset_index()


# ---------------------------------------------------------------- review drivers

@st.cache_data(show_spinner="Training the review-driver model…", max_entries=4)
def review_drivers(slug: str, sig: str):
    df = metrics.facts(slug, sig)
    d = df[(~df["is_canceled"]) & df["is_delivered"] & df["has_review"]].copy()
    num = ["delay_days", "delivery_days", "estimated_days", "freight_share", "products_value", "items_count",
           "sellers_count", "distance_km", "weight_g_total", "installments"]
    cat = ["customer_state", "seller_state", "main_category", "payment_type"]
    d = _codes(d, cat)
    X, y = d[num + cat], d["is_bad_review"].astype(int)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    m = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.08, categorical_features=[X.columns.get_loc(c) for c in cat], random_state=42)
    m.fit(Xtr, ytr)
    auc = roc_auc_score(yte, m.predict_proba(Xte)[:, 1])
    samp = Xte.sample(min(6000, len(Xte)), random_state=1)
    pi = permutation_importance(m, samp, yte.loc[samp.index], scoring="roc_auc", n_repeats=3, random_state=1)
    imp = pd.DataFrame({"feature": X.columns, "importance": pi.importances_mean}).sort_values("importance", ascending=False)
    imp = imp[imp["importance"] > 0]
    imp["driver"] = imp["feature"].map(FRIENDLY).fillna(imp["feature"])
    imp["share"] = imp["importance"] / imp["importance"].sum()
    return dict(auc=float(auc), importance=imp, n_train=len(Xtr), n_test=len(Xte), base_rate=float(y.mean()))


# ---------------------------------------------------------------- late-delivery risk

@st.cache_data(show_spinner="Training the late-delivery model…", max_entries=4)
def late_model(slug: str, sig: str):
    df = metrics.facts(slug, sig)
    d = df[(~df["is_canceled"])].copy()
    d["purchase_month_num"] = d["purchase_ts"].dt.month
    d["purchase_weekday"] = d["purchase_ts"].dt.weekday
    deliv = d[d["is_delivered"]]
    split = deliv["purchase_date"].quantile(0.8)
    train = deliv[deliv["purchase_date"] < split]
    hist = train.groupby("seller_id").agg(seller_hist_late=("is_late", "mean"), seller_hist_orders=("order_id", "size"))
    d = d.join(hist, on="seller_id")
    d["seller_hist_late"] = d["seller_hist_late"].fillna(train["is_late"].mean())
    d["seller_hist_orders"] = d["seller_hist_orders"].fillna(0)
    num = ["estimated_days", "distance_km", "freight_value", "products_value", "weight_g_total", "items_count",
           "sellers_count", "purchase_month_num", "purchase_weekday", "seller_hist_late", "seller_hist_orders"]
    cat = ["customer_state", "seller_state", "main_category"]
    d = _codes(d, cat)
    feats = num + cat
    dl = d[d["is_delivered"]]
    tr, te = dl[dl["purchase_date"] < split], dl[dl["purchase_date"] >= split]
    m = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, categorical_features=[feats.index(c) for c in cat], random_state=42)
    m.fit(tr[feats], tr["is_late"].astype(int))
    p_te = m.predict_proba(te[feats])[:, 1]
    auc = roc_auc_score(te["is_late"].astype(int), p_te)
    top = te.assign(p=p_te).nlargest(max(1, len(te) // 10), "p")
    prec10 = float(top["is_late"].mean())
    d["late_risk"] = m.predict_proba(d[feats])[:, 1]
    return dict(auc=float(auc), precision_top10=prec10, base_rate=float(te["is_late"].mean()), split=split,
                scores=d[["order_id", "late_risk"]], n_train=len(tr), n_test=len(te))


def seller_scorecard(df_p: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    x = df_p[~df_p["is_canceled"]].merge(scores, on="order_id", how="left")
    g = x.groupby("seller_id").agg(state=("seller_state", "first"), orders=("order_id", "size"), gmv=("gmv", "sum"),
                                   late_rate=("is_late", "mean"), avg_review=("review_score", "mean"),
                                   avg_delivery_days=("delivery_days", "mean"), predicted_risk=("late_risk", "mean"),
                                   main_category=("main_category", lambda s: s.mode().iat[0] if len(s.mode()) else ""))
    avg = float(x["late_risk"].mean())
    g["risky"] = (g["orders"] >= 10) & ((g["predicted_risk"] >= 2 * avg) | (g["late_rate"] >= 0.2))
    return g.reset_index().sort_values(["risky", "gmv"], ascending=[False, False])


# ---------------------------------------------------------------- demand forecast

def _wape(a, f):
    a, f = np.asarray(a, float), np.asarray(f, float)
    return float(np.abs(a - f).sum() / max(np.abs(a).sum(), 1e-9))


def _forecast_series(y: pd.Series, h: int = 8):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    y = y.astype(float)
    def fit_models(train, steps):
        res = {"Naive (last week)": np.repeat(train.iloc[-1], steps),
               "Moving average (4 weeks)": np.repeat(train.iloc[-4:].mean(), steps)}
        try:
            hw = ExponentialSmoothing(train, trend="add", damped_trend=True, initialization_method="estimated").fit()
            res["Holt-Winters (damped trend)"] = np.clip(hw.forecast(steps).values, 0, None)
        except Exception:
            pass
        return res
    bt = 8 if len(y) > 30 else max(2, len(y) // 4)
    tr, te = y.iloc[:-bt], y.iloc[-bt:]
    scores = {name: _wape(te.values, f) for name, f in fit_models(tr, bt).items()}
    best = min(scores, key=scores.get)
    fc = fit_models(y, h)[best]
    resid_sd = float(np.std(te.values - fit_models(tr, bt)[best]))
    idx = pd.date_range(y.index[-1] + pd.Timedelta(weeks=1), periods=h, freq="W-MON")
    return pd.DataFrame({"week": idx, "forecast": fc, "lo": np.clip(fc - 1.28 * resid_sd, 0, None), "hi": fc + 1.28 * resid_sd}), scores, best


@st.cache_data(show_spinner="Forecasting demand…", max_entries=4)
def demand_forecast(slug: str, sig: str, end: pd.Timestamp, top_n: int = 8, h: int = 8):
    df = metrics.facts(slug, sig)
    live = df[(~df["is_canceled"]) & (df["purchase_date"] <= end)].copy()
    live["week"] = live["purchase_date"].dt.to_period("W-SUN").dt.start_time
    last_full = (end - pd.Timedelta(days=end.weekday() + 1)).normalize() - pd.Timedelta(days=6)
    live = live[(live["week"] <= last_full) & (live["week"] >= live["week"].max() - pd.Timedelta(weeks=78))]
    recent = live[live["week"] > last_full - pd.Timedelta(weeks=26)]
    cats = recent.groupby("main_category")["gmv"].sum().nlargest(top_n).index.tolist()
    series = {"All orders": live.groupby("week").size()}
    for c in cats:
        series[c] = live[live["main_category"] == c].groupby("week").size()
    hist_rows, fc_rows, met_rows = [], [], []
    late_by_cat = live[live["is_delivered"]].groupby("main_category")["is_late"].mean()
    for name, s in series.items():
        s = s.reindex(pd.date_range(s.index.min(), last_full, freq="W-MON"), fill_value=0)
        fc, scores, best = _forecast_series(s, h)
        hist_rows.append(pd.DataFrame({"series": name, "week": s.index, "orders": s.values}))
        fc_rows.append(fc.assign(series=name))
        last4 = float(s.iloc[-4:].sum())
        met_rows.append(dict(series=name, best_model=best, wape=scores[best], baseline_wape=scores["Naive (last week)"],
                             last4=last4, next4=float(fc["forecast"].iloc[:4].sum()),
                             late_rate=float(late_by_cat.get(name, np.nan)) if name != "All orders" else np.nan))
    met = pd.DataFrame(met_rows)
    met["change"] = met["next4"] / met["last4"].replace(0, np.nan) - 1
    return pd.concat(hist_rows), pd.concat(fc_rows), met


# ---------------------------------------------------------------- cross-sell

@st.cache_data(show_spinner="Finding cross-sell pairs…", max_entries=4)
def cross_sell(slug: str, sig: str, min_customers: int = 5):
    pairs = store.q(slug, """
        WITH cc0 AS (SELECT DISTINCT customer_unique_id AS c, main_category AS cat FROM order_facts
                    WHERE NOT is_canceled AND main_category IS NOT NULL),
        cc AS (SELECT * FROM cc0 WHERE c IN (SELECT c FROM cc0 GROUP BY 1 HAVING count(*) >= 2)),
        n AS (SELECT count(DISTINCT c) AS n FROM cc),
        single AS (SELECT cat, count(*) AS cnt FROM cc GROUP BY 1),
        pr AS (SELECT a.cat AS a, b.cat AS b, count(*) AS both_cnt FROM cc a JOIN cc b ON a.c = b.c AND a.cat <> b.cat GROUP BY 1, 2)
        SELECT pr.a AS if_customer_buys, pr.b AS they_also_buy, pr.both_cnt AS customers, n.n AS base_customers,
               pr.both_cnt / sa.cnt AS confidence,
               (pr.both_cnt / sa.cnt) / (sb.cnt / n.n) AS lift
        FROM pr JOIN single sa ON sa.cat = pr.a JOIN single sb ON sb.cat = pr.b, n
        WHERE pr.both_cnt >= ? ORDER BY lift DESC""", [min_customers])
    return pairs[pairs["lift"] > 1]
