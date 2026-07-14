"""
RIAR Pydantic Schemas
Owner: Haseeb
Defines the strict structured output models used by the Local LLM (Ollama)
during the RIAR pipeline execution. No logic, just schemas.
"""

from pydantic import BaseModel, Field
from typing import Literal


class RIARClassification(BaseModel):
    """
    Step 1: Unified Ambiguity Classification output.
    The local LLM must return exactly this structure.
    """

    ambiguity_score: float = Field(
        ...,
        description="A float between 0.0 and 1.0 indicating how ambiguous the query is.",
        ge=0.0,
        le=1.0,
    )
    ambiguity_type: Literal["CLEAR", "SEMANTIC", "CONTEXTUAL", "CROSS_DOMAIN"] = Field(
        ..., description="The category of the query. CLEAR means no ambiguity."
    )
    confidence: float = Field(
        ...,
        description="Confidence score of this classification (0.0 to 1.0).",
        ge=0.0,
        le=1.0,
    )
    requires_clarification: bool = Field(
        ...,
        description="True if the query is too ambiguous to answer without asking the user for clarification.",
    )
    reasoning: str = Field(
        ...,
        description="A short, 1-sentence explanation of why this classification was chosen.",
    )


class SemanticClarification(BaseModel):
    """
    Step 2a: Used when ambiguity_type is SEMANTIC.
    Generates a binary or multi-choice question from specific interpretations.
    """

    question: str = Field(
        ...,
        description="A clarification question presenting the options as a binary or multi-choice question.",
    )
    options: list[str] = Field(
        ...,
        description="2-4 distinct interpretations pulled directly from the domain hits.",
        min_length=2,
        max_length=4,
    )


class ContextualClarification(BaseModel):
    """
    Step 2b: Used when ambiguity_type is CONTEXTUAL.
    Asks the user for a specific missing slot.
    """

    question: str = Field(
        ...,
        description="A targeted question asking the user to provide the missing slot.",
    )
    missing_slot: str = Field(
        ...,
        description="The name of the missing slot (e.g. professor name, department, deadline name).",
    )


class CrossDomainClarification(BaseModel):
    """
    Step 2c: Used when ambiguity_type is CROSS_DOMAIN.
    Asks the user to prioritize between the conflicting domains.
    """

    question: str = Field(
        ...,
        description="A clarification question asking the user which domain is the priority.",
    )
    domain_options: list[str] = Field(
        ..., description="The names of the specific domains found.", min_length=2
    )


class RIARRouting(BaseModel):
    """
    Step 3: Domain Routing output.
    Used to route a CLEAR or properly refined query to the correct Domain Agent.
    """

    domain: Literal[
        "admissions",
        "academics",
        "placements",
        "research",
        "navigation",
        "student_services",
        "general",
    ] = Field(
        ...,
        description="The specific knowledge domain that is best suited to answer this query.",
    )
    confidence: float = Field(
        ..., description="Routing confidence score (0.0 to 1.0).", ge=0.0, le=1.0
    )


class RIARQueryMerger(BaseModel):
    """
    Step 4 (After User Response): Merges the original ambiguous query with the user's clarification.
    """

    resolved_query: str = Field(
        ...,
        description="A complete, self-contained query combining the original intent with the user's new clarification.",
    )
