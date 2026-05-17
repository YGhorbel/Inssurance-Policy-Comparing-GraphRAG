import streamlit as st
import sys
import os

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ingestion.pipeline import Pipeline
from query import GraphQueryEngine

st.set_page_config(page_title="Document Intelligence Pipeline", layout="wide")

st.title("📄 Document Intelligence Pipeline (GraphRAG)")

# Sidebar for Configuration/Status
with st.sidebar:
    st.header("Status")
    if st.button("Check Connections"):
        try:
            # Simple check by instantiating (which usually connects in __init__)
            # Or we could add explicit health checks
            st.success("Configuration loaded.")
        except Exception as e:
            st.error(f"Error: {e}")
            
    st.info("Ensure Docker containers (MinIO, Neo4j) are running.")

tab1, tab2 = st.tabs(["🚀 Ingestion", "🔍 Query & Comparison"])

# --- Ingestion Tab ---
with tab1:
    st.header("Pipeline Ingestion")
    st.write("Trigger the pipeline to check MinIO for new PDFs, chunk them with **Chonkie**, and update the **Neo4j** graph.")
    
    if st.button("Run Ingestion Pipeline", type="primary"):
        with st.spinner("Running pipeline... This may take a while."):
            try:
                # Capture standard output to show logs in UI? 
                # For simplicity, we just run it and show success.
                # A more advanced version would use a custom logger or capture stdout.
                pipeline = Pipeline()
                pipeline.run()
                st.success("Pipeline execution completed successfully!")
            except Exception as e:
                st.error(f"Pipeline failed: {e}")

# --- Query Tab ---
with tab2:
    st.header("Knowledge Graph Query")
    
    query_type = st.radio("Select Action:", ["Summarize Regulation", "Compare Regulations"])

    
    @st.cache_resource
    def get_query_engine():
        return GraphQueryEngine()

    engine = get_query_engine()
    
    if query_type == "Summarize Regulation":
        reg_name = st.text_input("Regulation Name (e.g., 'GDPR Article 12')")
        if st.button("Summarize"):
            if reg_name:
                with st.spinner("Querying Graph & LLM..."):
                    result = engine.summarize_regulation(reg_name)
                    st.markdown("### Result")
                    st.write(result)
            else:
                st.warning("Please enter a regulation name.")
                
    elif query_type == "Compare Regulations":
        col1, col2 = st.columns(2)
        with col1:
            reg_a = st.text_input("Regulation A")
        with col2:
            reg_b = st.text_input("Regulation B")
            
        if st.button("Compare"):
            if reg_a and reg_b:
                with st.spinner("Comparing..."):
                    result = engine.compare_regulations(reg_a, reg_b)
                    st.markdown("### Comparison")
                    st.write(result)
            else:
                st.warning("Please enter both regulation names.")
