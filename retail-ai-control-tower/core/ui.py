"""Shared look & feel: CSS, KPI cards, chart helpers."""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.config import ALIGN, CX, GRID, INK, MUTED, REVENUE, SUPPLY, AI, CATEGORICAL

PILLAR = {"Customers": CX, "Supply": SUPPLY, "Revenue": REVENUE, "Alignment": ALIGN, "AI": AI}

CSS = f"""
<style>
.block-container {{padding: 1.2rem 1.6rem 3rem 1.6rem; max-width: 100% !important;}}
[data-testid="stMainBlockContainer"] {{max-width: 100% !important; padding-left: 1.6rem; padding-right: 1.6rem;}}
h1, h2, h3 {{color: {INK}; letter-spacing: -0.01em;}}
[data-testid="stSidebar"] {{background: #0F172A;}}
[data-testid="stSidebar"] * {{color: #E2E8F0;}}
[data-testid="stSidebar"] [data-baseweb="select"] *, [data-testid="stSidebar"] input {{color: {INK} !important; -webkit-text-fill-color: {INK} !important;}}
[data-testid="stSidebar"] [data-baseweb="select"] > div {{background: #fff !important;}}
[data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] small {{color: #94A3B8 !important;}}
.kpi {{background:#fff;border:1px solid {GRID};border-radius:14px;padding:14px 16px 12px;min-height:128px;}}
.kpi .l {{font-size:0.80rem;color:{MUTED};font-weight:600;display:flex;align-items:center;gap:6px;}}
.kpi .l i {{width:9px;height:9px;border-radius:3px;display:inline-block;}}
.kpi .v {{font-size:1.75rem;font-weight:750;color:{INK};line-height:1.2;margin-top:4px;}}
.kpi .d {{font-size:0.80rem;font-weight:600;margin-top:2px;}}
.kpi .h {{font-size:0.75rem;color:{MUTED};margin-top:2px;}}
.kpi .bar {{height:8px;border-radius:4px;background:#EDE9FE;margin-top:8px;overflow:hidden;}}
.kpi .bar div {{height:100%;background:{ALIGN};}}
.up {{color:#15803D;}} .down {{color:#B91C1C;}} .flat {{color:{MUTED};}}
.alert {{display:flex;gap:10px;padding:9px 12px;border:1px solid {GRID};border-radius:10px;margin-bottom:8px;background:#fff;font-size:0.9rem;line-height:1.35}}
.alert .tag {{flex:0 0 auto;font-size:0.72rem;font-weight:700;color:#fff;border-radius:999px;padding:2px 9px;height:fit-content;margin-top:1px}}
.hero {{border-radius:16px;padding:14px 20px;background:linear-gradient(135deg,#F5F3FF 0%,#EFF6FF 100%);border:1px solid #E9E5FF;margin-bottom:12px;display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap}}
.hero .info {{font-size:0.82rem;color:{MUTED};text-align:right}}
.hero .info b {{color:{INK}}}
.hero h1 {{font-size:1.6rem;margin:0}}
.hero p {{margin:4px 0 0;color:{MUTED}}}
.pill {{display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.75rem;font-weight:700;color:#fff;margin-right:6px}}
.note {{font-size:0.82rem;color:{MUTED};}}
.link-card {{background:#fff;border:1px solid {GRID};border-radius:12px;padding:12px 14px;height:100%}}
.link-card .t {{font-size:0.8rem;font-weight:700;color:{MUTED}}}
.link-card .v {{font-size:1.25rem;font-weight:750;color:{INK};margin:4px 0}}
div[data-testid="stMetric"] {{background:#fff;border:1px solid {GRID};border-radius:12px;padding:10px 14px;}}
</style>
"""


def setup():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str = "", info: str = ""):
    import re
    info = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", info)
    st.markdown(f'<div class="hero"><div><h1>{title}</h1><p>{subtitle}</p></div><div class="info">{info}</div></div>', unsafe_allow_html=True)


def section(title: str, help_text: str = ""):
    """Section header; explanations live in the (i) tooltip instead of loose text on the page."""
    st.subheader(title, help=help_text or None, anchor=False)


def fmt_money(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(x) >= div:
            return f"R$ {x / div:,.2f}{suf}" if div >= 1e6 else f"R$ {x / div:,.1f}{suf}"
    return f"R$ {x:,.0f}"


def fmt_num(x, d=0):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    if abs(x) >= 1e6:
        return f"{x / 1e6:,.2f}M"
    if abs(x) >= 1e4:
        return f"{x / 1e3:,.1f}k"
    return f"{x:,.{d}f}"


def fmt_pct(x, d=1):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{d}f}%"


def delta_html(cur, prev, kind="pct_change", good_up=True):
    if prev is None or cur is None or any(isinstance(v, float) and math.isnan(v) for v in (cur, prev)) or prev == 0:
        return '<span class="flat">no comparison</span>'
    if kind == "pts":
        d = (cur - prev) * 100
        txt = f"{d:+.1f} pts"
    elif kind == "abs":
        d = cur - prev
        txt = f"{d:+.2f}"
    else:
        d = cur / prev - 1
        txt = f"{d:+.1%}"
    cls = "flat" if abs(d) < 1e-9 else ("up" if (d > 0) == good_up else "down")
    arrow = "▲" if d > 0 else ("▼" if d < 0 else "■")
    return f'<span class="{cls}">{arrow} {txt} vs previous</span>'


def kpi(label, value, delta="", color=None, help_text="", bar=None):
    dot = f'<i style="background:{color}"></i>' if color else ""
    bar_html = f'<div class="bar"><div style="width:{max(0, min(100, bar)):.0f}%"></div></div>' if bar is not None else ""
    st.markdown(f'<div class="kpi"><div class="l">{dot}{label}</div><div class="v">{value}</div>{bar_html}'
                f'<div class="d">{delta}</div><div class="h">{help_text}</div></div>', unsafe_allow_html=True)


def alert(pillar, text, level="warning"):
    color = PILLAR.get(pillar, ALIGN)
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    st.markdown(f'<div class="alert"><span class="tag" style="background:{color}">{pillar}</span><span>{text}</span></div>', unsafe_allow_html=True)


def base_layout(fig: go.Figure, height=320, title=None, legend=True, yfmt=None, xfmt=None):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=40 if title else 10, b=8),
        title=dict(text=title, font=dict(size=14, color=INK), x=0, xanchor="left") if title else None,
        paper_bgcolor="white", plot_bgcolor="white", font=dict(color=INK, size=12),
        hovermode="x unified" if legend else "closest",
        legend=(dict(orientation="h", yanchor="top", y=-0.16, xanchor="left", x=0, title=None) if title else
                dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=None)) if legend else None,
        showlegend=legend,
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED), title=None)
    fig.update_yaxes(gridcolor="#F1F5F9", zeroline=False, tickfont=dict(color=MUTED), title=None)
    if yfmt:
        fig.update_yaxes(tickformat=yfmt)
    if xfmt:
        fig.update_xaxes(tickformat=xfmt)
    return fig


def line(df, x, ys: dict, height=300, title=None, yfmt=None, hover_fmt=None, dash=None):
    """ys: {column: (label, color)}"""
    fig = go.Figure()
    for col, (label, color) in ys.items():
        fig.add_trace(go.Scatter(x=df[x], y=df[col], name=label, mode="lines+markers",
                                 line=dict(color=color, width=2, dash=(dash or {}).get(col)), marker=dict(size=5),
                                 hovertemplate=f"%{{y:{hover_fmt or ',.2f'}}}<extra>{label}</extra>"))
    return base_layout(fig, height, title, legend=len(ys) > 1, yfmt=yfmt)


def hbar(df, y, x, color, height=None, title=None, xfmt=None, text_fmt=None, hover_extra="", tickfmt=None):
    d = df.iloc[::-1]
    fig = go.Figure(go.Bar(x=d[x], y=d[y], orientation="h", marker=dict(color=color, cornerradius=4),
                           text=[(text_fmt.format(v) if text_fmt else "") for v in d[x]], textposition="outside",
                           cliponaxis=False, hovertemplate=f"%{{y}}: %{{x:{xfmt or ',.2f'}}}{hover_extra}<extra></extra>"))
    fig = base_layout(fig, height or max(360, 32 * len(d) + 60), title, legend=False, xfmt=tickfmt or xfmt)
    fig.update_yaxes(tickfont=dict(color=INK))
    fig.update_xaxes(showgrid=True, gridcolor="#F1F5F9")
    try:
        mx = float(pd.to_numeric(d[x], errors="coerce").max())
        if mx > 0 and text_fmt:
            fig.update_xaxes(range=[0, mx * 1.32])
    except Exception:
        pass
    return fig


def vbar(df, x, y, color, height=400, title=None, yfmt=None, text_fmt=None):
    fig = go.Figure(go.Bar(x=df[x], y=df[y], marker=dict(color=color, cornerradius=4),
                           text=[(text_fmt.format(v) if text_fmt else "") for v in df[y]], textposition="outside",
                           cliponaxis=False, hovertemplate=f"%{{x}}: %{{y:{yfmt or ',.2f'}}}<extra></extra>"))
    return base_layout(fig, height, title, legend=False, yfmt=yfmt)


def auto_chart(df: pd.DataFrame, spec: dict | None):
    """Chart from an AI chart spec; returns a figure or None."""
    if df is None or df.empty or len(df) < 2 or not spec:
        return None
    typ = (spec.get("type") or "none").lower()
    x, y = spec.get("x"), spec.get("y")
    if isinstance(y, str):
        y = [y]
    if typ in ("table", "none") or x not in df.columns or not y or any(c not in df.columns for c in y):
        return None
    y = [c for c in y if pd.api.types.is_numeric_dtype(df[c])][:4]
    if not y:
        return None
    d = df.head(60)
    fig = go.Figure()
    if typ == "line":
        for i, c in enumerate(y):
            fig.add_trace(go.Scatter(x=d[x], y=d[c], name=c, mode="lines+markers", line=dict(color=CATEGORICAL[i], width=2), marker=dict(size=5)))
    elif typ == "pie" and len(y) == 1:
        fig.add_trace(go.Pie(labels=d[x], values=d[y[0]], hole=0.55, marker=dict(colors=CATEGORICAL, line=dict(color="white", width=2)), sort=False))
        return base_layout(fig, 420, legend=True)
    elif typ == "scatter" and len(y) == 1:
        fig.add_trace(go.Scatter(x=d[x], y=d[y[0]], mode="markers", marker=dict(color=CATEGORICAL[0], size=9, line=dict(color="white", width=1))))
    else:
        for i, c in enumerate(y):
            fig.add_trace(go.Bar(x=d[x], y=d[c], name=c, marker=dict(color=CATEGORICAL[i], cornerradius=4)))
    return base_layout(fig, 420, legend=len(y) > 1)


def download_buttons(df: pd.DataFrame, name: str, key: str):
    import io
    c1, c2 = st.columns(2)
    c1.download_button("⬇ CSV", df.to_csv(index=False).encode("utf-8-sig"), f"{name}.csv", "text/csv", key=f"{key}_csv", width="stretch")
    if len(df) <= 1_000_000:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name=name[:31] or "data")
        c2.download_button("⬇ Excel", buf.getvalue(), f"{name}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key}_xlsx", width="stretch")
