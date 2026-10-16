"""Shared context for the Control Tower pages."""
from __future__ import annotations

import streamlit as st

from core import metrics, store


class Ctx:
    pass


def retail_context() -> Ctx | None:
    """Returns the active retail dataset context, or shows a message and returns None."""
    slug = st.session_state.get("ds")
    if not slug:
        st.info("No dataset yet. Open **Data manager** to upload one.")
        return None
    meta = store.read_meta(slug)
    if meta.get("kind") != "olist":
        st.warning(f"**{meta.get('name', slug)}** is a custom dataset. The Control Tower pages need retail data in the Olist format "
                   "(orders, order_items, order_reviews, customers …). Use **Explorer** and **Ask AI** for this dataset, "
                   "or switch to the default dataset in the sidebar.")
        try:
            st.page_link("views/explorer.py", label="Open Explorer", icon="📊")
        except Exception:
            pass
        return None
    c = Ctx()
    c.slug, c.meta, c.sig = slug, meta, store.signature(slug)
    c.df = metrics.facts(slug, c.sig)
    c.end = metrics.data_end(c.df)
    c.period = st.session_state.get("period", "Last 6 months")
    c.s, c.e, c.ps, c.pe = metrics.period_bounds(c.df, c.period)
    c.cur = metrics.slice_period(c.df, c.s, c.e)
    c.prev = metrics.slice_period(c.df, c.ps, c.pe) if c.period != "All data" else None
    c.k = metrics.kpis(c.cur)
    c.kp = metrics.kpis(c.prev) if c.prev is not None and len(c.prev) > 100 else None
    return c


def period_text(c: Ctx) -> str:
    txt = f"Period **{c.s:%d %b %Y} – {c.e:%d %b %Y}**"
    if c.kp:
        txt += f"<br>vs {c.ps:%d %b %Y} – {c.pe:%d %b %Y}"
    return txt + f"<br>{c.meta.get('name')}"
