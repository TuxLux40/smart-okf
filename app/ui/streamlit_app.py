"""Lightweight Streamlit UI for smart-okf (Phase 2 starter).

Run with: streamlit run app/ui/streamlit_app.py
Provides folder browser, ingest trigger, MD preview, LLM config, reasoning controls.
"""

import os
from pathlib import Path

import streamlit as st

from app.constants import DEFAULT_LLM_MODEL, DEFAULT_OLLAMA_HOST
from app.services.ingest import ingest_folder
from app.services.llm_client import LLMClient

st.set_page_config(page_title="smart-okf", layout="wide")
st.title("smart-okf — Local OKF Knowledge Base")
st.caption("Co-located structured MDs + your local LLM + Honcho-inspired reasoning")

st.sidebar.header("Configuration")
llm_model = st.sidebar.text_input("LLM Model", value=os.getenv("DEFAULT_MODEL", DEFAULT_LLM_MODEL))
llm_host = st.sidebar.text_input(
    "LLM Host",
    value=os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
)
doc_root = st.sidebar.text_input(
    "Document Root (test one folder first)",
    value="/path/to/test/docs",
)

client = LLMClient(model=llm_model, host=llm_host)

tab1, tab2, tab3 = st.tabs(["Browse & Preview", "Ingest", "Reasoning & Review"])

with tab1:
    st.header("Document Browser (Co-located MDs)")
    st.info("In final version: Interactive tree showing originals + .md companions. For now, manual path input.")
    browse_path = st.text_input("Enter folder path to list", value=doc_root)
    if browse_path and Path(browse_path).exists():
        for item in sorted(Path(browse_path).iterdir()):
            if item.is_file():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"📄 {item.name}")
                with col2:
                    if item.suffix == ".md":
                        if st.button(f"Preview {item.name}", key=str(item)):
                            content = item.read_text(encoding="utf-8", errors="ignore")
                            st.markdown(content)
                    else:
                        st.caption("Original doc")

with tab2:
    st.header("Ingest Pipeline")
    st.write("Run OCR + LLM extraction → co-located OKF MDs")
    if st.button("Run Ingest on Document Root"):
        with st.spinner("Processing..."):
            result = ingest_folder(doc_root, client=client)
            st.success(f"Ingest completed. Wrote {len(result.written_paths)} markdown file(s).")

with tab3:
    st.header("Honcho-Inspired Reasoning Loop")
    st.write("Derive (on new content) + Dream (periodic synthesis for patterns, conflicts, links, actions)")
    if st.button("Trigger Derive Pass"):
        st.info(f"Placeholder: derive pass via {client.model} at {client.host}.")
    if st.button("Trigger Dream Synthesis"):
        st.info("Placeholder: Periodic background-style reasoning over KB.")

st.sidebar.markdown("---")
st.sidebar.caption("All local. Configure your LLM. MDs co-located for human + agent use.")
st.sidebar.caption("See DEVELOPMENT_PLAN.md for full roadmap.")
