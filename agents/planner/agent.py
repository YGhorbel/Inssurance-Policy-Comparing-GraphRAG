from core.mcp.handler import mcp_registry

# Import all agents to ensure tools are registered
import agents.document_access.agent
import agents.graph_rag.agent
import agents.rag.agent
import agents.analyzer.agent
import agents.summarizer.agent

async def execute_pipeline(query: str) -> dict:
    """
    Orchestrate the multi-agent pipeline to answer a user query.
    """
    print(f"Planner: Processing query: {query}")
    
    # 1. Analyze
    analysis = await mcp_registry.methods["analyze_query"](query=query)
    print(f"Planner Result: {analysis}")
    
    intent = analysis.get("classification", "RAG")
    entities = analysis.get("entities", {})
    region = entities.get("region", [])
    
    context = ""
    
    # 2. Retrieve / Reason
    if intent == "GraphRAG":
        print("Planner: Routing to GraphRAG...")
        # For comparison specifically
        if "compare" in query.lower():
            # Naive extraction of policies to compare if available, else fall back to search
            # Ideally LLM extracts "Regulation A" and "Regulation B"
            # Here we simulate or use RAG to find relevant docs first
            rag_results = await mcp_registry.methods["rag_search"](query=query, top_k=5)
            context += f"GraphRAG/RAG Context: {rag_results}\n"
        else:
             rag_results = await mcp_registry.methods["rag_search"](query=query, top_k=5)
             context += f"GraphRAG Context: {rag_results}\n"
             
    else: # RAG
        print("Planner: Routing to RAG...")
        results = await mcp_registry.methods["rag_search"](query=query, top_k=3)
        context += f"RAG Context: {results}\n"

    # 3. Summarize
    print("Planner: Summarizing...")
    answer = await mcp_registry.methods["summarize_results"](query=query, context=context)
    
    return {
        "answer": answer,
        "analysis": analysis,
        "context_used": len(context)
    }

async def ingest_pending_documents() -> dict:
    """
    Orchestrate the ingestion of all pending documents.
    1. Get Pending Docs
    2. Download & Read
    3. Chunk
    4. Ingest to RAG (Qdrant)
    5. Ingest to GraphRAG (Neo4j)
    6. Update Status
    """
    print("Planner: Starting Ingestion...")
    metadata_list = await mcp_registry.methods["list_metadata"]()
    pending = [d for d in metadata_list if d.get("status") == "pending"]
    
    if not pending:
        return {"status": "No pending documents."}

    results = []
    for doc in pending:
        print(f"Processing {doc['filename']}...")
        try:
            print(f"  - Updating status to processing...")
            await mcp_registry.methods["update_doc_metadata"](doc_id=doc['id'], updates={"status": "processing"})

            # Run the canonical analyzer pipeline: download + chunk + enrich
            # (summary, keywords, questions, requirements, classification) +
            # hybrid BGE-M3 embed + upsert into regulations_chunks_v2. The
            # previous path (chunk_document + rag_ingest_chunks) skipped the
            # enrichment and wrote to a different collection; Subtask B
            # consolidated onto a single analyzer-owned write path.
            print(f"  - Running analyzer pipeline...")
            analyzer_result = await mcp_registry.methods["analyzer.process_document"](object_name=doc['filename'])
            enriched_chunks = analyzer_result.get("enriched_chunks", []) if isinstance(analyzer_result, dict) else []
            print(f"    > Analyzer indexed {len(enriched_chunks)} enriched chunks.")

            print(f"  - Ingesting to Neo4j (GraphRAG)...")
            for i, chunk in enumerate(enriched_chunks):
                if i % 10 == 0:
                    print(f"    > Processing chunk {i+1}/{len(enriched_chunks)}...")
                graph_meta = {
                    "chunk_id": chunk.get("chunk_id"),
                    "filename": chunk.get("source", {}).get("document") or doc['filename'],
                    "country": chunk.get("country") or doc.get('country'),
                    "policy_type": chunk.get("policy_type"),
                    "clause_type": chunk.get("clause_type"),
                    "summary": chunk.get("summary", ""),
                    "keywords": chunk.get("keywords", []),
                    "extracted_requirements": chunk.get("extracted_requirements", []),
                    "source": chunk.get("source", {}),
                }
                await mcp_registry.methods["graph_ingest_chunk"](text=chunk.get("text", ""), metadata=graph_meta)

            print(f"  - Marking as processed...")
            await mcp_registry.methods["update_doc_metadata"](doc_id=doc['id'], updates={"status": "processed", "chunks_count": len(enriched_chunks)})
            results.append(f"Processed {doc['filename']}")

        except Exception as e:
            print(f"Failed {doc['filename']}: {e}")
            await mcp_registry.methods["update_doc_metadata"](doc_id=doc['id'], updates={"status": "error", "error": str(e)})
            results.append(f"Failed {doc['filename']}")

    return {"status": "Ingestion Complete", "details": results}

mcp_registry.register_tool("execute_pipeline", execute_pipeline)
mcp_registry.register_tool("ingest_documents", ingest_pending_documents)
print("Planner Agent initialized.")
