"""
Cross-Domain Response Merger
Owner: Haseeb

Fuses multiple domain answers into a single cohesive response.
"""

import logging
from typing import Dict
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

CROSS_DOMAIN_PROMPT = """
You are the VidyaSahayak Kiosk AI Assistant.
A user has asked a question that spans multiple departments.
We have queried the relevant department agents and collected their answers.

USER'S QUERY: "{query}"

DEPARTMENT ANSWERS:
{domain_answers}

Your task:
Synthesize these answers into a single, cohesive, natural-sounding paragraph.
Do not say "According to Admissions..." or "Placements says...". Just provide the combined information directly as if you are the single source of truth.
Keep it concise, clear, and friendly.
"""


class CrossDomainMerger:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", CROSS_DOMAIN_PROMPT)]
        )

    def merge(self, query: str, domain_responses: Dict[str, str]) -> str:
        """
        Merges a dictionary of domain responses into a single string.
        """
        if not domain_responses:
            return ""
        if len(domain_responses) == 1:
            return list(domain_responses.values())[0]

        logger.info(
            f"Merging {len(domain_responses)} cross-domain responses for query: '{query}'"
        )

        domain_answers_text = ""
        for domain, response in domain_responses.items():
            # strip out the [Source: ...] part if it exists for cleaner LLM synthesis
            clean_resp = response.split("\n\n[Source:")[0].strip()
            domain_answers_text += f"[{domain.upper()}]:\n{clean_resp}\n\n"

        try:
            formatted = self.prompt.format_messages(
                query=query, domain_answers=domain_answers_text.strip()
            )
            result = self.llm.invoke(formatted)

            merged_text = result.content if hasattr(result, "content") else str(result)

            # Combine all sources for the final output
            all_sources = []
            for resp in domain_responses.values():
                if "\n\n[Source: " in resp:
                    src = resp.split("\n\n[Source: ")[1].rstrip("]")
                    all_sources.append(src)

            if all_sources:
                sources_str = " | ".join(all_sources)
                merged_text += f"\n\n[Source: {sources_str} (Cross-Domain)]"

            return merged_text
        except Exception as e:
            logger.error(
                f"CrossDomainMerger failed: {e}. Returning concatenated fallback."
            )
            fallback = "\n\n".join(domain_responses.values())
            return fallback
