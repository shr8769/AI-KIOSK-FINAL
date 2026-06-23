"""
RIAR Router — Step 3
Owner: Haseeb

Routes a CLEAR query to a specific domain agent using the LLM.
"""

import logging
from typing import Dict, Any, List
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from riar.schemas.schemas import RIARRouting

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """
You are the Domain Router for VidyaSahayak, the PES University Kiosk.
The user's query has already been classified as CLEAR and ready for routing.
Your job is to select the SINGLE best domain to handle this query based on the query and the probe signals.

USER QUERY: "{query}"

PROBE DOMAIN SIGNALS (0.0 to 1.0):
{domain_signals}

TOP DETECTED DOMAINS: {top_domains}

DOMAINS:
- admissions: PESSAT, eligibility, fees, deadlines.
- academics: Exams, syllabus, grades, credits.
- placements: Jobs, internships, salaries, companies.
- research: PhD, publications, labs, grants.
- student_services: Hostels, libraries, sports, health center.
- navigation: Directions, building locations, finding offices.
- general: Any university query that doesn't fit the above.

Output your strict JSON classification according to the schema.
"""

class RIARRouter:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        
        try:
            self.structured_llm = self.llm.with_structured_output(RIARRouting)
        except Exception as e:
            logger.warning(f"LLM does not support native structured output for router. Error: {e}")
            self.structured_llm = None
            
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", ROUTER_PROMPT)
        ])
        
    def route(self, query: str, domain_scores: Dict[str, float]) -> RIARRouting:
        if not self.structured_llm:
            logger.error("Structured LLM is not initialized for router. Using fallback.")
            return self._fallback_routing(domain_scores)

        signals_str = "\n".join([f"- {d}: {s:.2f}" for d, s in domain_scores.items()]) if domain_scores else "No strong signals."
        top_domains = [d for d, s in domain_scores.items() if s > 0.45]
        
        try:
            formatted_messages = self.prompt.format_messages(
                query=query,
                domain_signals=signals_str,
                top_domains=", ".join(top_domains) if top_domains else "None"
            )
            
            result = self.structured_llm.invoke(formatted_messages)
            
            if isinstance(result, dict):
                return RIARRouting(**result)
            return result
            
        except Exception as e:
            logger.error(f"Structured LLM routing failed: {e}. Triggering fallback path.")
            return self._fallback_routing(domain_scores)
            
    def _fallback_routing(self, domain_scores: Dict[str, float]) -> RIARRouting:
        # Fallback: Just pick the highest domain score, or general if none
        if domain_scores:
            best_domain = max(domain_scores.items(), key=lambda x: x[1])
            if best_domain[1] > 0.0:
                return RIARRouting(domain=best_domain[0], confidence=best_domain[1])
        return RIARRouting(domain="general", confidence=0.5)
