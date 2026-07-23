import os
import re
import json
import datetime
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

SYNONYMS = {
    "documents": {"documents", "document", "certificate", "certificates", "marks", "card", "cards", "receipt", "receipts", "records", "pan", "aadhar", "order", "original", "reporting"},
    "pessat": {"pessat", "entrance", "test", "process", "merit"},
    "kcet": {"kcet", "cet", "kea"},
    "fees": {"fees", "fee", "cost", "payment", "tuition"},
    "scholarship": {"scholarship", "scholarships", "aid", "loyalty", "mrd"},
    "eligibility": {"eligibility", "eligible", "criteria", "requirements", "requirement"},
    "hostel": {"hostel", "hostels", "mess", "boarding", "accommodation"},
    "required": {"required", "require", "mandatory", "necessary"}
}

STOP_WORDS = {
    "what", "is", "are", "the", "for", "in", "to", "do", "how", "a", "of", "on", 
    "and", "or", "about", "with", "where", "you", "i", "can", "my", "your",
    "does", "did", "at", "by", "an", "this", "that", "through", "under", "from", 
    "within", "via", "during", "after", "before", "out", "all", "any", "both", 
    "each", "few", "more", "most", "other", "some", "such", "than", "too", "very", 
    "can", "will", "should", "would", "could", "may", "might", "must", "get", 
    "got", "make", "made", "take", "took", "use", "used", "using", "about", "please",
    "regarding", "which", "who", "whom", "whose", "why"
}

def normalize_word(w: str) -> str:
    w = w.lower().strip()
    # Normalize common program acronyms to allow consistent matching
    w = w.replace("b.tech", "btech").replace("m.tech", "mtech")
    w = w.replace("b.sc", "bsc").replace("m.sc", "msc")
    w = w.replace("ph.d", "phd").replace("ll.m", "llm")
    if w.endswith('s') and len(w) > 3:
        w = w[:-1]
    return w



try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    pass

from agents.domain.gemini_rag import GeminiSynthesizer
from config import llm_config
from agents.llm.qwen_client import QwenClient
from config.contact_config import get_specific_contact, format_fallback_message

def log_evaluation_trace(
    query: str,
    selected_agent: str,
    selected_domain: str,
    routing_confidence: float,
    selected_doc_id: str,
    retrieved_docs: List[Dict[str, Any]],
    answer: str,
    relevance_decision: str = "SUFFICIENT",
    confidence_score: float = 0.0,
    fallback_used: bool = False
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
        "confidence_score": confidence_score,
        "fallback_used": fallback_used,
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
        logger.warning(f"Failed to write evaluation trace: {e}")


def get_natural_source_attribution(metadata: Dict[str, Any]) -> str:
    """
    Returns a user-friendly natural name for the source based on metadata.
    """
    category = str(metadata.get("category", "")).lower().strip()
    doc_name = str(metadata.get("document_name", "")).lower().strip()
    
    mapping = {
        "admissions": "the official PES University Admissions page",
        "scholarships": "the PES University Scholarships details",
        "orientation": "the PES Orientation guidelines",
        "important_dates": "the official PES Academic Admissions calendar",
        "government_sources": "the official admissions board guidelines (COMEDK/KCET)",
        "programs": "the PES University Academic Programs catalog",
        "departments": "the PES University Academic Departments directory",
        "academic_calendar": "the official PES Academic Calendar",
        "placements": "the PES Placements Office statistics",
        "research": "the PES Research Office publications",
        "hostels": "the PES Hostel Administration records",
        "hostel": "the PES Hostel Administration records",
        "transportation": "the PES Transportation Department schedule",
        "student_services": "the PES Student Services handbook",
        "library": "the PES Central Library records",
        "events": "the PES Campus Events directory",
        "campus_life": "the PES Campus Life portal",
        "student_support": "the PES Student Support Services",
        "clubs": "the PES Student Clubs directory",
        "campus_facilities": "the PES Campus Facilities guidelines",
        "campus_maps": "the official PES Campus Map",
        "navigation": "the PES Campus Navigation directory",
        "general": "the official PES University info portal"
    }
    
    attribution = mapping.get(category)
    if not attribution:
        for key, val in mapping.items():
            if key in doc_name:
                attribution = val
                break
    if not attribution:
        attribution = "the official PES University information portal"
        
    return attribution


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
        similarity_weight: float = 5.0,
        keyword_weight: float = 1.5,
        rag_enabled: bool = True
    ):
        """
        Initializes the BaseAgent with a ChromaDB collection.
        """
        self.collection_name = collection_name
        self.similarity_weight = similarity_weight
        self.keyword_weight = keyword_weight
        self.rag_enabled = rag_enabled
        self.similarity_threshold = 0.58  # Updated baseline low confidence threshold
        
        if self.rag_enabled:
            self.qwen_client = QwenClient()
            self.synthesizer = GeminiSynthesizer()
        
        if client is not None:
            self.client = client
        else:
            if db_path is None:
                db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_new", "vectorstore"))
            try:
                self.client = chromadb.PersistentClient(path=db_path)
            except Exception as e:
                logger.warning(f"Failed to initialize ChromaDB client at path {db_path}: {e}")
                self.client = None
            
        if BaseAgent._shared_emb_fn is None:
            try:
                BaseAgent._shared_emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2",
                    device="cpu"
                )
            except Exception:
                BaseAgent._shared_emb_fn = None
        self.emb_fn = BaseAgent._shared_emb_fn
            
        self.collection = None
        if self.client:
            try:
                self.collection = self.client.get_collection(
                    name=self.collection_name, 
                    embedding_function=self.emb_fn
                )
            except Exception as e:
                logger.warning(f"Failed to get collection '{self.collection_name}': {e}. Running in degraded offline mode.")
                self.collection = None

    def calculate_overlap_score(self, query: str, text_content: str) -> float:
        """
        Calculates the keyword overlap score (ratio of matching tokens) between the
        query and the text content with simple stemming/plural handling and concept synonyms.
        """
        def tokenize(text: str) -> set:
            words = re.findall(r'\b\w+\b', text.lower())
            tokens = set()
            for w in words:
                if w not in STOP_WORDS:
                    norm = normalize_word(w)
                    if norm:
                        tokens.add(norm)
            return tokens
            
        query_tokens = tokenize(query)
        content_tokens = tokenize(text_content)
        
        if not query_tokens:
            return 0.0
            
        match_count = 0
        for q_tok in query_tokens:
            matched = False
            # Check literal match
            if q_tok in content_tokens:
                matched = True
            else:
                # Check synonym match
                for group_words in SYNONYMS.values():
                    group_normalized = {normalize_word(w) for w in group_words}
                    if q_tok in group_normalized:
                        if any(w in content_tokens for w in group_normalized):
                            matched = True
                            break
            if matched:
                match_count += 1
                
        return match_count / len(query_tokens)


    def parse_document(self, doc_text: str) -> Tuple[str, str]:
        """
        Parses a document string formatted as "Question: ... \nAnswer: ..." 
        into its individual question and answer components, supporting multiline structures.
        """
        lines = doc_text.split("\n")
        question_lines = []
        answer_lines = []
        in_question = False
        in_answer = False
        
        for line in lines:
            if line.startswith("Question:"):
                in_question = True
                in_answer = False
                question_lines.append(line[len("Question:"):].strip())
            elif line.startswith("Answer:"):
                in_question = False
                in_answer = True
                answer_lines.append(line[len("Answer:"):].strip())
            elif in_question:
                question_lines.append(line)
            elif in_answer:
                answer_lines.append(line)
                
        question = "\n".join(question_lines).strip()
        answer = "\n".join(answer_lines).strip()
        
        if not question:
            question = doc_text
        if not answer:
            answer = doc_text
            
        return question, answer

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """
        Retrieves the top 15 documents from the collection, calculates keyword
        overlap scores with metadata boosts, re-ranks them based on a combined
        score, and removes duplicate logical sections.
        """
        if not self.collection:
            logger.warning(f"Collection '{self.collection_name}' is not initialized. Returning empty candidate list.")
            return []
            
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=30
            )
        except Exception as e:
            logger.warning(f"Querying collection '{self.collection_name}' failed: {e}. Returning empty candidate list.")
            return []
            
        retrieved_docs = []
        if results and results.get('documents') and results['documents'][0]:
            docs = results['documents'][0]
            ids = results['ids'][0] if 'ids' in results and results['ids'] else [None] * len(docs)
            metadatas = results['metadatas'][0] if 'metadatas' in results and results['metadatas'] else [{}] * len(docs)
            distances = results['distances'][0] if 'distances' in results and results['distances'] else [None] * len(docs)
            
            # Normalize query words
            query_raw_words = re.findall(r'\b\w+\b', query.lower())
            query_words = [normalize_word(w) for w in query_raw_words if w not in STOP_WORDS]
            
            # Identify active target concepts in the query
            active_concepts = []
            for concept, synonyms in SYNONYMS.items():
                is_active = False
                for syn in synonyms:
                    pattern = r'\b' + re.escape(syn) + r'\b'
                    if re.search(pattern, query.lower()):
                        is_active = True
                        break
                if is_active:
                    active_concepts.append((concept, synonyms))
            
            for doc, doc_id, meta, dist in zip(docs, ids, metadatas, distances):
                meta = meta if isinstance(meta, dict) else {}
                
                # Parse the document into question and answer
                q_text, a_text = self.parse_document(doc)
                
                # Calculate keyword overlap score incorporating title, heading and full document body text
                heading_raw = meta.get("heading", "")
                title_raw = meta.get("title", "")
                full_text_for_keywords = f"{title_raw} {heading_raw} {doc}"
                kw_score = self.calculate_overlap_score(query, full_text_for_keywords)
                
                # Calculate metadata-aware boosts with normalization
                heading_words = [normalize_word(w) for w in re.findall(r'\b\w+\b', heading_raw)]
                title_words = [normalize_word(w) for w in re.findall(r'\b\w+\b', title_raw)]
                category_words = [normalize_word(w) for w in re.findall(r'\b\w+\b', meta.get("category", ""))]
                
                # Extract actual headings from body text
                body_headings = []
                for line in doc.split('\n'):
                    if line.strip().startswith('#'):
                        body_headings.extend(re.findall(r'\b\w+\b', line.lstrip('#').strip().lower()))
                body_heading_words = [normalize_word(w) for w in body_headings]
                
                all_heading_words = set(heading_words + body_heading_words)
                
                heading_boost = sum(0.3 for w in query_words if w in all_heading_words)
                title_boost = sum(0.1 for w in query_words if w in title_words)
                category_boost = sum(0.1 for w in query_words if w in category_words)
                
                heading_boost = min(heading_boost, 0.9)
                title_boost = min(title_boost, 0.3)
                category_boost = min(category_boost, 0.2)
                
                metadata_boost = heading_boost + title_boost + category_boost
                
                # Concept-level synonym boosting
                boost_amount = 0.0
                doc_text_lower = doc.lower()
                for concept, synonyms in active_concepts:
                    matched = False
                    for syn in synonyms:
                        if syn in doc_text_lower or syn in heading_raw.lower() or syn in title_raw.lower():
                            matched = True
                            break
                    if matched:
                        boost_amount += 1.5  # Concept boost
                
                # Map distance to similarity metric
                similarity_score = 1.0 / (1.0 + (dist if dist is not None else 0.0))
                combined_score = self.similarity_weight * similarity_score + self.keyword_weight * kw_score + metadata_boost + boost_amount
                
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
                
            # Re-rank results based on combined score in descending order
            retrieved_docs.sort(key=lambda x: x["combined_score"], reverse=True)
            
        return retrieved_docs


    def answer(self, query: str, routing_confidence: float = None, debug: bool = False) -> str:
        """
        Performs retrieval, prints debugging information about all candidates if debug is True,
        selects the best matching document based on re-ranked scores, applies
        confidence-level thresholds, and formats the final response.
        Never performs a secondary LLM relevance sufficiency check.
        """
        start_time = time.time()
        
        fallback_msg = format_fallback_message(query, self.get_domain())
        
        # 1. Retrieve documents
        docs = self.retrieve(query)
        
        # 2. If no documents exist: Return contact fallback
        if not docs:
            if debug:
                print(f"\n[{self.__class__.__name__}] Selected Collection: {self.collection_name}")
                print(f"[{self.__class__.__name__}] Retrieved Chunk IDs: []")
                print(f"Fallback triggered for query: '{query}'")
                print(f"Reason: No documents retrieved from ChromaDB collection '{self.collection_name}'")
            log_evaluation_trace(
                query=query,
                selected_agent=self.__class__.__name__,
                selected_domain=self.get_domain(),
                routing_confidence=routing_confidence if routing_confidence is not None else 0.0,
                selected_doc_id="None",
                retrieved_docs=[],
                answer=fallback_msg,
                relevance_decision="INSUFFICIENT",
                confidence_score=0.0,
                fallback_used=True
            )
            return f"Answer:\n{fallback_msg}\n\nSources:\n    None"
            
        best_doc = docs[0]
        
        # 3. Compute similarity score
        best_sim_score = 1.0 / (1.0 + best_doc["distance"])
        
        # 4. If similarity/keyword match is below threshold: Return contact fallback
        threshold = 0.48
        is_sufficient = (best_sim_score >= threshold) or (best_doc.get("keyword_score", 0.0) >= 0.3) or (best_doc.get("combined_score", 0.0) >= 1.2)
        
        if best_sim_score >= 0.65:
            confidence_level = "HIGH"
        elif is_sufficient:
            confidence_level = "MEDIUM"
        else:
            confidence_level = "LOW"
            
        if not is_sufficient:
            if debug:
                print(f"\n[{self.__class__.__name__}] Selected Collection: {self.collection_name}")
                print(f"[{self.__class__.__name__}] Retrieved Chunk IDs: {[d['id'] for d in docs]}")
                print(f"[Warning] Similarity score {best_sim_score:.4f} and keyword score {best_doc.get('keyword_score', 0.0):.4f} are below threshold. Forcing fallback.")
                print(f"Fallback triggered. Reason: Insufficient similarity and keyword score (combined={best_doc.get('combined_score', 0.0):.4f})")
            log_evaluation_trace(
                query=query,
                selected_agent=self.__class__.__name__,
                selected_domain=self.get_domain(),
                routing_confidence=routing_confidence if routing_confidence is not None else 0.0,
                selected_doc_id="None",
                retrieved_docs=docs,
                answer=fallback_msg,
                relevance_decision="INSUFFICIENT",
                confidence_score=best_sim_score,
                fallback_used=True
            )
            return f"Answer:\n{fallback_msg}\n\nSources:\n    None"
            
        # 5. Otherwise: Generate the answer directly using Gemini or Qwen
            
        # Synthesis RAG mode
        formatted_context = ""
        
        # Deduplicate and filter context docs based on strict thresholds
        seen_texts = set()
        context_docs = []
        for doc in docs:
            doc_sim = 1.0 / (1.0 + doc["distance"])
            # Require at least moderate similarity or keyword overlap to be included as context
            if doc_sim < 0.45 and doc.get("keyword_score", 0.0) < 0.2 and doc.get("combined_score", 0.0) < 1.0:
                continue
                
            # Simple deduplication by hash to prevent duplicate FAQs
            text_hash = hash(doc["document"])
            if text_hash not in seen_texts:
                seen_texts.add(text_hash)
                context_docs.append(doc)
                
            # Limit to top 3 unique, high-confidence chunks to reduce noise
            if len(context_docs) >= 3:
                break
                
        # Fallback if filtering was too aggressive
        if not context_docs:
            context_docs = docs[:1]
            
        for i, doc in enumerate(context_docs, 1):
            formatted_context += f"Document {i} (ID: {doc.get('id', 'unknown')}):\n{doc.get('document', '')}\n\n"
            
        # Concise, direct answer prompt
        prompt = (
            f"You are VidyaSahayak, the PES University AI Campus Assistant. "
            f"Answer the user query based ONLY on the provided context. "
            f"Synthesize a concise answer (1-3 sentences) using your own words. "
            f"Do not blindly copy and paste large blocks of text from the context. "
            f"Be direct, polite, and helpful. "
            f"Do not mention source files, document names, document IDs, or internal metadata. "
            f"Do not start with 'According to...' or 'Based on...'. Just answer the question directly.\n\n"
            f"PES-specific acronyms (use these definitions, never invent your own):\n"
            f"  ISA = In-Semester Assessment (internal exam conducted during the semester)\n"
            f"  ESA = End-Semester Assessment (final exam at the end of a semester)\n"
            f"  CGPA = Cumulative Grade Point Average\n"
            f"  SGPA = Semester Grade Point Average\n"
            f"  PESSAT = PES Scholastic Aptitude Test (university entrance exam)\n"
            f"  KCET = Karnataka Common Entrance Test\n"
            f"  COMEDK = Consortium of Medical, Engineering and Dental Colleges of Karnataka\n"
            f"  CIE = Center for Innovation and Entrepreneurship\n"
            f"  MRD = Prof. M.R. Doreswamy (scholarship name)\n\n"
            f"Context:\n{formatted_context}\n"
            f"Query: {query}\n"
            f"Answer:"
        )
        
        rag_answer = None
        llm_used = getattr(llm_config, "PRIMARY_LLM", "qwen")
        
        llm_start = time.time()
        if llm_used == "qwen":
            try:
                rag_answer = self.qwen_client.generate(prompt)
            except Exception as e:
                if debug:
                    print(f"[Warning] Qwen generation failed: {e}. Falling back to Gemini.")
                
        if not rag_answer:
            try:
                rag_answer = self.synthesizer.synthesize(query, context_docs, domain=self.get_domain())
                llm_used = "gemini"
            except Exception as e:
                if debug:
                    print(f"[Warning] Gemini RAG synthesis failed: {e}. Falling back to raw markdown chunk.")
                llm_used = "retrieval-only"
        
        # If both LLMs failed/timed out/degraded, retrieve raw text from first chunk directly
        if not rag_answer or not rag_answer.strip():
            llm_used = "offline-markdown-fallback"
            if debug:
                print("[Warning] Both Qwen and Gemini are offline/degraded. Falling back to raw retrieved markdown chunk.")
            q_parsed, a_parsed = self.parse_document(best_doc['document'])
            rag_answer = a_parsed if a_parsed else best_doc['document']
            
        llm_latency = time.time() - llm_start
        total_latency = time.time() - start_time
        
        if rag_answer.startswith("Answer:"):
            rag_answer = rag_answer[len("Answer:"):].strip()
            
        # Clean up prompt formatting if raw document question was returned
        if rag_answer.strip().startswith("Question:"):
            _, parsed_ans = self.parse_document(rag_answer)
            rag_answer = parsed_ans
            
        # Strip any leftover attribution preambles the LLM may have added
        for prefix in ["According to ", "Based on "]:
            if rag_answer.startswith(prefix):
                # Find the end of the attribution clause (first comma or period)
                for sep in [", ", ". "]:
                    idx = rag_answer.find(sep, len(prefix))
                    if idx != -1 and idx < 120:
                        rag_answer = rag_answer[idx + len(sep):]
                        if rag_answer:
                            rag_answer = rag_answer[0].upper() + rag_answer[1:]
                        break
            
        source_file = self.get_domain()
            
        if "Sorry, I could not find information" in rag_answer or fallback_msg in rag_answer:
            rag_answer = fallback_msg
            source_file = "None"
            
        if debug:
            print(f"\n[{self.__class__.__name__}] Selected Collection: {self.collection_name}")
            print(f"[{self.__class__.__name__}] Retrieved Chunk IDs: {[doc['id'] for doc in docs]}")
            print(f"[{self.__class__.__name__}] Retrieved Chunk Text:")
            print("=" * 80)
            for i, doc in enumerate(docs, 1):
                print(f"--- Chunk {i} (ID: {doc['id']}) ---")
                print(doc['document'])
                print("-" * 80)
            print("=" * 80)
            print(f"[{self.__class__.__name__}] Final Prompt:")
            print("=" * 80)
            print(prompt)
            print("=" * 80)
            print(f"[{self.__class__.__name__}] LLM Model: {llm_used}")
            print(f"[{self.__class__.__name__}] Response Latency: {total_latency:.2f}s (LLM: {llm_latency:.2f}s)")
            print(f"[{self.__class__.__name__}] Prompt Length: {len(prompt)} characters")
            print(f"[{self.__class__.__name__}] Token Counts (Estimated): Prompt: {len(prompt)//4} tokens, Answer: {len(rag_answer)//4} tokens")
            print(f"[{self.__class__.__name__}] Final Answer: {rag_answer}")
            print()

            
        log_evaluation_trace(
            query=query,
            selected_agent=self.__class__.__name__,
            selected_domain=self.get_domain(),
            routing_confidence=routing_confidence if routing_confidence is not None else 1.0,
            selected_doc_id=best_doc["id"],
            retrieved_docs=docs,
            answer=rag_answer,
            relevance_decision="SUFFICIENT",
            confidence_score=best_sim_score,
            fallback_used=(rag_answer == fallback_msg)
        )
        
        # --- Observability Debug Record ---
        print("\n" + "="*40)
        print("[DEBUG] RAG PIPELINE DEBUG RECORD")
        print("="*40)
        print(f"Intent:           {self.get_domain().capitalize()}")
        if fallback_used_flag := (rag_answer == fallback_msg):
            print(f"Retrieved:        None (Fallback Triggered)")
            print(f"Similarity:       N/A")
            print(f"Chunks Used:      0")
        else:
            print(f"Retrieved:        {best_doc.get('id', 'Unknown')}")
            print(f"Similarity:       {best_sim_score:.4f}")
            print(f"Chunks Used:      {len(context_docs)}")
        print(f"Prompt Tokens:    {len(prompt)//4}")
        print(f"Response Tokens:  {len(rag_answer)//4}")
        print("="*40 + "\n")
        
        return f"Answer:\n{rag_answer}\n\nSources:\n    {source_file}"            
        # Retrieval-only mode fallback or disabled RAG
        ans_text = best_doc['answer']
        if ans_text.startswith("Answer:"):
            ans_text = ans_text[len("Answer:"):].strip()
            

            
        source_file = self.get_domain()
            
        log_evaluation_trace(
            query=query,
            selected_agent=self.__class__.__name__,
            selected_domain=self.get_domain(),
            routing_confidence=routing_confidence if routing_confidence is not None else 1.0,
            selected_doc_id=best_doc["id"],
            retrieved_docs=docs,
            answer=ans_text,
            relevance_decision="SUFFICIENT",
            confidence_score=best_sim_score,
            fallback_used=False
        )
        return ans_text

    @abstractmethod
    def get_domain(self) -> str:
        """
        Returns the domain/collection name associated with this agent.
        """
        pass
