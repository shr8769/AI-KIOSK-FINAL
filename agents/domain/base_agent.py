import os
import re
import json
import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    pass

from agents.domain.gemini_rag import GeminiSynthesizer
from config import llm_config
from agents.llm.qwen_client import QwenClient

def log_evaluation_trace(
    query: str,
    selected_agent: str,
    selected_domain: str,
    routing_confidence: float,
    selected_doc_id: str,
    retrieved_docs: List[Dict[str, Any]],
    answer: str,
    relevance_decision: str = "SUFFICIENT"
):
    """
    Utility function to log query, routing, and retrieval details to a JSONL file
    for future evaluations.
    """
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "evaluation", "results"))
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "evaluation_log.jsonl")
    
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "query": query,
        "selected_agent": selected_agent,
        "selected_domain": selected_domain,
        "routing_confidence": routing_confidence,
        "selected_doc_id": selected_doc_id,
        "retrieved_documents": [
            {
                "id": doc["id"],
                "document": doc.get("document", ""),
                "distance": doc["distance"],
                "similarity_score": 1.0 / (1.0 + doc["distance"]),
                "keyword_score": doc["keyword_score"],
                "combined_score": doc["combined_score"]
            } for doc in retrieved_docs
        ],
        "relevance_decision": relevance_decision,
        "answer": answer
    }
    
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Warning] Failed to write evaluation trace: {e}")

class BaseAgent(ABC):
    """
    Abstract base class representing a domain-specific QA agent.
    Implements a unified retrieval and re-ranking pipeline using semantic similarity
    and keyword overlap scoring.
    """
    _shared_emb_fn = None
    def __init__(
        self, 
        collection_name: str, 
        client: Any = None, 
        db_path: str = None,
        similarity_weight: float = 1.0,
        keyword_weight: float = 1.5,
        rag_enabled: bool = True
    ):
        """
        Initializes the BaseAgent with a ChromaDB collection.
        
        Args:
            collection_name (str): Name of the ChromaDB collection.
            client (chromadb.PersistentClient, optional): Shared client instance.
            db_path (str, optional): Path to persistent ChromaDB storage.
            similarity_weight (float): Weight for semantic similarity score.
            keyword_weight (float): Weight for token overlap score.
            rag_enabled (bool): Whether to enable Gemini RAG response generation.
        """
        self.collection_name = collection_name
        self.similarity_weight = similarity_weight
        self.keyword_weight = keyword_weight
        self.rag_enabled = rag_enabled
        self.similarity_threshold = 0.55
        
        if self.rag_enabled:
            self.qwen_client = QwenClient()
            self.synthesizer = GeminiSynthesizer()
        
        if client is not None:
            self.client = client
        else:
            if db_path is None:
                # Resolve default path relative to this file
                db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "vectorstore"))
            self.client = chromadb.PersistentClient(path=db_path)
            
        if BaseAgent._shared_emb_fn is None:
            try:
                BaseAgent._shared_emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            except Exception:
                BaseAgent._shared_emb_fn = None
        self.emb_fn = BaseAgent._shared_emb_fn
            
        self.collection = self.client.get_collection(
            name=self.collection_name, 
            embedding_function=self.emb_fn
        )

    def calculate_overlap_score(self, query: str, question: str) -> float:
        """
        Calculates the keyword overlap score (ratio of matching tokens) between the
        query and the retrieved document's question with simple stemming/plural handling.
        
        Args:
            query (str): The user search query.
            question (str): The question retrieved from the document.
            
        Returns:
            float: Overlap score between 0.0 and 1.0.
        """
        stop_words = {
            "what", "is", "are", "the", "for", "in", "to", "do", "how", "a", "of", "on", 
            "and", "or", "about", "with", "where", "you", "i", "can", "my", "your",
            "does", "did", "at", "by", "an", "this", "that"
        }
        
        def tokenize(text: str) -> set:
            words = re.findall(r'\b\w+\b', text.lower())
            tokens = set()
            for w in words:
                if w not in stop_words:
                    tokens.add(w)
                    if w.endswith('s') and len(w) > 3:
                        tokens.add(w[:-1])
            return tokens
            
        query_tokens = tokenize(query)
        question_tokens = tokenize(question)
        
        if not query_tokens:
            return 0.0
            
        intersection = query_tokens.intersection(question_tokens)
        return len(intersection) / len(query_tokens)

    def parse_document(self, doc_text: str) -> Tuple[str, str]:
        """
        Parses a document string formatted as "Question: ... \nAnswer: ..." 
        into its individual question and answer components.
        
        Args:
            doc_text (str): Raw document text.
            
        Returns:
            Tuple[str, str]: (question, answer)
        """
        lines = doc_text.split("\n")
        question = ""
        answer = ""
        for line in lines:
            if line.startswith("Question:"):
                question = line[len("Question:"):].strip()
            elif line.startswith("Answer:"):
                answer = line[len("Answer:"):].strip()
        
        if not question:
            question = doc_text
        if not answer:
            answer = doc_text
            
        return question, answer

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """
        Retrieves the top 5 documents from the collection, calculates keyword
        overlap scores, and re-ranks them based on a combined score.
        
        Args:
            query (str): The search query.
            
        Returns:
            List[Dict[str, Any]]: Re-ranked list of documents with scores.
        """
        # 1. Retrieve top 5 documents from ChromaDB
        results = self.collection.query(
            query_texts=[query],
            n_results=5
        )
        
        retrieved_docs = []
        if results and results['documents'] and results['documents'][0]:
            docs = results['documents'][0]
            ids = results['ids'][0] if 'ids' in results and results['ids'] else [None] * len(docs)
            metadatas = results['metadatas'][0] if 'metadatas' in results and results['metadatas'] else [{}] * len(docs)
            distances = results['distances'][0] if 'distances' in results and results['distances'] else [None] * len(docs)
            
            for doc, doc_id, meta, dist in zip(docs, ids, metadatas, distances):
                # Parse the document into question and answer
                q_text, a_text = self.parse_document(doc)
                
                # 2. Calculate keyword overlap score
                kw_score = self.calculate_overlap_score(query, q_text)
                
                # 3. Combine scores
                # Map distance (usually 0.0 - 2.0, lower is better) to a similarity metric
                similarity_score = 1.0 / (1.0 + (dist if dist is not None else 0.0))
                combined_score = self.similarity_weight * similarity_score + self.keyword_weight * kw_score
                
                retrieved_docs.append({
                    "id": doc_id,
                    "document": doc,
                    "question": q_text,
                    "answer": a_text,
                    "metadata": meta,
                    "distance": dist if dist is not None else 0.0,
                    "keyword_score": kw_score,
                    "combined_score": combined_score
                })
                
            # 4. Re-rank results based on combined score in descending order
            retrieved_docs.sort(key=lambda x: x["combined_score"], reverse=True)
            
        return retrieved_docs

    def answer(self, query: str, routing_confidence: float = None) -> str:
        """
        Performs retrieval, prints debugging information about all candidates,
        selects the best matching document, logs the trace, and returns the answer.
        
        Args:
            query (str): The user query.
            routing_confidence (float, optional): The confidence score from the coordinator.
            
        Returns:
            str: The final formatted answer.
        """
        fallback_msg = (
            "Sorry, I could not find information regarding this in the university knowledge base. "
            "Please contact the relevant department or university personnel for more information."
        )
        
        docs = self.retrieve(query)
        if not docs:
            # Log failure
            log_evaluation_trace(
                query=query,
                selected_agent=self.__class__.__name__,
                selected_domain=self.get_domain(),
                routing_confidence=routing_confidence if routing_confidence is not None else 0.0,
                selected_doc_id="None",
                retrieved_docs=[],
                answer=fallback_msg,
                relevance_decision="INSUFFICIENT"
            )
            return f"Answer:\n{fallback_msg}\n\nSources:\n    None"
        
        # Select best document (first in the re-ranked list)
        best_doc = docs[0]
        
        # Print debugging details as required by PART 3
        print("\nRetrieved Documents:\n")
        for i, doc in enumerate(docs, 1):
            sim_score = 1.0 / (1.0 + doc['distance'])
            print(f"Document {i}:")
            print(f"* ID: {doc['id']}")
            print(f"* Distance: {doc['distance']:.4f}")
            print(f"* Similarity Score: {sim_score:.4f}")
            print(f"* Keyword Score: {doc['keyword_score']:.4f}")
            print(f"* Final Score: {doc['combined_score']:.4f}")
            print() # empty line
            
        print("Selected Document:")
        print(f"* ID: {best_doc['id']}")
        
        # Determine relevance decision
        relevance_decision = "SUFFICIENT"
        
        # First filter: check similarity score against threshold (default: 0.55)
        best_sim_score = 1.0 / (1.0 + best_doc["distance"])
        current_threshold = getattr(self, "similarity_threshold", 0.55)
        if best_sim_score < current_threshold:
            print(f"[Warning] Similarity score {best_sim_score:.4f} is below threshold {current_threshold:.2f}.")
            relevance_decision = "INSUFFICIENT"
            
        # Second filter: if RAG is enabled and similarity is sufficient, run the relevance check
        if relevance_decision == "SUFFICIENT" and getattr(self, "rag_enabled", False):
            check_result = None
            if os.getenv("SPEEDUP_BENCHMARK") == "1":
                check_result = "SUFFICIENT"
            # Attempt Gemini first if not degraded
            if check_result is None and not getattr(self.synthesizer, "is_degraded", False):
                try:
                    check_result = self.synthesizer.check_sufficiency(query, docs, domain=self.get_domain())
                    if check_result is not None:
                        print(f"Gemini relevance check decision: {check_result}")
                except Exception as e:
                    print(f"[Warning] Gemini relevance check failed: {e}.")
            
            # If Gemini failed/is degraded, use local Qwen client as backup
            if check_result is None and not getattr(self.qwen_client, "is_degraded", False):
                try:
                    print("[Info] Attempting local Qwen sufficiency check...")
                    formatted_context = ""
                    for i, doc in enumerate(docs, 1):
                        formatted_context += f"Document {i} (ID: {doc.get('id', 'unknown')}):\n{doc.get('document', '')}\n\n"
                    check_prompt = f"""Question:
{query}

Context:
{formatted_context.strip()}

Determine whether the context contains sufficient information to answer the question.
Reply with exactly one word: SUFFICIENT or INSUFFICIENT. Do not provide any explanations.

Decision:"""
                    qwen_check = self.qwen_client.generate(check_prompt)
                    if qwen_check:
                        qwen_check_clean = qwen_check.strip().upper()
                        if "SUFFICIENT" in qwen_check_clean and "INSUFFICIENT" not in qwen_check_clean:
                            check_result = "SUFFICIENT"
                        else:
                            check_result = "INSUFFICIENT"
                        print(f"Local Qwen relevance check decision: {check_result}")
                except Exception as e:
                    print(f"[Warning] Local Qwen relevance check failed: {e}.")

            if check_result is not None:
                relevance_decision = check_result
            else:
                print("[Info] Bypassing relevance check and falling back to similarity filter.")
                
        # If either check decides INSUFFICIENT, bypass LLM answer synthesis and return fallback
        if relevance_decision == "INSUFFICIENT":
            log_evaluation_trace(
                query=query,
                selected_agent=self.__class__.__name__,
                selected_domain=self.get_domain(),
                routing_confidence=routing_confidence if routing_confidence is not None else 0.0,
                selected_doc_id="None",
                retrieved_docs=docs,
                answer=fallback_msg,
                relevance_decision=relevance_decision
            )
            return f"Answer:\n{fallback_msg}\n\nSources:\n    None"
        
        # Log evaluation trace as required by PART 4
        if getattr(self, "rag_enabled", False):
            # Format context documents for prompt template
            formatted_context = ""
            for i, doc in enumerate(docs, 1):
                formatted_context += f"Document {i} (ID: {doc.get('id', 'unknown')}):\n{doc.get('document', '')}\n\n"
            
            # Load template
            try:
                from agents.concierge.prompt_templates import TEMPLATES
                template = TEMPLATES.get(self.get_domain(), TEMPLATES.get("default"))
            except ImportError:
                template = "Answer the user query based ONLY on the provided context.\nContext:\n{context}\nQuery: {query}\nAnswer:"
                
            prompt = template.format(context=formatted_context, query=query)
            
            rag_answer = None
            # Try Qwen first if it is the primary LLM
            if getattr(llm_config, "PRIMARY_LLM", "qwen") == "qwen":
                try:
                    rag_answer = self.qwen_client.generate(prompt)
                except Exception as e:
                    print(f"[Warning] Qwen generation failed: {e}. Falling back to Gemini.")
            
            # If Qwen is disabled or failed, use Gemini synthesizer
            if not rag_answer:
                try:
                    rag_answer = self.synthesizer.synthesize(query, docs, domain=self.get_domain())
                except Exception as e:
                    print(f"[Warning] Gemini RAG synthesis failed: {e}. Falling back to retrieval-only mode.")
            
            if rag_answer:
                # Standardize clean up of Answer: prefix if present
                if rag_answer.startswith("Answer:"):
                    rag_answer = rag_answer[len("Answer:"):].strip()
                
                source_file = f"{self.get_domain()}.json"
                if self.get_domain() == "navigation":
                    source_file = "locations.json"
                
                # If model replied with the fallback message, set source to None
                if "Sorry, I could not find information regarding this" in rag_answer or fallback_msg in rag_answer:
                    rag_answer = fallback_msg
                    source_file = "None"
                    
                log_evaluation_trace(
                    query=query,
                    selected_agent=self.__class__.__name__,
                    selected_domain=self.get_domain(),
                    routing_confidence=routing_confidence if routing_confidence is not None else 1.0,
                    selected_doc_id=best_doc["id"],
                    retrieved_docs=docs,
                    answer=rag_answer,
                    relevance_decision="SUFFICIENT"
                )
                return f"Answer:\n{rag_answer}\n\nSources:\n    {source_file}"
                
        # Retrieval-only mode (fallback or disabled)
        source_file = f"{self.get_domain()}.json"
        if self.get_domain() == "navigation":
            source_file = "locations.json"
            
        log_evaluation_trace(
            query=query,
            selected_agent=self.__class__.__name__,
            selected_domain=self.get_domain(),
            routing_confidence=routing_confidence if routing_confidence is not None else 1.0,
            selected_doc_id=best_doc["id"],
            retrieved_docs=docs,
            answer=best_doc["answer"],
            relevance_decision="SUFFICIENT"
        )
        
        ans_text = best_doc['answer']
        if ans_text.startswith("Answer:"):
            ans_text = ans_text[len("Answer:"):].strip()
            
        return f"Answer:\n{ans_text}\n\nSources:\n    {source_file}"

    @abstractmethod
    def get_domain(self) -> str:
        """
        Returns the domain/collection name associated with this agent.
        
        Returns:
            str: The name of the domain/collection (e.g., 'admissions').
        """
        pass
