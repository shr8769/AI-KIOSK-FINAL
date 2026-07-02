import os
import sys
import concurrent.futures
from typing import Tuple

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
    agent based on explicit domain assignment from the RIAR Pipeline.
    """
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "vectorstore"))
            
        self.client = chromadb.PersistentClient(path=db_path)
        
        self.agents = {
            "admissions": AdmissionsAgent(client=self.client),
            "academics": AcademicsAgent(client=self.client),
            "placements": PlacementsAgent(client=self.client),
            "research": ResearchAgent(client=self.client),
            "student_services": StudentServicesAgent(client=self.client),
            "navigation": NavigationAgent(client=self.client)
        }

    def answer(self, query: str, target_domain: str = None) -> str:
        """
        Retrieves the answer from the specified domain agent.
        If no target_domain is provided, falls back to a general response.
        
        Args:
            query (str): The user search query.
            target_domain (str): The strictly predicted domain from the RIAR pipeline.
            
        Returns:
            str: The final answer or fallback response.
        """
        try:
            from agents.concierge.language_fallback import GeminiTranslator
            translator = GeminiTranslator()
            english_query, detected_lang = translator.translate_to_english(query)
        except Exception as e:
            print(f"[Warning] Translation initialization failed: {e}. Passing query through.")
            english_query = query
            detected_lang = "en"

        # Check if a strong match exists
        if not target_domain or target_domain == "general" or target_domain not in self.agents:
            best_agent_domain = None
            best_score = -1.0
            
            for domain_name, agent in self.agents.items():
                try:
                    docs = agent.retrieve(english_query)
                    if docs:
                        best_doc = docs[0]
                        sim_score = 1.0 / (1.0 + best_doc["distance"])
                        if sim_score >= getattr(agent, "similarity_threshold", 0.58):
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
                fallback_msg = (
                    "Sorry, I could not find information regarding this in the university knowledge base. "
                    "Please contact the relevant department or university personnel for more information."
                )
                
                if detected_lang in ["kn", "hi"]:
                    try:
                        fallback_msg = translator.translate_from_english(fallback_msg, detected_lang)
                    except Exception:
                        pass
    
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
                return f"{fallback_msg}\n\n[Source: None]"
            
        selected_agent = self.agents[target_domain]
        selected_agent_name = selected_agent.__class__.__name__
        
        # Print USER QUERY and ROUTING DECISION
        print("=" * 52)
        print("USER QUERY")
        print("==========")
        print()
        print(query)
        print()
        if detected_lang in ["kn", "hi"]:
            print(f"Translated to English: {english_query}")
            print()
        print("=" * 52)
        print("ROUTING DECISION (VIA RIAR)")
        print("================")
        print()
        print("Selected Agent:")
        print(selected_agent_name)
        print()
        print("Domain Selected:")
        print(target_domain)
        print()
        print("=" * 52)
        
        # Retrieve answer from the targeted agent
        try:
            raw_ans = selected_agent.answer(english_query, routing_confidence=1.0)
        except Exception as exc:
            print(f"[Error] Agent {target_domain} generated an exception: {exc}")
            raw_ans = "I encountered an error retrieving that information."

        # Parse returned answer to separate answer and source
        if target_domain == "navigation":
            # NavigationAgent returns raw JSON. Pass it through untouched.
            answer_part = raw_ans
            source_part = ""
            raw_ans = answer_part # Avoid appending source
        elif "\n\n[Source: " in raw_ans:
            answer_part, source_part = raw_ans.split("\n\n[Source: ", 1)
            source_part = "\n\n[Source: " + source_part
            raw_ans = answer_part + source_part
        else:
            answer_part = raw_ans
            source_part = f"\n\n[Source: {target_domain.title().replace('_', ' ')}]"
            raw_ans = answer_part + source_part
            
        # Translate the answer back if needed (Skip for navigation JSON)
        if detected_lang in ["kn", "hi"] and target_domain != "navigation":
            try:
                translated_ans = translator.translate_from_english(answer_part, detected_lang)
                answer_part = translated_ans
                raw_ans = answer_part + source_part
            except Exception as e:
                print(f"[Warning] Translation of response failed: {e}")

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
        print(source_part.replace("\n\n[Source: ", "").rstrip("]"))
        print()
        print("=" * 52)
        
        return raw_ans

if __name__ == "__main__":
    print("====================================")
    print("CAMPUS AI BRAIN (RIAR MODE)")
    print("====================================")
    print("Type 'exit' to quit.")
    
    coordinator = CoordinatorAgent()
    
    # We load the full RIAR pipeline for CLI testing
    from app.core.dependencies import get_riar_pipeline
    pipeline = get_riar_pipeline()
    
    while True:
        try:
            query = input("\nEnter your query:\n").strip()
            if query.lower() == "exit":
                print("\nGoodbye!")
                break
            if not query:
                continue
                
            # 1. Run pipeline
            riar_result = pipeline.run(query=query, session_history=[], language="en")
            
            # 2. Check ambiguity
            if riar_result.ambiguity_detected:
                print("\n[AMBIGUITY DETECTED]")
                print(f"Type: {riar_result.ambiguity_type}")
                print(f"Clarification Needed: {riar_result.clarification_question}")
                print("=" * 52)
                continue
                
            # 3. Route if CLEAR
            target_domain = riar_result.selected_domain
            print(f"\nPipeline selected domain: {target_domain}")
            
            # Get response
            raw_ans = coordinator.answer(query, target_domain=target_domain)
            
            # Extract clean answer text
            if "\n\n[Source: " in raw_ans:
                ans_text, _ = raw_ans.split("\n\n[Source: ", 1)
            else:
                ans_text = raw_ans
                
            print("\nAnswer:")
            print(ans_text)
            print("=" * 52)
            
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
