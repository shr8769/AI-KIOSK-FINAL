import json
import logging
import re

from agents.llm.qwen_client import QwenClient

logger = logging.getLogger(__name__)


class MemorySummary:
    def __init__(self):
        self.llm_client = QwenClient()

    def generate_summary(self, conversation_text: str) -> dict:
        """
        Summarizes conversation content and extracts the primary topic.
        Returns a dict: {"summary": "...", "topic": "..."}
        """
        prompt = f"""Analyze this conversation snippet:
"{conversation_text}"

1. Provide a short, concise summary of the user's key intent or request (max 15 words).
2. Identify a single-word or short-phrase topic/category for this request (e.g. admissions, academics, placements, research, navigation, billing, general).

Respond strictly in JSON format as follows:
{{
  "summary": "concise summary text",
  "topic": "topic name"
}}"""
        try:
            response = self.llm_client.generate(prompt)
            if response:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    return {
                        "summary": data.get("summary", "").strip(),
                        "topic": data.get("topic", "general").strip().lower()
                    }
        except Exception as e:
            logger.error(f"Error generating memory summary from LLM: {e}")

        # Simple local rule-based fallback if LLM parser fails
        words = conversation_text.split()
        summary = " ".join(words[:8]) + ("..." if len(words) > 8 else "")

        # Simple keyword matching for topic
        topic = "general"
        text_lower = conversation_text.lower()
        if "admission" in text_lower or "apply" in text_lower or "pessat" in text_lower:
            topic = "admissions"
        elif "course" in text_lower or "syllabus" in text_lower or "class" in text_lower:
            topic = "academics"
        elif "job" in text_lower or "placement" in text_lower or "recruit" in text_lower:
            topic = "placements"
        elif "direction" in text_lower or "where" in text_lower or "building" in text_lower or "map" in text_lower:
            topic = "navigation"

        return {
            "summary": summary,
            "topic": topic
        }
