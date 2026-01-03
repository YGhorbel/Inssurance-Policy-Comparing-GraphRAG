from pydoc import doc
import re
from urllib import response
from pypdf import PdfReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import Document
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
import requests
import openai

  
class DocumentAnalyzerAgent:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.full_text = ""
        self.cleaned_text = ""
        self.chunks = []
        self.vectorstore = None
        self.metadatas = []
        self.llm = Ollama(model="llama3:8b", temperature=0.3)
        self.enrichment_time = 0
        
    def clean_text(self, text: str) -> str:
        """
        Lightweight text cleaner to reduce token load by 20-30%
        Removes headers, footers, page numbers, excess whitespace, and formatting artifacts
        """
        # Split into lines and basic cleaning
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        # Remove common PDF artifacts
        cleaned_lines = []
        for line in lines:
            # Skip lines that are likely page numbers
            if line.isdigit() or re.match(r'^Page\s+\d+', line, re.IGNORECASE):
                continue
            
            # Skip lines that are just page headers/footers (common patterns)
            if re.match(r'^(Page|Chapter|\d+\s*$)', line, re.IGNORECASE):
                continue
                
            # Skip lines with mostly special characters or formatting
            if len(re.sub(r'[^\w\s]', '', line)) < 3:
                continue
                
            # Skip repeated header/footer patterns
            if line.lower() in ['table of contents', 'appendix', 'references']:
                continue
                
            # Clean up excessive whitespace and special characters
            line = re.sub(r'\s+', ' ', line)  # Multiple spaces to single space
            line = re.sub(r'[^\w\s.,;:!?()-]', '', line)  # Remove unusual special chars
            
            # Skip very short lines that are likely artifacts
            if len(line.split()) >= 3:  # Keep lines with at least 3 words
                cleaned_lines.append(line)
        
        # Join lines and additional cleaning
        cleaned_text = " ".join(cleaned_lines)
        
        # Remove table artifacts and repeated patterns
        cleaned_text = self._remove_table_artifacts(cleaned_text)
        cleaned_text = self._remove_repeated_patterns(cleaned_text)
        
        # Final cleanup
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        return cleaned_text
    
    def _remove_table_artifacts(self, text: str) -> str:
        """Remove common table formatting artifacts"""
        # Remove patterns like "| | |" or "--- ---"
        text = re.sub(r'\|[\s\|]*\|', ' ', text)
        text = re.sub(r'[-=]{3,}', ' ', text)
        text = re.sub(r'_{3,}', ' ', text)
        return text
    
    def _remove_repeated_patterns(self, text: str) -> str:
        """Remove obviously repeated header/footer content"""
        words = text.split()
        if len(words) < 10:
            return text
            
        # Simple approach: if same phrase appears >3 times, it's likely header/footer
        word_counts = {}
        for i in range(len(words) - 2):
            phrase = " ".join(words[i:i+3])
            word_counts[phrase] = word_counts.get(phrase, 0) + 1
        
        # Remove phrases that appear too frequently (likely headers/footers)
        for phrase, count in word_counts.items():
            if count > 3:
                text = text.replace(phrase, " ")
        
        return re.sub(r'\s+', ' ', text).strip()

    def extract_text_with_pypdf2(self, pdf_path: str) -> str:
        """Extract text from PDF using pypdf"""
        reader = PdfReader(pdf_path)
        text = "".join([page.extract_text() or "" for page in reader.pages])
        print(f"Extracted {len(text)} characters")
        return text

    def chunk_text(self, text: str, chunk_size=2500, chunk_overlap=300):
        """Chunk text using sentence splitter"""
        document = Document(text=text)
        splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        nodes = splitter.get_nodes_from_documents([document])
        chunks = [node.text for node in nodes]
        print(f"Created {len(chunks)} chunks")
        return chunks

    def enrich_chunk_with_llama(self, chunk, llm):
        """Use LLaMA to generate all enrichments for a single chunk"""
        combined_prompt = PromptTemplate(
            input_variables=["text"],
            template="""Analyze the following document text and provide:

{text}

Please respond in this exact format:
SUMMARY: [Summarize the following insurance text in 2-3 sentences, focusing on key points and main topics]
KEYWORDS: [Extract 5-7 key insurance terms and concepts from this text. Return only the keywords separated by commas]
QUESTIONS: [Generate 3 hypothetical questions that this insurance text could answer. Return questions separated by newlines]

Response:"""
        )
        
        try:
            response = llm.invoke(combined_prompt.format(text=chunk))
            response_text = response.strip() if hasattr(response, 'strip') else str(response).strip()
            
            # Parse the combined response
            summary = ""
            keywords = ""
            questions = ""
            
            lines = response_text.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                if line.startswith('SUMMARY:'):
                    current_section = 'summary'
                    summary = line.replace('SUMMARY:', '').strip()
                elif line.startswith('KEYWORDS:'):
                    current_section = 'keywords'
                    keywords = line.replace('KEYWORDS:', '').strip()
                elif line.startswith('QUESTIONS:'):
                    current_section = 'questions'
                    questions = line.replace('QUESTIONS:', '').strip()
                elif current_section and line:
                    if current_section == 'summary':
                        summary += " " + line
                    elif current_section == 'keywords':
                        keywords += " " + line
                    elif current_section == 'questions':
                        questions += "\n" + line
            
            return {
                "summary": summary.strip() or "Summary not available",
                "keywords": keywords.strip() or "No keywords extracted", 
                "questions": questions.strip() or "No questions generated"
            }
            
        except Exception as e:
            print(f"Error enriching chunk: {e}")
            return {
                "summary": "Summary not available",
                "keywords": "No keywords extracted",
                "questions": "No questions generated"
            }

    def process_document(self, doc_id="insurance_doc_001"):
        """Complete pipeline: extract, chunk, enrich (parallelized), and store in vector DB"""

        # Step 1: Extract text
        self.full_text = self.extract_text_with_pypdf2(self.pdf_path)

        # Step 2: Clean text
        self.cleaned_text = self.clean_text(self.full_text)

        # Show preprocessing stats
        original_chars = len(self.full_text)
        cleaned_chars = len(self.cleaned_text)
        reduction_percent = ((original_chars - cleaned_chars) / original_chars) * 100
        print(f"   Original: {original_chars:,} characters")
        print(f"   Cleaned: {cleaned_chars:,} characters")
        print(f"   Reduction: {reduction_percent:.1f}%")

        # Step 3: Chunk the text
        self.chunks = self.chunk_text(self.cleaned_text, chunk_size=2000, chunk_overlap=200)

        start_time = time.time()
        texts_for_embedding = []
        metadata_list = []

        print(f"🚀 Enriching {len(self.chunks)} chunks in parallel...")
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(self.enrich_chunk_with_llama, chunk, self.llm): idx
                for idx, chunk in enumerate(self.chunks)
            }

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    enrichment = future.result()
                except Exception as e:
                    print(f"⚠️ Error processing chunk {idx}: {e}")
                    enrichment = {
                        "summary": "Summary not available",
                        "keywords": "No keywords extracted",
                        "questions": "No questions generated"
                    }

                chunk = self.chunks[idx]

                # Metadata dict for this chunk
                meta = {
                    "doc_id": doc_id,
                    "chunk_id": f"{doc_id}_chunk_{idx}",
                    "chunk_index": idx,
                    "original_text": chunk,
                    "summary": enrichment["summary"],
                    "keywords": enrichment["keywords"],
                    "questions": enrichment["questions"]
                }

                # Text to embed: combine summary + keywords + questions + original_text
                text_for_embedding = (
                    f"Summary: {enrichment['summary']}\n"
                    f"Keywords: {enrichment['keywords']}\n"
                    f"Questions: {enrichment['questions']}\n"
                    f"Original Text: {chunk}"
                )

                texts_for_embedding.append(text_for_embedding)
                metadata_list.append(meta)

        end_time = time.time()
        self.enrichment_time = end_time - start_time
        print(f"🏁 Parallel enrichment completed in {self.enrichment_time:.2f} seconds")

        # Step 4: Create embeddings and FAISS vector store
        print("\n🔍 Creating vector store...")
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

        self.vectorstore = FAISS.from_texts(
            texts=texts_for_embedding,  # Texts for embedding
            embedding=embeddings,
            metadatas=metadata_list      # Store the structured metadata separately
        )

        self.metadatas = metadata_list

        print("✅ Vector store created successfully!")
        return self.vectorstore, self.metadatas


    def query_vectorstore(self, query: str, k: int = 3):
        """
        Query the vector store and return relevant chunks.
        """
        if not self.vectorstore:
            return []

        results = self.vectorstore.similarity_search(query, k=k)
        return results

    def answer_query(self, query: str) -> str:
        """Answer a specific query using the most relevant chunk and LLM for better output"""
        if not self.vectorstore:
            return "Please process a document first."
        if not query.strip():
            return "Query cannot be empty." 

        print(f"🔍 Querying vector store for: {query}")
        
        # Get top relevant chunk
        response = self.query_vectorstore(query, k=1)
        top_doc = response[0]

        # Now you can access metadata
        original_text = top_doc.metadata.get("original_text", "")
        summary = top_doc.metadata.get("summary", "")
        keywords = top_doc.metadata.get("keywords", "")
        questions = top_doc.metadata.get("questions", "")

        # Create the output prompt

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
        response = self.llm.invoke(prompt)
        return response
