# riar/schemas/log_schema.py
from pydantic import BaseModel
from typing import Optional, Literal, Dict, List
from datetime import datetime

class RIARLogEntry(BaseModel):
    # Identity
    session_id:               str
    turn_id:                  int
    timestamp:                datetime
    condition:                Literal["RIAR", "BASELINE"]

    # Input
    raw_query:                str
    language:                 Literal["en", "hi", "kn"]

    # Probe
    probe_domain_scores:      Dict[str, float]
    probe_top_domains:        List[str]
    probe_latency_ms:         int

    # Classification
    ambiguity_score:          float
    ambiguity_type:           Literal["CLEAR","SEMANTIC","CONTEXTUAL","CROSS_DOMAIN"]
    classification_confidence:float
    classification_model:     str
    classification_latency_ms:int
    fallback_used:            bool

    # Clarification
    clarification_triggered:  bool
    clarification_question:   Optional[str]
    clarification_response:   Optional[str]
    clarification_latency_ms: Optional[int]

    # Routing
    domain_routed:            str
    routing_latency_ms:       int

    # Answer
    resolved_query:           str
    answer_text:              str
    crag_score:               float
    answer_latency_ms:        int

    # Post-session (filled later)
    user_rating:              Optional[int]
    task_completed:           Optional[bool]
    faithfulness_score:       Optional[float]

    # Pipeline total
    total_latency_ms:         int
