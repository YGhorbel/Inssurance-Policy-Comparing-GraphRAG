import streamlit as st
import requests
import uuid

st.set_page_config(page_title="Tunisian Insurance Legal Assistant", layout="wide")

API_URL = "http://localhost:8000/mcp"

st.title("🤖 Legal & Regulatory Multi-Agent Assistant")
st.markdown("*Architecture: LiquidAI LFM2-2.6B + Qdrant + Neo4j + MinIO (Orchestrated via MCP)*")

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
                        
                        with st.expander("Agent Reasoning (Trace)"):
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
                requests.post(API_URL, json=payload)
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

    if metadata:
        # Edit Mode
        for doc in metadata:
            with st.expander(f"{doc['filename']} ({doc['country']}) - {doc['status']}"):
                c1, c2, c3 = st.columns(3)
                new_country = c1.selectbox("Country", ["Tunisia", "Europe", "France", "Unknown"], index=["Tunisia", "Europe", "France", "Unknown"].index(doc.get("country", "Unknown")), key=f"c_{doc['id']}")
                new_type = c2.selectbox("Type", ["Regulation", "Law", "Guideline"], index=["Regulation", "Law", "Guideline"].index(doc.get("doc_type", "Regulation")), key=f"t_{doc['id']}")
                
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

