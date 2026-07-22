import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class SessionHistoryManager:
    _conversations: Dict[str, List[Dict[str, str]]] = {}

    @classmethod
    def append_turn(cls, session_id: str, query: str, answer: str):
        if session_id not in cls._conversations:
            cls._conversations[session_id] = []
        cls._conversations[session_id].append({"query": query, "answer": answer})
        logger.info(f"Turn added to session {session_id}. History size: {len(cls._conversations[session_id])}")

    @classmethod
    def get_history(cls, session_id: str) -> List[Dict[str, str]]:
        return cls._conversations.get(session_id, [])

    @classmethod
    def get_history_text(cls, session_id: str) -> str:
        turns = cls.get_history(session_id)
        if not turns:
            return ""
        lines = []
        for turn in turns:
            lines.append(f"User: {turn['query']}")
            lines.append(f"Agent: {turn['answer']}")
        return "\n".join(lines)

    @classmethod
    def clear_history(cls, session_id: str):
        if session_id in cls._conversations:
            del cls._conversations[session_id]
            logger.info(f"Cleared history for session {session_id}")
