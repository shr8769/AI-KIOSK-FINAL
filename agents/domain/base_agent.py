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

def log_evaluation_trace(
    query: str,
    selected_agent: str,
    selected_domain: str,
    routing_confidence: float,
    selected_doc_id: str,
    retrieved_docs: List[Dict[str, Any]],
    answer: str
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
        self.similarity_threshold = 0.58
        
        if self.rag_enabled:
            self.synthesizer = GeminiSynthesizer()
        
        if client is not None:
            self.client = client
        else:
            if db_path is None:
                # Resolve default path relative to this file
                db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "vectorstore"))
            self.client = chromadb.PersistentClient(path=db_path)
            
        try:
            self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
        except Exception:
            self.emb_fn = None
            
        self.collection = self.client.get_collection(
            name=self.collection_name, 
            embedding_function=self.emb_fn
        )

    def calculate_overlap_score(self, query: str, question: str) -> float:
        """
        Calculates the keyword overlap score (ratio of matching tokens) between the
        query and the retrieved document's question.
        
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
            return {w for w in words if w not in stop_words}
            
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
                answer=fallback_msg
            )
            return f"{fallback_msg}\n\n[Source: None]"
        
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
        
        # Check similarity score against threshold (0.58)
        best_sim_score = 1.0 / (1.0 + best_doc["distance"])
        if best_sim_score < getattr(self, "similarity_threshold", 0.58):
            print(f"[Warning] Similarity score {best_sim_score:.4f} is below threshold {self.similarity_threshold:.2f}. Bypassing LLM generation.")
            log_evaluation_trace(
                query=query,
                selected_agent=self.__class__.__name__,
                selected_domain=self.get_domain(),
                routing_confidence=routing_confidence if routing_confidence is not None else 0.0,
                selected_doc_id="None",
                retrieved_docs=docs,
                answer=fallback_msg
            )
            return f"{fallback_msg}\n\n[Source: None]"
        
        # Log evaluation trace as required by PART 4
        if getattr(self, "rag_enabled", False):
            try:
                # Synthesize answer using Gemini/fallback RAG
                rag_answer = self.synthesizer.synthesize(query, docs, domain=self.get_domain())
                if rag_answer is None:
                    raise ValueError("Gemini RAG synthesis returned None.")
                
                log_evaluation_trace(
                    query=query,
                    selected_agent=self.__class__.__name__,
                    selected_domain=self.get_domain(),
                    routing_confidence=routing_confidence if routing_confidence is not None else 1.0,
                    selected_doc_id=best_doc["id"],
                    retrieved_docs=docs,
                    answer=rag_answer
                )
                # Combine the source references for context docs
                refs = ", ".join(d["id"] for d in docs[:3])
                response = f"{rag_answer}\n\n[Source: {self.get_domain().title().replace('_', ' ')} (RAG Synth) | Refs: {refs}]"
                return response
            except Exception as e:
                print(f"[Warning] Gemini RAG synthesis failed: {e}. Falling back to retrieval-only mode.")
                
        # Retrieval-only mode (fallback or disabled)
        log_evaluation_trace(
            query=query,
            selected_agent=self.__class__.__name__,
            selected_domain=self.get_domain(),
            routing_confidence=routing_confidence if routing_confidence is not None else 1.0,
            selected_doc_id=best_doc["id"],
            retrieved_docs=docs,
            answer=best_doc["answer"]
        )
        response = f"{best_doc['answer']}\n\n[Source: {self.get_domain().title().replace('_', ' ')} | Ref: {best_doc['id']}]"
        return response

    @abstractmethod
    def get_domain(self) -> str:
        """
        Returns the domain/collection name associated with this agent.
        
        Returns:
            str: The name of the domain/collection (e.g., 'admissions').
        """
        pass
