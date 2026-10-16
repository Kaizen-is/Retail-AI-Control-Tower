import streamlit as st

from core import ai, store, ui
from core.config import openai_model

slug = st.session_state.get("ds")
if not slug:
    st.info("No dataset yet. Open Data manager to upload one.")
    st.stop()
meta = store.read_meta(slug)
ui.hero("Ask AI — questions about your data in plain English",
        f"The AI writes SQL for <b>{meta.get('name', slug)}</b>, runs it (read-only), and explains the result with a table and a chart.")

if not ai.available():
    st.warning("AI is off. Open the **.env** file in the project folder, set `OPENAIKEY=sk-...` and restart the app. "
               "Optional: `OPENAI_MODEL=` to choose another model (default gpt-4.1-mini).")

chats = st.session_state.setdefault("chats", {})
history = chats.setdefault(slug, [])

top = st.columns([4, 1])
with top[0]:
    picked = st.pills("Try a question", ai.suggested_questions(slug), selection_mode="single", key=f"pick_{slug}_{len(history)}")
with top[1]:
    if st.button("🧹 Clear chat", width="stretch", disabled=not history):
        chats[slug] = []
        st.rerun()


def render(item, idx):
    with st.chat_message("user"):
        st.markdown(item["question"])
    with st.chat_message("assistant", avatar="🛰️"):
        st.markdown(item["answer"])
        df = item.get("df")
        if df is not None and len(df):
            fig = ui.auto_chart(df, item.get("chart"))
            if fig is not None:
                st.plotly_chart(fig, width="stretch", key=f"fig_{slug}_{idx}")
            with st.expander(f"📄 Result table ({len(df):,} rows)", expanded=fig is None):
                st.dataframe(df, width="stretch", hide_index=True)
                st.download_button("⬇ CSV", df.to_csv(index=False).encode("utf-8-sig"), f"answer_{idx}.csv", "text/csv", key=f"dl_{slug}_{idx}")
        if item.get("sql"):
            with st.expander("🧾 SQL used"):
                st.code(item["sql"], language="sql")
                st.markdown(f"_Attempts: {item.get('attempts', 1)} · model {openai_model()}_")


for i, item in enumerate(history):
    render(item, i)

q = st.chat_input(f"Ask about {meta.get('name', slug)} — e.g. KPIs, trends, top lists, comparisons…", disabled=not ai.available())
q = q or picked
if q and ai.available():
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant", avatar="🛰️"):
        with st.spinner("Writing SQL and checking the data…"):
            try:
                res = ai.ask(slug, q, history)
            except Exception as e:
                res = dict(question=q, answer=f"⚠️ {e}", sql=None, df=None, chart=None)
    history.append({k: res.get(k) for k in ("question", "answer", "sql", "df", "chart", "title", "attempts")})
    st.rerun()
