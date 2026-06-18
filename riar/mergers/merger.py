"""
RIAR Merger
Owner: Haseeb

Merges an ambiguous query and the user's clarification response into a single resolved query.
"""
import logging
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from riar.schemas.schemas import RIARQueryMerger

logger = logging.getLogger(__name__)

MERGER_PROMPT = """
You are the Query Resolution Engine for VidyaSahayak.
The user asked an ambiguous query, we asked for clarification, and the user responded.
Your job is to merge the original query and the user's clarification into a single, complete, self-contained query.

ORIGINAL AMBIGUOUS QUERY: "{original_query}"
OUR CLARIFICATION QUESTION: "{clarification_question}"
USER'S RESPONSE: "{user_response}"

Rewrite this as one complete, standalone question that can be sent to a search engine.
Output your merged query using the strict JSON schema.
"""

class RIARMerger:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        try:
            self.structured_llm = self.llm.with_structured_output(RIARQueryMerger)
        except Exception as e:
            logger.warning(f"LLM doesn't support structured output: {e}")
            self.structured_llm = None
            
        self.prompt = ChatPromptTemplate.from_messages([("system", MERGER_PROMPT)])
        
    def merge(self, original_query: str, clarification_question: str, user_response: str) -> str:
        if not self.structured_llm:
            logger.error("Structured LLM missing in Merger. Using fallback.")
            return f"{original_query} {user_response}"
            
        try:
            formatted = self.prompt.format_messages(
                original_query=original_query,
                clarification_question=clarification_question,
                user_response=user_response
            )
            result = self.structured_llm.invoke(formatted)
            if isinstance(result, dict):
                return result.get("resolved_query", f"{original_query} {user_response}")
            return result.resolved_query
        except Exception as e:
            logger.error(f"Merger LLM failed: {e}. Using fallback merge.")
            return f"{original_query} {user_response}"
