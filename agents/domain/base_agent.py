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

def consolidate_faqs(knowledge_dir: str):
    """
    Consolidates the separate domain FAQ and locations files into a single faq.json
    located in the knowledge folder, matching the user's specification.
    """
    sources_dir = os.path.join(knowledge_dir, "sources")
    faq_file = os.path.join(knowledge_dir, "faq.json")
    
    file_map = {
        "admissions": os.path.join("admissions", "faq.json"),
        "academics": os.path.join("academics", "faq.json"),
        "placements": os.path.join("placements", "faq.json"),
        "research": os.path.join("research", "faq.json"),
        "student_services": os.path.join("student_services", "faq.json"),
        "navigation": os.path.join("navigation", "locations.json"),
    }
    
    consolidated = []
    
    for domain, rel_path in file_map.items():
        src_path = os.path.join(sources_dir, rel_path)
        if not os.path.exists(src_path):
            continue
            
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            if domain == "navigation":
                for idx, item in enumerate(data):
                    facility = item.get("facility", "")
                    building = item.get("building", "")
                    floor = item.get("floor", "")
                    landmark = item.get("landmark", "")
                    directions = item.get("directions", "")
                    
                    question = f"Where is the {facility}?"
                    answer = f"The {facility} is located in {building} on the {floor} (landmark: {landmark}). Directions: {directions}"
                    
                    consolidated.append({
                        "id": f"navigation_{idx}",
                        "source": "navigation",
                        "topic": facility,
                        "question": question,
                        "answer": answer
                    })
            else:
                for idx, item in enumerate(data):
                    consolidated.append({
                        "id": item.get("id") or f"{domain}_{idx}",
                        "source": domain,
                        "topic": item.get("topic", ""),
                        "question": item.get("question", ""),
                        "answer": item.get("answer", "")
                    })
        except Exception as e:
            print(f"[Warning] Failed to read {src_path} during consolidation: {e}")
            
    try:
        with open(faq_file, "w", encoding="utf-8") as f:
            json.dump(consolidated, f, indent=4, ensure_ascii=False)
        print(f"[Info] Successfully created consolidated faq.json with {len(consolidated)} items.")
    except Exception as e:
        print(f"[Error] Failed to write consolidated faq.json: {e}")


def stem_token(word: str) -> str:
    """
    Simple suffix stripping to handle basic plurals and inflections in English.
    """
    if word.endswith("sses"):
        return word[:-2]
    elif word.endswith("ies"):
        return word[:-3] + "y"
    elif word.endswith("es") and len(word) > 4:
        return word[:-2]
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 2:
        return word[:-1]
    elif word.endswith("ing") and len(word) > 5:
        return word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        return word[:-2]
    return word


def tokenize_text(text: str) -> set:
    """
    Tokenizes, lowercases, filters stop words, and stems input text.
    """
    if not text:
        return set()
    stop_words = {
        "what", "is", "are", "the", "for", "in", "to", "do", "how", "a", "of", "on", 
        "and", "or", "about", "with", "where", "you", "i", "can", "my", "your",
        "does", "did", "at", "by", "an", "this", "that"
    }
    words = re.findall(r'\b\w+\b', text.lower())
    return {stem_token(w) for w in words if w not in stop_words}

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
            
        try:
            self.collection = self.client.get_collection(
                name=self.collection_name,
                embedding_function=self.emb_fn
            )
        except Exception:
            # Collection doesn't exist yet (Gowtham hasn't run ingestion).
            # Agent will run in FAQ-only mode using faq.json keyword retrieval.
            self.collection = None
            print(f"[Warning] ChromaDB collection '{self.collection_name}' not found. Running in FAQ-only mode.")


        # Resolve path to the consolidated faq.json in the knowledge directory
        knowledge_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge"))
        faq_file = os.path.join(knowledge_dir, "faq.json")
        
        # Ensure the consolidated faq.json exists, otherwise generate it
        if not os.path.exists(faq_file):
            consolidate_faqs(knowledge_dir)
            
        self.source_file = faq_file
        self.data = []
        if os.path.exists(faq_file):
            try:
                with open(faq_file, "r", encoding="utf-8") as f:
                    all_data = json.load(f)
                # Filter by source domain
                self.data = [item for item in all_data if item.get("source") == collection_name]
            except Exception as e:
                print(f"[Warning] Failed to load consolidated faq.json {faq_file}: {e}")

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
        Retrieves the top 5 documents from the collection by matching the user query 
        keywords against 'topic' and 'question' fields in the source JSON files.
        Falls back to ChromaDB semantic similarity search if keyword matching returns no results.
        
        Args:
            query (str): The search query.
            
        Returns:
            List[Dict[str, Any]]: Re-ranked list of documents with scores.
        """
        query_tokens = tokenize_text(query)
        retrieved_docs = []
        
        if query_tokens and self.data:
            for idx, item in enumerate(self.data):
                topic_text = item.get("topic", "")
                question_text = item.get("question", "")
                answer_text = item.get("answer", "")
                item_id = item.get("id") or f"{self.collection_name}_{idx}"
                    
                # Tokenize topic and question using new stemming tokenizer
                topic_tokens = tokenize_text(topic_text)
                question_tokens = tokenize_text(question_text)
                
                # Calculate match overlaps
                topic_match = len(query_tokens.intersection(topic_tokens))
                question_match = len(query_tokens.intersection(question_tokens))
                
                # Calculate score: weight topic match higher (2.0) and question match (1.0)
                combined_score = (topic_match * 2.0) + (question_match * 1.0)

                
                # Keep only items that have at least some match
                if combined_score > 0:
                    retrieved_docs.append({
                        "id": item_id,
                        "document": f"Topic: {topic_text}\nQuestion: {question_text}\nAnswer: {answer_text}",
                        "question": question_text,
                        "answer": answer_text,
                        "metadata": {"category": self.collection_name, "topic": topic_text},
                        "distance": 0.0,
                        "keyword_score": combined_score,
                        "combined_score": combined_score
                    })
                    
            # Re-rank based on combined_score descending
            retrieved_docs.sort(key=lambda x: x["combined_score"], reverse=True)
        
        # If nothing matched via keyword overlap, fall back to ChromaDB query
        if not retrieved_docs and self.collection is not None:

            try:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=5
                )
                if results and results['documents'] and results['documents'][0]:
                    docs = results['documents'][0]
                    ids = results['ids'][0] if 'ids' in results and results['ids'] else [None] * len(docs)
                    metadatas = results['metadatas'][0] if 'metadatas' in results and results['metadatas'] else [{}] * len(docs)
                    distances = results['distances'][0] if 'distances' in results and results['distances'] else [None] * len(docs)
                    
                    for doc, doc_id, meta, dist in zip(docs, ids, metadatas, distances):
                        q_text, a_text = self.parse_document(doc)
                        kw_score = self.calculate_overlap_score(query, q_text)
                        similarity_score = 1.0 / (1.0 + (dist if dist is not None else 0.0))
                        comb_score = similarity_score + kw_score
                        
                        retrieved_docs.append({
                            "id": doc_id,
                            "document": doc,
                            "question": q_text,
                            "answer": a_text,
                            "metadata": meta,
                            "distance": dist if dist is not None else 0.0,
                            "keyword_score": kw_score,
                            "combined_score": comb_score
                        })
                    retrieved_docs.sort(key=lambda x: x["combined_score"], reverse=True)
            except Exception:
                pass
                
        return retrieved_docs[:5]

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
        
        # Determine relevance decision
        relevance_decision = "SUFFICIENT"
        
        # First filter: check similarity score against threshold (0.58)
        best_sim_score = 1.0 / (1.0 + best_doc["distance"])
        if best_sim_score < getattr(self, "similarity_threshold", 0.58):
            print(f"[Warning] Similarity score {best_sim_score:.4f} is below threshold {self.similarity_threshold:.2f}.")
            relevance_decision = "INSUFFICIENT"
            
        # Second filter: if RAG is enabled and similarity is sufficient, run the Gemini relevance check
        if relevance_decision == "SUFFICIENT" and getattr(self, "rag_enabled", False):
            try:
                check_result = self.synthesizer.check_sufficiency(query, docs, domain=self.get_domain())
                if check_result is not None:
                    relevance_decision = check_result
                    print(f"Gemini relevance check decision: {relevance_decision}")
            except Exception as e:
                print(f"[Warning] Gemini relevance check failed: {e}. Falling back to similarity filter.")
                
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
                    answer=rag_answer,
                    relevance_decision="SUFFICIENT"
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
            answer=best_doc["answer"],
            relevance_decision="SUFFICIENT"
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
