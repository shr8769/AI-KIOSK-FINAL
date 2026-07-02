"""
RIAR Classifier — Step 2
Owner: Haseeb

Classifies query ambiguity using a structured LLM call (temporarily Gemini,
designed for Qwen 8B). Implements a strict fallback path if the LLM fails.
"""

import logging
from typing import Dict, Any, List
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from riar.schemas.schemas import RIARClassification

logger = logging.getLogger(__name__)

CLASSIFIER_PROMPT = """
You are the Ambiguity Classification Engine for VidyaSahayak, the PES University Kiosk.
Analyze the user's query along with the domain signals collected from a vector database probe.

Your job is to determine if the query is clear enough to route directly to a domain expert, 
or if it is ambiguous and requires clarification from the user.

CONVERSATION HISTORY:
{history}

USER QUERY: "{query}"

PROBE DOMAIN SIGNALS (0.0 to 1.0):
{domain_signals}

TOP DETECTED DOMAINS: {top_domains}

AMBIGUITY TYPES:
- CLEAR: The query is highly specific, complete, and maps cleanly to one domain.
- SEMANTIC: The query uses vague words (e.g., "the program", "it") missing key entities.
- CONTEXTUAL: The query lacks time, location, or subject context (e.g., "when does it start?").
- CROSS_DOMAIN: The query spans multiple distinct domains (e.g., "how do placements affect research?").

Output your strict JSON classification according to the schema. 
"""


class RIARClassifier:
    def __init__(self, llm: BaseChatModel):
        """
        Args:
            llm: A LangChain ChatModel (e.g., ChatOllama or ChatGoogleGenerativeAI)
                 that supports .with_structured_output()
        """
        self.llm = llm

        # Bind the Pydantic schema to the LLM to enforce strict JSON output
        try:
            self.structured_llm = self.llm.with_structured_output(RIARClassification)
        except Exception as e:
            logger.warning(f"LLM does not support native structured output. Error: {e}")
            self.structured_llm = None

        self.prompt = ChatPromptTemplate.from_messages([("system", CLASSIFIER_PROMPT)])

    def classify(
        self,
        query: str,
        domain_scores: Dict[str, float],
        session_history: List[Any] = None,
    ) -> RIARClassification:
        """
        Classify the ambiguity of the query.

        Args:
            query: The raw user query.
            domain_scores: Dictionary of domain -> normalized confidence score from the Probe.

        Returns:
            A strictly validated RIARClassification Pydantic object.
        """
        if not self.structured_llm:
            logger.error("Structured LLM is not initialized. Using fallback.")
            return self._fallback_classification(query)

        # Format domain signals for the prompt
        signals_str = (
            "\n".join([f"- {d}: {s:.2f}" for d, s in domain_scores.items()])
            if domain_scores
            else "No strong signals."
        )
        top_domains = [d for d, s in domain_scores.items() if s > 0.45]

        # Format history
        history_str = "No prior context."
        if session_history:
            history_str = "\n".join(
                [f"{t.role.upper()}: {t.text}" for t in session_history]
            )

        try:
            formatted_messages = self.prompt.format_messages(
                history=history_str,
                query=query,
                domain_signals=signals_str,
                top_domains=", ".join(top_domains) if top_domains else "None",
            )

            result = self.structured_llm.invoke(formatted_messages)

            # Ensure it's the correct type (some older LC versions return dicts)
            if isinstance(result, dict):
                return RIARClassification(**result)
            return result

        except Exception as e:
            logger.error(
                f"Structured LLM classification failed: {e}. Triggering fallback path."
            )
            return self._fallback_classification(query)

    def _fallback_classification(self, query: str) -> RIARClassification:
        """
        Immediate fallback path if the local LLM times out, crashes, or produces invalid JSON.
        We default to a safe CROSS_DOMAIN ambiguity requiring clarification, to avoid hallucinating.
        """
        return RIARClassification(
            ambiguity_score=0.85,
            ambiguity_type="CROSS_DOMAIN",
            confidence=0.5,
            requires_clarification=True,
            reasoning="Fallback triggered due to LLM failure. Query marked ambiguous for safety.",
        )
