from typing import Any, Dict, Optional
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from mcp import Context
from core.llm.adapter import get_llm


class DocumentAnalyzerAgent:
    def __init__(
        self,
        collection_name: str,
        qdrant_client: QdrantClient,
        context: Context = None,
    ):
        self.collection_name = collection_name
        self.client = qdrant_client
        self.context = Context() if context is None else context

        self.vectorstore = Qdrant(client=self.client, collection_name=self.collection_name)

        # Use adapter to provide a unified LLM interface
        self.llm = get_llm()

    def query_vectorstore(self, query: str, k: int = 3):
        if not self.vectorstore:
            return []

        results = self.vectorstore.similarity_search(query=query, k=k)
        return results

    def answer_query(self, query: str) -> str:
        """Answer a specific query using the most relevant chunk and LLM"""

        if not query.strip():
            return "Query cannot be empty."

        print(f"🔍 Querying Qdrant for: {query}")

        # Retrieve best matching chunk
        response = self.query_vectorstore(query, k=1)

        if not response:
            return "No relevant document chunks found."

        top_doc = response[0]

        # Persist evidence for downstream agents
        if self.context:
            self.context.set("last_query", query)
            self.context.set(
                "last_top_chunk",
                {
                    "summary": top_doc.metadata.get("summary"),
                    "original_text": top_doc.metadata.get("original_text"),
                    "source": top_doc.metadata.get("source"),
                },
            )

        # Extract metadata (unchanged)
        original_text = top_doc.metadata.get("original_text", "")
        summary = top_doc.metadata.get("summary", "")
        keywords = top_doc.metadata.get("keywords", "")
        questions = top_doc.metadata.get("questions", "")

        # ⬇️ PROMPT IS KEPT AS IN README/REQUEST ⬇️
        prompt = f"""
        You are a highly knowledgeable insurance AI assistant with expertise in life, health, and property insurance policies, procedures, and regulations. 
        Your task is to answer the user's query accurately and comprehensively using the document content provided.

        Below you have:

        - **Document Content:** Full text of the relevant insurance document chunk.
        - **Summary:** A concise overview of the chunk key points.
        - **Keywords:** Important insurance terms and concepts from the chunk.
        - **Generated Questions:** Potential questions that this chunk answers.

        Use all of this information to understand the context fully. If the user's query can be answered using the provided information, give a detailed, structured, and professional answer. 
        Include relevant details such as policy conditions, coverage, procedures, and exceptions where applicable. 

        If the information is insufficient to answer the query, clearly state that the answer cannot be determined from the document.

        **Document Content:**
        {original_text}

        **Summary:**
        {summary}

        **Keywords:**
        {keywords}

        **Generated Questions:**
        {questions}

        **User Query:**
        {query}

        **Instructions for Answering:**
        - Prioritize clarity, precision, and relevance to insurance context.
        - Use terminology appropriate for insurance professionals.
        - Provide examples if necessary to illustrate key points.
        - Do not make assumptions beyond the information provided.
        - If multiple interpretations are possible, outline them clearly.

        Provide the answer below:
        """

        response = self.llm.generate(prompt)
        return response


__all__ = ["DocumentAnalyzerAgent"]
