import os
import sys
import re
from typing import Dict, Any, Tuple

# Ensure parent directory is in search path if run directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

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
            db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "vectorstore"))
            
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
                "cost", "installments"
            ],
            "academics": [
                "attendance", "exam", "exams", "midterm", "midterms", "revaluation", "sgpa", "cgpa calculation", 
                "academic transcript", "academic transcripts", "grading", "credits", "grade", "grades", "timetable", "course", 
                "courses", "section", "sections", "lecture", "lectures", "calculator", "calculators", "seating", 
                "attendance waiver", "re-totaling", "re-totalling", "marks", "paper", "papers", "calculate gpa", 
                "gpa", "cgpa", "professor", "office hours", "holiday", "holidays", "schedule", "schedules", "class", 
                "classes", "missed class", "missed classes", "miss", "audit", "midterms schedule", "seating arrangement", 
                "posted", "visa"
            ],
            "placements": [
                "microsoft", "amazon", "internship", "internships", "placement", "placements", "recruitment", 
                "oa", "online assessment", "coding test", "backlog eligibility", "backlogs", "backlog", 
                "dream offer", "dream company", "cgpa", "interview", "interviews", "resume", "resumes", 
                "ppo", "salary", "job", "jobs", "job offer", "job offers", "placement drive", "placement drives", 
                "signing", "acceptance", "portal", "placement cell", "resume verification", "eligibility requirements"
            ],
            "research": [
                "publication", "publications", "journal", "journals", "conference", "conferences", 
                "research grant", "travel grant", "travel", "faculty project", "urop", "research lab", 
                "hpc", "gpu cluster", "gpu", "clusters", "research", "lab", "labs", "symposium", 
                "thesis", "funding", "stipend", "stipends", "paper", "papers", "deep learning", "models", 
                "authorship", "collaborating", "publish", "co-author", "cgpa", "independent study", 
                "research project", "research projects", "faculty research", "urop application", "urop deadline", "honors thesis"
            ],
            "student_services": [
                "hostel room", "hostel rooms", "hostel accommodation", "hostel", "hostels", "library", "id card", "counseling", "maintenance", "certificate", 
                "certificates", "visitor", "visitors", "curfew", "book borrowing", "book", "books", 
                "borrow", "borrowing", "loan", "bonafide", "health center", "vpn access", "vpn", "proxy", "off-campus", 
                "guest house", "parents", "wi-fi", "wifi", "laptop", "stressed", "stress", "anonymously", 
                "ambulance", "operational hours", "dining hall", "refund", "gym", "facility", "online journals", "e-books",
                "doctor", "resident doctor", "medical services", "central library", "university central library", "library open",
                "ieee", "ieee journals"
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

    def answer(self, query: str) -> str:
        """
        Routes the query, prints the selection and routing reason, and retrieves the answer.
        If no strong match exists (confidence score is 0), returns "No suitable agent found".
        
        Args:
            query (str): The user search query.
            
        Returns:
            str: The final answer or fallback response.
        """
        selected_domain, confidence, reason, all_matches = self.route(query)
        
        # Check if a strong match exists
        if selected_domain is None or confidence <= 0.0:
            fallback_msg = (
                "I'm sorry, I couldn't identify the right department for your query.\n"
                "Please try asking about one of the following topics:\n"
                "- Admissions (requirements, application, fees, scholarships)\n"
                "- Academics (attendance, exams, SGPA/CGPA, transcripts)\n"
                "- Placements (internships, company eligibility, recruitment process)\n"
                "- Research (labs, publications, faculty projects, UROP)\n"
                "- Student Services (hostel, library, ID cards, certificate requests)\n"
                "- Navigation (campus directions, building/office locations)"
            )
            print("=" * 52)
            print("USER QUERY")
            print("==========")
            print()
            print(query)
            print()
            print("=" * 52)
            print("ROUTING DECISION")
            print("================")
            print()
            print("Matched Keywords:")
            print("None")
            print()
            print("Selected Agent:")
            print("None")
            print()
            print("Domain Selected:")
            print("None")
            print()
            print("Confidence:")
            print("0.00")
            print()
            print("=" * 52)
            print("ANSWER")
            print("======")
            print()
            print(fallback_msg)
            print()
            print("=" * 52)
            print("SOURCE")
            print("======")
            print()
            print("None")
            print()
            print("=" * 52)
            
            # Log trace for unmatched query
            from agents.domain.base_agent import log_evaluation_trace
            log_evaluation_trace(
                query=query,
                selected_agent="None",
                selected_domain="None",
                routing_confidence=0.0,
                selected_doc_id="None",
                retrieved_docs=[],
                answer=fallback_msg
            )
            return fallback_msg
            
        agent = self.agents[selected_domain]
        selected_agent_name = agent.__class__.__name__
        matched_keywords_str = ", ".join(all_matches) if all_matches else "None"
        
        # Print USER QUERY and ROUTING DECISION
        print("=" * 52)
        print("USER QUERY")
        print("==========")
        print()
        print(query)
        print()
        print("=" * 52)
        print("ROUTING DECISION")
        print("================")
        print()
        print("Matched Keywords:")
        print(matched_keywords_str)
        print()
        print("Selected Agent:")
        print(selected_agent_name)
        print()
        print("Domain Selected:")
        print(selected_domain)
        print()
        print("Confidence:")
        print(f"{confidence:.2f}")
        print()
        print("=" * 52)
        
        # Perform retrieval and printing of candidate documents
        raw_ans = agent.answer(query, routing_confidence=confidence)
        
        # Parse returned answer to separate answer and source
        if "\n\n[Source: " in raw_ans:
            answer_part, source_part = raw_ans.split("\n\n[Source: ", 1)
            source_part = source_part.rstrip("]")
        else:
            answer_part = raw_ans
            source_part = f"{selected_domain.title().replace('_', ' ')}"
            
        # Print ANSWER and SOURCE sections
        print("ANSWER")
        print("======")
        print()
        print(answer_part)
        print()
        print("=" * 52)
        print("SOURCE")
        print("======")
        print()
        print(source_part)
        print()
        print("=" * 52)
        
        return raw_ans

if __name__ == "__main__":
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
            if "\n\n[Source: " in raw_ans:
                ans_text, _ = raw_ans.split("\n\n[Source: ", 1)
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
