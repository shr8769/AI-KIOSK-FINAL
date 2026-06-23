"""
RIAR Clarifier
Owner: Haseeb

Generates a targeted, natural question to ask the user when a query is deemed ambiguous.
Implements strict typed branching based on the ambiguity classification type.
"""
import logging
from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from riar.schemas.schemas import (
    RIARClassification, 
    SemanticClarification, 
    ContextualClarification, 
    CrossDomainClarification
)

logger = logging.getLogger(__name__)

SEMANTIC_PROMPT = """
You are the Clarification Engine for VidyaSahayak, the PES University Kiosk.
The user asked a query that has multiple valid semantic interpretations.

CONVERSATION HISTORY:
{history}

USER QUERY: "{query}"

PROBE CONTEXT (Domain Signals & Hits):
{probe_context}

The query has multiple valid interpretations found in the corpus.
Generate a clarification question that presents these as a binary or multi-choice option, referencing the specific interpretations found. Do not ask an open-ended question.
"""

CONTEXTUAL_PROMPT = """
You are the Clarification Engine for VidyaSahayak, the PES University Kiosk.
The user asked a query that is missing necessary context.

CONVERSATION HISTORY:
{history}

USER QUERY: "{query}"

PROBE CONTEXT (Domain Signals & Hits):
{probe_context}

The query is missing a required slot (e.g. professor name, department, deadline name). 
Generate a clarification question that asks specifically for this missing slot. Do not ask a general 'can you clarify' question.
"""

CROSS_DOMAIN_PROMPT = """
You are the Clarification Engine for VidyaSahayak, the PES University Kiosk.
The user asked a query that spans multiple domains.

CONVERSATION HISTORY:
{history}

USER QUERY: "{query}"

PROBE CONTEXT (Domain Signals & Hits):
{probe_context}

The query spans these domains with these confidence scores. 
Generate a clarification question that asks the user to confirm which domain is the priority, explicitly naming both domains found.
"""


class RIARClarifier:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        
        try:
            self.semantic_llm = self.llm.with_structured_output(SemanticClarification)
            self.contextual_llm = self.llm.with_structured_output(ContextualClarification)
            self.cross_domain_llm = self.llm.with_structured_output(CrossDomainClarification)
        except Exception as e:
            logger.warning(f"LLM doesn't support structured output: {e}")
            self.semantic_llm = None
            self.contextual_llm = None
            self.cross_domain_llm = None

        self.semantic_prompt = ChatPromptTemplate.from_messages([("system", SEMANTIC_PROMPT)])
        self.contextual_prompt = ChatPromptTemplate.from_messages([("system", CONTEXTUAL_PROMPT)])
        self.cross_domain_prompt = ChatPromptTemplate.from_messages([("system", CROSS_DOMAIN_PROMPT)])
        
    def generate_question(self, query: str, classification: RIARClassification, probe_chunks: list[Any] = None, session_history: list[Any] = None) -> str:
        """
        Router function to dispatch to the correct clarification strategy.
        """
        ambiguity_type = classification.ambiguity_type
        
        history_str = "No prior context."
        if session_history:
            history_str = "\n".join([f"{t.role.upper()}: {t.text}" for t in session_history])
        
        # Build context string from probe chunks to pass to the prompts
        probe_context = "No chunks provided."
        if probe_chunks:
            probe_context = "\n".join([f"Domain: {c.source} | Text: {c.text}" for c in probe_chunks[:5]])
            
        if ambiguity_type == "SEMANTIC":
            return self._generate_semantic_clarification(probe_context, query, history_str)
        elif ambiguity_type == "CONTEXTUAL":
            return self._generate_contextual_clarification(probe_context, query, history_str)
        elif ambiguity_type == "CROSS_DOMAIN":
            return self._generate_cross_domain_clarification(probe_context, query, history_str)
        elif ambiguity_type == "CLEAR":
            raise ValueError(f"No clarification needed for CLEAR queries.")
        else:
            raise ValueError(f"Unknown ambiguity type: {ambiguity_type}")

    def _generate_semantic_clarification(self, probe_context: str, query: str, history_str: str) -> str:
        if not self.semantic_llm:
            return "Do you mean option A or option B?"
        try:
            formatted = self.semantic_prompt.format_messages(history=history_str, query=query, probe_context=probe_context)
            result = self.semantic_llm.invoke(formatted)
            return result.get("question", "Can you clarify?") if isinstance(result, dict) else result.question
        except Exception as e:
            logger.error(f"Semantic clarifier failed: {e}")
            return "Could you please specify which interpretation you mean?"

    def _generate_contextual_clarification(self, probe_context: str, query: str, history_str: str) -> str:
        if not self.contextual_llm:
            return "What specific detail is missing?"
        try:
            formatted = self.contextual_prompt.format_messages(history=history_str, query=query, probe_context=probe_context)
            result = self.contextual_llm.invoke(formatted)
            return result.get("question", "Can you clarify?") if isinstance(result, dict) else result.question
        except Exception as e:
            logger.error(f"Contextual clarifier failed: {e}")
            return "Could you provide a bit more context?"

    def _generate_cross_domain_clarification(self, probe_context: str, query: str, history_str: str) -> str:
        if not self.cross_domain_llm:
            return "Which domain is your priority?"
        try:
            formatted = self.cross_domain_prompt.format_messages(history=history_str, query=query, probe_context=probe_context)
            result = self.cross_domain_llm.invoke(formatted)
            return result.get("question", "Can you clarify?") if isinstance(result, dict) else result.question
        except Exception as e:
            logger.error(f"Cross-domain clarifier failed: {e}")
            return "Which department's perspective are you asking about?"
