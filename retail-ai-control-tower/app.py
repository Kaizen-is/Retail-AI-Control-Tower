"""Retail AI Control Tower — Streamlit entry point.  Run:  streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="Retail AI Control Tower", page_icon="🛰️", layout="wide", initial_sidebar_state="expanded")


def _hot_reload():
    """Reload our own modules when their files change, so updates show after a page refresh (no restart needed)."""
    import sys
    from pathlib import Path
    root = Path(__file__).parent
    files = list((root / "core").glob("*.py")) + list((root / "views").glob("common.py"))
    mt = max(f.stat().st_mtime for f in files)
    if getattr(sys, "_rct_mtime", None) != mt:
        for name in list(sys.modules):
            if name in ("core", "views", "views.common") or name.startswith("core."):
                del sys.modules[name]  # next import loads the new code
    sys._rct_mtime = mt


_hot_reload()

from core import ai, store, ui  # noqa: E402
from core.config import DEFAULT_DATASET, openai_model  # noqa: E402

ui.setup()

# ---------------------------------------------------------------- sidebar: dataset + period
datasets = store.list_datasets()
slugs = [d["slug"] for d in datasets]
names = {d["slug"]: d.get("name", d["slug"]) for d in datasets}
ACTIVE_FILE = store.DATA_DIR.parent / "active_dataset.txt"
if "ds" not in st.session_state or st.session_state.ds not in slugs:
    saved = ACTIVE_FILE.read_text(encoding="utf-8").strip() if ACTIVE_FILE.exists() else ""
    st.session_state.ds = saved if saved in slugs else (DEFAULT_DATASET if DEFAULT_DATASET in slugs else (slugs[0] if slugs else None))

with st.sidebar:
    st.markdown("### 🛰️ Retail AI Control Tower")
    st.caption("Customers · Supply · Revenue — aligned")
    if slugs:
        st.selectbox("Active dataset", slugs, key="ds", format_func=lambda s: names.get(s, s))
        meta = store.read_meta(st.session_state.ds)
        kind = meta.get("kind", "generic")
        st.caption(f"{'Retail (Olist format)' if kind == 'olist' else 'Custom dataset'} · {len(meta.get('tables', {}))} tables")
        if kind == "olist":
            st.selectbox("Period", ["Last 3 months", "Last 6 months", "Last 12 months", "All data"], index=1, key="period")
    st.divider()
    try:
        if st.session_state.get("ds"):
            ACTIVE_FILE.write_text(st.session_state.ds, encoding="utf-8")
    except OSError:
        pass
    if ai.available():
        st.caption(f"🟢 AI ready · model {openai_model()}")
    else:
        st.caption("⚪ AI off — add OPENAIKEY to the .env file")

# ---------------------------------------------------------------- pages
pages = {
    "Control Tower": [
        st.Page("views/overview.py", title="Overview", icon="🧭", default=True),
        st.Page("views/customers.py", title="Customers", icon="👥"),
        st.Page("views/supply.py", title="Supply", icon="🚚"),
        st.Page("views/revenue.py", title="Revenue", icon="💰"),
        st.Page("views/whatif.py", title="What-if", icon="🎛️"),
    ],
    "Data": [
        st.Page("views/data_manager.py", title="Data manager", icon="🗂️"),
        st.Page("views/explorer.py", title="Explorer", icon="📊"),
    ],
    "AI": [st.Page("views/ask_ai.py", title="Ask AI", icon="💬")],
}
st.navigation(pages).run()
