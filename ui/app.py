import streamlit as st
import requests
import uuid

st.set_page_config(page_title="Tunisian Insurance Legal Assistant", layout="wide")

API_URL = "http://localhost:8000/mcp"

# Status emoji mapping for document display
STATUS_EMOJIS = {
    "pending": "⏳",
    "processing": "⚙️",
    "processed": "✅",
    "error": "❌"
}

# Document metadata options
COUNTRY_OPTIONS = ["Tunisia", "Europe", "France", "Unknown"]
DOC_TYPE_OPTIONS = ["Regulation", "Law", "Guideline"]

st.title("🤖 Legal & Regulatory Multi-Agent Assistant")
st.markdown("*Architecture: LiquidAI LFM2-2.6B + Qdrant + Neo4j + MinIO (Orchestrated via MCP)*")

# Add information about enriched knowledge ingestion
with st.expander("ℹ️ About Knowledge Enrichment System", expanded=False):
    st.markdown("""
    ### 📚 Enriched Knowledge Ingestion
    
    Our advanced analyzer agent transforms raw documents into enriched knowledge chunks with:
    
    - **📝 Summaries**: Concise summaries for each chunk
    - **🔑 Keywords**: Extracted key insurance terms and concepts
    - **❓ Questions**: Generated questions that each chunk can answer
    - **📋 Requirements**: Explicit requirements and obligations extracted
    - **🏷️ Classifications**: Policy type (Auto, Health, Life, etc.) and Clause type (Requirement, Coverage, etc.)
    - **🔗 Metadata**: Enhanced source tracking with page and section information
    
    This enrichment enables more accurate search, better context understanding, and comprehensive policy analysis.
    """)

# Initialize Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

tab1, tab2 = st.tabs(["💬 Chat Assistant", "⚙️ Admin Dashboard"])

with tab1:
    # Display History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # User Input
    if prompt := st.chat_input("Ask a question about insurance regulations..."):
        # Add to history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Agents are thinking..."):
                try:
                    # MCP Request
                    payload = {
                        "jsonrpc": "2.0",
                        "method": "execute_pipeline",
                        "params": {"query": prompt},
                        "id": str(uuid.uuid4())
                    }
                    
                    response = requests.post(API_URL, json=payload)
                    data = response.json()
                    
                    if "error" in data:
                         st.error(f"Agent Error: {data['error']['message']}")
                    else:
                        result = data.get("result", {})
                        answer = result.get("answer", "No answer generated.")
                        analysis = result.get("analysis", {})
                        
                        st.markdown(answer)
                        
                        # Display enriched analysis information
                        with st.expander("📊 Agent Reasoning & Analysis"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.subheader("Query Analysis")
                                if analysis:
                                    classification = analysis.get("classification", "N/A")
                                    st.metric("Routing", classification)
                                    
                                    entities = analysis.get("entities", {})
                                    region = entities.get("region", [])
                                    if isinstance(region, list) and region:
                                        st.write("**Regions:**", ", ".join(str(r) for r in region))
                                    if entities.get("topic"):
                                        st.write("**Topic:**", entities.get("topic", "N/A"))
                            
                            with col2:
                                st.subheader("Context Stats")
                                context_used = result.get("context_used", 0)
                                st.metric("Context Size", f"{context_used} chars")
                            
                            st.divider()
                            st.subheader("Full Analysis Trace")
                            st.json(analysis)
                        
                        # Add to history
                        st.session_state.messages.append({"role": "assistant", "content": answer})

                except Exception as e:
                    st.error(f"Connection Error: {e}")
                    st.warning("Make sure the API server is running: `python api/server.py`")

with tab2:
    st.header("Admin Dashboard")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Sync Metadata"):
            try:
                payload = {"jsonrpc": "2.0", "method": "sync_metadata", "id": "sync"}
                res = requests.post(API_URL, json=payload)
                data = res.json()
                
                if "error" in data:
                    st.error(f"Sync Failed: {data['error'].get('message', 'Unknown error')}")
                else:
                    result = data.get("result", [])
                    # Ensure result is a list for len() operation
                    if isinstance(result, list):
                        st.success(f"Synced! Found {len(result)} document(s).")
                    else:
                        st.success("Synced!")
                    st.rerun()
            except Exception as e:
                st.error(f"Sync Failed: {e}")

    with col2:
        if st.button("🚀 Process All Pending", type="primary"):
            with st.spinner("Running Ingestion Pipeline..."):
                try:
                    payload = {"jsonrpc": "2.0", "method": "ingest_documents", "id": "ingest"}
                    res = requests.post(API_URL, json=payload).json()
                    
                    if "error" in res:
                        st.error(f"Ingestion Failed: {res['error'].get('message', 'Unknown error')}")
                    else:
                        st.success(res.get("result", {}).get("status", "Done"))
                        st.write(res.get("result", {}).get("details", []))
                        st.rerun()
                except Exception as e:
                    st.error(f"Ingestion Failed: {e}")

    # Fetch Metadata
    try:
        payload = {"jsonrpc": "2.0", "method": "list_metadata", "id": "list"}
        res = requests.post(API_URL, json=payload).json()
        metadata = res.get("result", [])
    except:
        metadata = []
    
    # Display enrichment statistics
    if metadata:
        processed_docs = [d for d in metadata if d.get("status") == "processed"]
        pending_docs = [d for d in metadata if d.get("status") == "pending"]
        
        st.subheader("📈 Document Statistics")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Documents", len(metadata))
        with col2:
            st.metric("Processed", len(processed_docs))
        with col3:
            st.metric("Pending", len(pending_docs))
        with col4:
            # Safely sum chunks_count, handling non-numeric values
            total_chunks = sum(
                chunks 
                for d in processed_docs 
                if isinstance(chunks := d.get("chunks_count"), (int, float))
            )
            st.metric("Total Enriched Chunks", int(total_chunks))
        
        st.divider()

    if metadata:
        # Edit Mode
        for doc in metadata:
            # Enhanced document title with status badge and chunk count
            status = doc.get('status', 'unknown')
            status_emoji = STATUS_EMOJIS.get(status, "❓")
            chunks_count = doc.get('chunks_count')
            
            # Safely display chunk count (handle None and non-numeric values)
            if isinstance(chunks_count, (int, float)) and chunks_count > 0:
                chunks_info = f" - {int(chunks_count)} chunks"
            else:
                chunks_info = ""
            
            with st.expander(f"{status_emoji} {doc['filename']} ({doc['country']}){chunks_info}"):
                # Show enrichment info for processed documents
                if status == "processed" and isinstance(chunks_count, (int, float)) and chunks_count > 0:
                    st.info(f"📚 Document enriched with {int(chunks_count)} chunks containing summaries, keywords, questions, and requirements")
                
                c1, c2, c3 = st.columns(3)
                
                # Safely get index for country selectbox
                current_country = doc.get("country", "Unknown")
                try:
                    country_index = COUNTRY_OPTIONS.index(current_country)
                except ValueError:
                    country_index = COUNTRY_OPTIONS.index("Unknown")
                
                # Safely get index for doc_type selectbox
                current_type = doc.get("doc_type", "Regulation")
                try:
                    type_index = DOC_TYPE_OPTIONS.index(current_type)
                except ValueError:
                    type_index = DOC_TYPE_OPTIONS.index("Regulation")
                
                new_country = c1.selectbox("Country", COUNTRY_OPTIONS, index=country_index, key=f"c_{doc['id']}")
                new_type = c2.selectbox("Type", DOC_TYPE_OPTIONS, index=type_index, key=f"t_{doc['id']}")
                
                if st.button("Save Changes", key=f"save_{doc['id']}"):
                    updates = {"country": new_country, "doc_type": new_type}
                    req = {
                        "jsonrpc": "2.0", 
                        "method": "update_doc_metadata", 
                        "params": {"doc_id": doc['id'], "updates": updates},
                        "id": "update"
                    }
                    requests.post(API_URL, json=req)
                    st.success("Saved!")
                    st.rerun()
    else:
        st.info("No documents found. Click Sync Metadata.")

# ------------------ PDF Tools ------------------
st.markdown("---")
st.header("PDF Tools")

# Fetch metadata for selection
try:
    payload = {"jsonrpc": "2.0", "method": "list_metadata", "id": "list"}
    res = requests.post(API_URL, json=payload).json()
    metadata = res.get("result", [])
except Exception:
    metadata = []

filenames = [d['filename'] for d in metadata] if metadata else []

with st.expander("Summarize a PDF"):
    if not filenames:
        st.info("No documents available. Sync metadata first.")
    else:
        sel = st.selectbox("Select document to summarize", filenames, key="summ_sel")
        user_prompt = st.text_input("Optional prompt (leave empty for generic summary)", key="summ_prompt")
        if st.button("Summarize PDF", key="summarize_pdf"):
            with st.spinner("Summarizing..."):
                try:
                    # 1) download and get local path on server
                    p1 = {"jsonrpc": "2.0", "method": "get_document_content", "params": {"filename": sel}, "id": "getdoc"}
                    r1 = requests.post(API_URL, json=p1).json()
                    file_path = r1.get("result")

                    # 2) read text
                    p2 = {"jsonrpc": "2.0", "method": "read_document_text", "params": {"file_path": file_path}, "id": "readdoc"}
                    r2 = requests.post(API_URL, json=p2).json()
                    text = r2.get("result", "")

                    if not text:
                        st.error("Failed to read document text.")
                    else:
                        q = user_prompt if user_prompt.strip() else f"Summarize the document {sel} and list key requirements and obligations."
                        p3 = {"jsonrpc": "2.0", "method": "summarize_results", "params": {"query": q, "context": text}, "id": "summ"}
                        r3 = requests.post(API_URL, json=p3).json()
                        summary = r3.get("result")
                        if isinstance(summary, dict):
                            st.json(summary)
                        else:
                            st.markdown(summary)
                except Exception as e:
                    st.error(f"Summarization failed: {e}")

with st.expander("Compare two PDFs"):
    if len(filenames) < 2:
        st.info("Need at least two documents to compare.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            a = st.selectbox("Document A", filenames, key="comp_a")
        with col2:
            b = st.selectbox("Document B", filenames, key="comp_b")

        if st.button("Compare PDFs", key="compare_pdfs"):
            if a == b:
                st.warning("Please select two different documents.")
            else:
                with st.spinner("Comparing documents..."):
                    try:
                        # Helper to fetch and read text
                        def fetch_text(fname):
                            p1 = {"jsonrpc": "2.0", "method": "get_document_content", "params": {"filename": fname}, "id": f"get_{fname}"}
                            r1 = requests.post(API_URL, json=p1).json()
                            fp = r1.get("result")
                            p2 = {"jsonrpc": "2.0", "method": "read_document_text", "params": {"file_path": fp}, "id": f"read_{fname}"}
                            r2 = requests.post(API_URL, json=p2).json()
                            return r2.get("result", "")

                        text_a = fetch_text(a)
                        text_b = fetch_text(b)

                        if not text_a or not text_b:
                            st.error("Failed to read one or both documents.")
                        else:
                            compare_prompt = f"Compare the following two regulatory documents. For each, list key requirements, differences, gaps, and suggestions for harmonization.\n\nDocument A:\n{a}\nDocument B:\n{b}"
                            combined_context = f"DOCUMENT_A:\n{text_a}\n\nDOCUMENT_B:\n{text_b}"
                            p4 = {"jsonrpc": "2.0", "method": "summarize_results", "params": {"query": compare_prompt, "context": combined_context}, "id": "compare"}
                            r4 = requests.post(API_URL, json=p4).json()
                            result = r4.get("result")
                            st.markdown(result if isinstance(result, str) else str(result))
                    except Exception as e:
                        st.error(f"Comparison failed: {e}")

