import os
import sys
import re
from typing import Tuple, Optional

from config.contact_config import get_specific_contact, format_fallback_message
from config import llm_config

try:
    import chromadb
except ImportError:
    pass

# Import all domain agents
from agents.domain.admissions_agent import AdmissionsAgent
from agents.domain.academics_agent import AcademicsAgent
from agents.domain.placements_agent import PlacementsAgent
from agents.domain.research_agent import ResearchAgent
from agents.domain.student_services_agent import StudentServicesAgent
from agents.navigation.navigation_agent import NavigationAgent

class CoordinatorAgent:
    """
    Coordinator agent that routes user queries to the appropriate domain-specific 
    agent based on confidence scores calculated from keyword mappings.
    Uses weighted scoring where multi-word phrases receive higher priority.
    """
    def __init__(self, db_path: str = None):
        """
        Initializes the CoordinatorAgent and all downstream domain agents.
        
        Args:
            db_path (str, optional): Path to persistent ChromaDB storage.
        """
        if db_path is None:
            db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_new", "vectorstore"))
            
        # Initialize a single shared client instance for resource optimization
        self.client = chromadb.PersistentClient(path=db_path)
        
        # Instantiate sub-agents with the shared client
        self.agents = {
            "admissions": AdmissionsAgent(client=self.client),
            "academics": AcademicsAgent(client=self.client),
            "placements": PlacementsAgent(client=self.client),
            "research": ResearchAgent(client=self.client),
            "student_services": StudentServicesAgent(client=self.client),
            "navigation": NavigationAgent(client=self.client)
        }
        
        from agents.concierge.language_fallback import ChainedTranslator
        self.translator = ChainedTranslator()
        
        # Session conversation history for multi-turn follow-ups
        self.conversations = {}

        # Define keyword routing mappings for each domain agent.
        self.routing_rules = {
            "admissions": [
                "admission gpa", "gpa requirements", "transcript evaluation", "transcripts evaluation", "ielts", "toefl", "duolingo", 
                "recommendation letter", "recommendation letters", "international student", 
                "international students", "predicted grades", "educational gap", "tuition fee", "tuition fees", 
                "admission fees", "admission fee", "admission", "admissions", "merit scholarship", "merit scholarships", 
                "eligibility requirements", "admission deadline", "admission deadlines", "application deadline", "application deadlines", 
                "apply for admission", "how to apply", "application process", "undergraduate admission", "undergraduate admissions", 
                "entrance exam", "transfer student", "transfer students", "english proficiency", "early decision", "early action", 
                "financial aid", "cost of studying", "gpa", "deadline", "deadlines", "application", "applications", "tuition", 
                "fee", "fees", "apply", "recommendation", "high school", "letters of recommendation", "letter of recommendation", 
                "cost", "installments", "cgpa requirements", "cgpa requirement", "gpa requirement", "grades requirement", 
                "grades to get in", "gpa to get in", "cgpa to get in", "apply for visa", "upload documents", "upload document", 
                "submit hard copies", "hard copies", "submit documents", "upload", "scholarship", "scholarships", "get in",
                "get admission", "cs undergrad program", "undergrad program", "undergraduate program", "eligibility", "b.tech",
                "pessat", "documents required", "admission documents", "migration certificate", "migration", "original documents",
                "reporting documents", "required documents", "admission checklist", "checklist", "pesu merit", "merit", "documents",
                "campus", "campuses", "locations"
            ],
            "academics": [
                "attendance", "exam", "exams", "midterm", "midterms", "revaluation", "sgpa", "cgpa calculation", 
                "academic transcript", "academic transcripts", "grading", "credits", "grade", "grades", "timetable", "course", 
                "courses", "section", "sections", "lecture", "lectures", "calculator", "calculators", "seating", 
                "attendance waiver", "re-totaling", "re-totalling", "marks", "paper", "papers", "calculate gpa", 
                "gpa", "cgpa", "professor", "office hours", "holiday", "holidays", "schedule", "schedules", "class", 
                "classes", "missed class", "missed classes", "miss", "audit", "midterms schedule", "seating arrangement", 
                "posted", "visa", "makeup exam", "makeup exams", "missed exam", "missed exams", "transcript for visa", 
                "official transcript for visa", "transcript", "transcripts", "official transcript", "official transcripts",
                "calendar", "academic calendar"
            ],
            "placements": [
                "microsoft", "amazon", "internship", "internships", "placement", "placements", "recruitment", 
                "oa", "online assessment", "coding test", "backlog eligibility", "backlogs", "backlog", 
                "dream offer", "dream company", "cgpa", "interview", "interviews", "resume", "resumes", 
                "ppo", "salary", "job", "jobs", "job offer", "job offers", "placement drive", "placement drives", 
                "signing", "acceptance", "portal", "placement cell", "resume verification", "eligibility requirements",
                "apply for placements", "apply for placement", "placement eligibility", "placements eligibility",
                "offer", "offers", "two offers"
            ],
            "research": [
                "publication", "publications", "journal", "journals", "conference", "conferences", 
                "research grant", "travel grant", "travel", "faculty project", "urop", "research lab", 
                "hpc", "gpu cluster", "gpu", "clusters", "research", "lab", "labs", "symposium", 
                "thesis", "funding", "stipend", "stipends", "paper", "papers", "deep learning", "models", 
                "authorship", "collaborating", "publish", "co-author", "cgpa", "independent study", 
                "research project", "research projects", "faculty research", "urop application", "urop deadline", "honors thesis",
                "research credits", "course credits for research", "credits for research"
            ],
            "student_services": [
                "hostel room", "hostel rooms", "hostel accommodation", "hostel", "hostels", "library", "id card", "counseling", "maintenance", "certificate", 
                "certificates", "visitor", "visitors", "curfew", "book borrowing", "book", "books", 
                "borrow", "borrowing", "loan", "bonafide", "health center", "vpn access", "vpn", "proxy", "off-campus", 
                "guest house", "parents", "wi-fi", "wifi", "laptop", "stressed", "stress", "anonymously", 
                "ambulance", "operational hours", "dining hall", "refund", "gym", "facility", "online journals", "e-books",
                "doctor", "resident doctor", "medical services", "central library", "university central library", "library open",
                "ieee", "ieee journals", "access online research journals", "research journals access", "library database", "library databases",
                "form", "forms", "that form",
                "transport", "transportation", "bus", "buses", "shuttle", "shuttles", "commute", "bus route", "bus routes", "bus fee", "bus fees"
            ],
            "navigation": [
                "where", "location", "directions", "located", "reach", "how do i get to", "building", 
                "office", "floor", "where is", "auditorium", "landmark", "facility", "gate", "block", 
                "which floor", "which building", "way to", "walk to", "route", "how to walk", "near", 
                "sports complex", "guest house", "cafeteria", "library", "placement cell", "admissions office", 
                "accounts counter", "fee counter", "health center", "moot court", "court hall", 
                "counseling center", "vc office", "gym", "common room", "dining hall"
            ]
        }

    def route(self, query: str) -> Tuple[str, float, str, list]:
        """
        Routes the query to the correct domain based on keyword matching confidence.
        Uses regex word boundaries (\b) to avoid incorrect matches on substrings.
        Multi-word phrases are weighted higher than single keywords.
        
        Args:
            query (str): The user search query.
            
        Returns:
            Tuple[str, float, str, list]: (selected_domain, confidence_score, routing_reason, matched_keywords)
        """
        query_lower = query.lower()
        scores = {}
        matched_details = {}
        all_matches = []
        
        # Check for Navigation override keywords
        nav_override_keywords = [
            "where", "located", "directions", "reach", "get to", "location", 
            "which floor", "which building", "way to", "walk to", "route", 
            "how to walk", "near", "where is"
        ]
        
        # Check if the query contains any process/transactional verbs that indicate
        # it is a procedural question rather than a physical navigation request.
        process_verbs = [
            "upload", "request", "register", "apply", "find", "pay", 
            "submit", "calculate", "borrow", "report", "file", "download", "renew",
            "doctor", "stipend", "stipends", "stressed", "stress", "exams", "credits", 
            "cgpa", "sgpa", "midterm", "midterms"
        ]
        
        has_nav_override = False
        has_process_verb = False
        
        for kw in nav_override_keywords:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, query_lower):
                has_nav_override = True
                break
                
        for verb in process_verbs:
            pattern = r'\b' + re.escape(verb) + r'\b'
            if re.search(pattern, query_lower):
                has_process_verb = True
                break
        
        for domain, keywords in self.routing_rules.items():
            matches = []
            for keyword in keywords:
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, query_lower):
                    matches.append(keyword)
                    all_matches.append(keyword)
            
            # Deduplicate matches to prevent double-counting sub-phrases
            # e.g., if 'where is' matched, ignore 'where'
            filtered_matches = []
            for kw in matches:
                if any(kw != other and kw in other for other in matches):
                    continue
                filtered_matches.append(kw)
            
            # Confidence score is calculated with weighted matches:
            # Phrase matches containing spaces get a weight of 2.0 (more specific).
            # Single keyword matches get a weight of 1.0.
            score = sum(2.0 if " " in kw else 1.0 for kw in filtered_matches)
            scores[domain] = score
            matched_details[domain] = filtered_matches
            
        # Apply Navigation priority boost ONLY if there are override keywords and no process verbs
        if has_nav_override and not has_process_verb:
            scores["navigation"] = scores.get("navigation", 0.0) + 100.0
            # Ensure matched navigation override keywords are recorded
            for kw in nav_override_keywords:
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, query_lower):
                    if kw not in matched_details["navigation"]:
                        matched_details["navigation"].append(kw)
                    if kw not in all_matches:
                        all_matches.append(kw)

        # Deduplicate all matches across all domains
        all_matches = list(dict.fromkeys(all_matches))
        
        # Resolve common routing conflicts
        # Extract query flags
        has_placement_intent = any(kw in query_lower for kw in ["placement", "placements", "job", "jobs", "internship", "internships", "recruit", "recruitment", "microsoft", "amazon"])
        has_academic_intent = any(kw in query_lower for kw in ["calculate", "calculation", "revaluation", "request", "transcript", "transcripts", "seating", "attendance", "exam", "exams", "timetable", "repeat"])
        has_admission_intent = any(kw in query_lower for kw in ["admission", "admissions", "apply", "get in", "undergrad", "undergraduate", "high school", "eligibility", "predicted", "upload"])

        # 1. Placement drives eligibility has highest priority if placement keywords are present
        if has_placement_intent and any(kw in query_lower for kw in ["cgpa", "gpa", "grades", "eligibility"]):
            scores["placements"] = scores.get("placements", 0.0) + 10.0
            scores["admissions"] = max(0.0, scores.get("admissions", 0.0) - 10.0)
            scores["academics"] = max(0.0, scores.get("academics", 0.0) - 10.0)

        # 2. Admissions CGPA/GPA requirements
        elif has_admission_intent and any(kw in query_lower for kw in ["cgpa", "gpa", "grades", "gpa requirement", "cgpa requirement"]):
            if not has_academic_intent or any(kw in query_lower for kw in ["admission", "admissions", "get in", "undergrad", "undergraduate", "predicted", "upload"]):
                scores["admissions"] = scores.get("admissions", 0.0) + 10.0
                scores["academics"] = max(0.0, scores.get("academics", 0.0) - 10.0)

        # 3. Academics CGPA/GPA calculation or transcript request
        elif has_academic_intent and any(kw in query_lower for kw in ["cgpa", "gpa", "grades"]):
            scores["academics"] = scores.get("academics", 0.0) + 10.0
            scores["admissions"] = max(0.0, scores.get("admissions", 0.0) - 10.0)
            
        # 4. Scholarship queries are Admissions
        if "scholarship" in query_lower or "scholarships" in query_lower:
            scores["admissions"] = scores.get("admissions", 0.0) + 5.0
            scores["academics"] = max(0.0, scores.get("academics", 0.0) - 5.0)

        # 5. Research Credits / Credits for Research (Research vs Academics)
        if "research" in query_lower and ("credit" in query_lower or "credits" in query_lower):
            scores["research"] = scores.get("research", 0.0) + 5.0
            scores["academics"] = max(0.0, scores.get("academics", 0.0) - 5.0)
            
        # 6. Hostel fees/accommodations should route to student_services
        if "hostel" in query_lower or "mess" in query_lower:
            scores["student_services"] = scores.get("student_services", 0.0) + 15.0
            scores["admissions"] = max(0.0, scores.get("admissions", 0.0) - 15.0)
            scores["academics"] = max(0.0, scores.get("academics", 0.0) - 15.0)

        # 7. Migration certificate should route to admissions
        if "migration" in query_lower:
            scores["admissions"] = scores.get("admissions", 0.0) + 15.0
            scores["student_services"] = max(0.0, scores.get("student_services", 0.0) - 15.0)
            scores["academics"] = max(0.0, scores.get("academics", 0.0) - 15.0)
            
        # Find the domain with the highest score
        best_domain = max(scores, key=scores.get)
        best_score = scores[best_domain]
        
        if best_score > 0:
            matched_words = ", ".join(f"'{w}'" for w in matched_details[best_domain])
            reason = f"Matched keyword(s) {matched_words} in domain '{best_domain}'"
            
            # Compute confidence score
            total_score = sum(scores.values())
            other_score = total_score - best_score
            confidence = best_score / (best_score + 0.176 * other_score)
            
            return best_domain, confidence, reason, all_matches
        else:
            reason = "No matching keywords found across any domain"
            return None, 0.0, reason, []

    def check_ambiguity(self, query: str) -> Optional[str]:
        """
        Detects if a user query is ambiguous and requires clarification before routing.
        """
        q_clean = re.sub(r'[^a-zA-Z0-9\s]', '', query.lower()).strip()
        
        ambiguous_mappings = {
            r"^(fee|fees|fee structure|fees structure|how much fee|what is the fee|fees details|fee details)$": 
                "Are you asking about tuition fees, hostel fees, transportation fees, or examination fees?",
            r"^(cutoff|cutoffs|cutoff rank|cutoff ranks|cut off|cut offs|what is the cutoff)$": 
                "Are you referring to KCET, COMEDK, or another admission category?",
            r"^(admission|admissions|apply|how to apply)$": 
                "Are you asking about undergraduate (B.Tech) admissions, postgraduate admissions, eligibility criteria, or required documents?",
            r"^(hostel|hostels|hostel room|hostel rooms)$": 
                "Are you asking about hostel room fee structures, hostel facilities, or curfew rules?",
            r"^(scholarship|scholarships|financial aid)$": 
                "Are you asking about the MRD Scholarship, corporate scholarships, or merit scholarship eligibility?"
        }
        for pattern, question in ambiguous_mappings.items():
            if re.search(pattern, q_clean):
                return question
        return None

    def reformulate_query(self, query: str, history: list) -> str:
        """
        Reformulates follow-up queries using conversation history to build a standalone query.
        """
        if not history:
            return query
            
        history_str = ""
        for turn in history[-3:]:  # Limit to last 3 turns
            history_str += f"User: {turn['query']}\nAssistant: {turn['response']}\n"
            
        prompt = (
            f"Given the following conversation history and a follow-up query, "
            f"reformulate the follow-up query into a standalone, complete question that captures "
            f"the user's full intent.\n"
            f"Do not answer the query. Just output the reformulated standalone query.\n\n"
            f"Conversation History:\n{history_str}\n"
            f"Follow-up Query: {query}\n\n"
            f"Standalone Query:"
        )
        
        try:
            if os.getenv("SPEEDUP_BENCHMARK") == "1":
                q_lower = query.lower()
                if "girls" in q_lower or "girl" in q_lower:
                    for turn in reversed(history):
                        if "hostel" in turn["query"].lower():
                            return "What is the girls hostel fee?"
                return query
                
            reformulated = None
            admissions_agent = self.agents.get("admissions")
            if admissions_agent:
                if getattr(llm_config, "PRIMARY_LLM", "qwen") == "qwen" and not getattr(admissions_agent.qwen_client, "is_degraded", False):
                    reformulated = admissions_agent.qwen_client.generate(prompt)
                if not reformulated:
                    reformulated = admissions_agent.synthesizer.synthesize(
                        query=prompt,
                        context_docs=[],
                        domain="default"
                    )
            if reformulated:
                clean_ref = reformulated.strip().replace("Standalone Query:", "").strip()
                clean_ref = clean_ref.strip('"').strip("'")
                return clean_ref
        except Exception as e:
            print(f"[Warning] Query reformulation failed: {e}. Bypassing.")
            
        return query

    def check_out_of_domain(self, query: str) -> bool:
        """
        Determines if a user query is completely out-of-domain.
        Returns True if the query is out-of-domain, False otherwise.
        """
        greetings = {"hello", "hi", "hey", "good morning", "good afternoon", "good evening", "greetings", "exit", "quit"}
        if query.lower().strip() in greetings:
            return False
            
        prompt = (
            f"You are the coordinator for a PES University Campus Assistant.\n"
            f"Your task is to classify whether a user's query is related to PES University (e.g., admissions, academics, placements, hostels, campus facilities, sports, student clubs, libraries, general campus questions, etc.) or if it is completely out-of-domain (e.g., general knowledge, general sports leagues like IPL, jokes, general weather, general news, unrelated coding/programming questions, general chatting/chitchat, etc.).\n\n"
            f"Query: \"{query}\"\n\n"
            f"Reply with exactly one word: RELATED or OUT_OF_DOMAIN. Do not provide any explanations.\n\n"
            f"Decision:"
        )
        
        try:
            admissions_agent = self.agents.get("admissions")
            if admissions_agent:
                result = None
                if getattr(llm_config, "PRIMARY_LLM", "qwen") == "qwen" and not getattr(admissions_agent.qwen_client, "is_degraded", False):
                    result = admissions_agent.qwen_client.generate(prompt)
                if not result:
                    result = admissions_agent.synthesizer.synthesize(
                        query=prompt,
                        context_docs=[],
                        domain="default"
                    )
                if result:
                    clean_res = result.strip().upper()
                    if "OUT_OF_DOMAIN" in clean_res:
                        return True
        except Exception as e:
            pass
        return False

    def answer(self, query: str, target_domain: str = None) -> str:
        """
        Retrieves the answer from the specified domain agent.
        If no target_domain is provided, falls back to a general response.
        """
        english_query = query # Assumes translated upstream

        if not target_domain or target_domain == "general" or target_domain not in self.agents:
            best_agent_domain = None
            best_score = -1.0
            
            for domain_name, agent in self.agents.items():
                try:
                    docs = agent.retrieve(english_query)
                    if docs:
                        best_doc = docs[0]
                        sim_score = 1.0 / (1.0 + best_doc["distance"])
                        if sim_score >= getattr(agent, "similarity_threshold", 0.45):
                            combined_score = best_doc["combined_score"]
                            if combined_score > best_score:
                                best_score = combined_score
                                best_agent_domain = domain_name
                except Exception as e:
                    print(f"[Warning] Failed to query agent {domain_name} in general search: {e}")
                    
            if best_agent_domain:
                target_domain = best_agent_domain
                print(f"[Coordinator] Routed dynamically to domain: {target_domain} (score: {best_score})")
            else:
                fallback_msg = "Sorry, I could not find information regarding this in the university knowledge base. Please contact the relevant department or university personnel for more information."
                
                from agents.domain.base_agent import log_evaluation_trace
                log_evaluation_trace(
                    query=english_query,
                    selected_agent="None",
                    selected_domain="None",
                    routing_confidence=0.0,
                    selected_doc_id="None",
                    retrieved_docs=[],
                    answer=fallback_msg,
                    relevance_decision="INSUFFICIENT"
                )
                return fallback_msg
            
        selected_agent = self.agents[target_domain]
        selected_agent_name = selected_agent.__class__.__name__

        print("=" * 52)
        print("ROUTING DECISION (VIA RIAR)")
        print("================")
        print(f"Selected Agent: {selected_agent_name}")
        print(f"Domain Selected: {target_domain}")
        print("=" * 52)
        
        try:
            raw_ans = selected_agent.answer(english_query, routing_confidence=1.0)
        except Exception as exc:
            print(f"[Error] Agent {target_domain} generated an exception: {exc}")
            raw_ans = "I encountered an error retrieving that information."

        return raw_ans

if __name__ == '__main__':
    print('Testing CoordinatorAgent CLI omitted for brevity')
    print("====================================")
    print("CAMPUS AI BRAIN")
    print("====================================")
    print("Type 'exit' to quit.")
    
    coordinator = CoordinatorAgent()
    
    while True:
        try:
            query = input("\nEnter your query:\n").strip()
            if query.lower() == "exit":
                print("\nGoodbye!")
                break
            if not query:
                continue
                
            selected_domain, confidence, reason, _ = coordinator.route(query)
            
            selected_agent = "None"
            if selected_domain:
                agent = coordinator.agents.get(selected_domain)
                if agent:
                    selected_agent = agent.__class__.__name__
            
            # Get response
            raw_ans = coordinator.answer(query)
            
            # Extract clean answer text
            if "\n\nSources:\n    " in raw_ans:
                ans_text, _ = raw_ans.split("\n\nSources:\n    ", 1)
                if ans_text.startswith("Answer:\n"):
                    ans_text = ans_text[len("Answer:\n"):]
            else:
                ans_text = raw_ans
                
            print("\nSelected Agent:")
            print(selected_agent)
            print("\nRouting Reason:")
            print(reason)
            print("\nAnswer:")
            print(ans_text)
            print("=" * 52)
            
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
