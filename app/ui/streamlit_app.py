"""Lightweight Streamlit UI for smart-okf (Phase 2 starter).

Run with: streamlit run app/ui/streamlit_app.py
Provides folder browser, ingest trigger, MD preview, LLM config, reasoning controls.
"""

import streamlit as st
from pathlib import Path
import os
from app.services.llm_client import LLMClient
from scripts.ingest_folder import main as ingest_main  # reuse or refactor

st.set_page_config(page_title="smart-okf", layout="wide")
st.title("smart-okf — Local OKF Knowledge Base")
st.caption("Co-located structured MDs + your local LLM + Honcho-inspired reasoning")

# Sidebar: Config
st.sidebar.header("Configuration")
llm_model = st.sidebar.text_input("LLM Model", value=os.getenv("DEFAULT_MODEL", "qwen2.5:3b"))
llm_host = st.sidebar.text_input("LLM Host", value=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
doc_root = st.sidebar.text_input("Document Root (test one folder first)", value="/path/to/test/docs")

client = LLMClient(model=llm_model, host=llm_host)

# Main tabs
tab1, tab2, tab3 = st.tabs(["Browse & Preview", "Ingest", "Reasoning & Review"])

with tab1:
    st.header("Document Browser (Co-located MDs)")
    st.info("In final version: Interactive tree showing originals + .md companions. For now, manual path input.")
    browse_path = st.text_input("Enter folder path to list", value=doc_root)
    if browse_path and Path(browse_path).exists():
        for item in sorted(Path(browse_path).iterdir()):
            if item.is_file():
                col1, col2 = st.columns([3,1])
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
            # In production: async job, progress, scoped to changed files
            ingest_main(doc_root)  # placeholder - enhance with real pipeline
            st.success("Ingest completed. Check co-located .md files in your folders.")

with tab3:
    st.header("Honcho-Inspired Reasoning Loop")
    st.write("Derive (on new content) + Dream (periodic synthesis for patterns, conflicts, links, actions)")
    if st.button("Trigger Derive Pass"):
        st.info("Placeholder: Calls reasoning_derive prompt on recent MDs via LLMClient.")
        # Implement: load recent MDs, call client with derive prompt, write updates
    if st.button("Trigger Dream Synthesis"):
        st.info("Placeholder: Periodic background-style reasoning over KB.")
        # Implement full dream prompt logic

st.sidebar.markdown("---")
st.sidebar.caption("All local. Configure your LLM. MDs co-located for human + agent use.")
st.sidebar.caption("See DEVELOPMENT_PLAN.md for full roadmap.")
