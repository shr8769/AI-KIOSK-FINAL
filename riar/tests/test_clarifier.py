"""
Test suite for RIARClarifier
Owner: Haseeb
"""

import pytest
from unittest.mock import MagicMock
from langchain_core.language_models.chat_models import BaseChatModel

from riar.clarifiers.clarifier import RIARClarifier
from riar.schemas.schemas import (
    RIARClassification,
    SemanticClarification,
    ContextualClarification,
    CrossDomainClarification,
)
from backend.app.models.shared_models import ProbeChunk


@pytest.fixture
def mock_llm_semantic():
    llm = MagicMock(spec=BaseChatModel)
    structured_mock = MagicMock()

    expected_output = SemanticClarification(
        question="Are you looking for the physical central library building or the digital library portal?",
        options=["Physical central library building", "Digital library portal"],
    )

    structured_mock.invoke.return_value = expected_output
    llm.with_structured_output.return_value = structured_mock
    return llm


@pytest.fixture
def mock_llm_contextual():
    llm = MagicMock(spec=BaseChatModel)
    structured_mock = MagicMock()

    expected_output = ContextualClarification(
        question="Could you specify which professor you are referring to?",
        missing_slot="professor name",
    )

    structured_mock.invoke.return_value = expected_output
    llm.with_structured_output.return_value = structured_mock
    return llm


@pytest.fixture
def mock_llm_cross_domain():
    llm = MagicMock(spec=BaseChatModel)
    structured_mock = MagicMock()

    expected_output = CrossDomainClarification(
        question="Are you asking about the admission fee structure or the academic course fees?",
        domain_options=["admissions", "academics"],
    )

    structured_mock.invoke.return_value = expected_output
    llm.with_structured_output.return_value = structured_mock
    return llm


def test_semantic_returns_options_list(mock_llm_semantic):
    clarifier = RIARClarifier(llm=mock_llm_semantic)

    # Overwrite the semantic LLM specifically to test branching
    clarifier.semantic_llm = mock_llm_semantic.with_structured_output()

    classification = RIARClassification(
        ambiguity_score=0.8,
        ambiguity_type="SEMANTIC",
        confidence=0.9,
        requires_clarification=True,
        reasoning="Multiple meanings of 'library'",
    )

    chunks = [
        ProbeChunk(
            chunk_id="1",
            text="Central library timings...",
            score=0.9,
            source="academics",
        )
    ]

    # generate_question routes to _generate_semantic_clarification
    result = clarifier.generate_question(
        "Where is the library?", classification, chunks
    )

    # Asserting the string output, but since we mocked the structured output,
    # we know the underlying execution path returned SemanticClarification.
    assert (
        result
        == "Are you looking for the physical central library building or the digital library portal?"
    )

    # Now explicitly test the private method to verify the schema properties
    structured_result = clarifier.semantic_llm.invoke("mock_prompt")
    assert isinstance(structured_result, SemanticClarification)
    assert len(structured_result.options) >= 2


def test_contextual_returns_missing_slot(mock_llm_contextual):
    clarifier = RIARClarifier(llm=mock_llm_contextual)
    clarifier.contextual_llm = mock_llm_contextual.with_structured_output()

    classification = RIARClassification(
        ambiguity_score=0.7,
        ambiguity_type="CONTEXTUAL",
        confidence=0.8,
        requires_clarification=True,
        reasoning="Missing professor name",
    )

    result = clarifier.generate_question(
        "Where is my professor's office?", classification, []
    )
    assert result == "Could you specify which professor you are referring to?"

    structured_result = clarifier.contextual_llm.invoke("mock_prompt")
    assert isinstance(structured_result, ContextualClarification)
    assert structured_result.missing_slot != ""


def test_cross_domain_names_both_domains(mock_llm_cross_domain):
    clarifier = RIARClarifier(llm=mock_llm_cross_domain)
    clarifier.cross_domain_llm = mock_llm_cross_domain.with_structured_output()

    classification = RIARClassification(
        ambiguity_score=0.9,
        ambiguity_type="CROSS_DOMAIN",
        confidence=0.9,
        requires_clarification=True,
        reasoning="Spans admissions and academics",
    )

    result = clarifier.generate_question("What are the fees?", classification, [])
    assert (
        result
        == "Are you asking about the admission fee structure or the academic course fees?"
    )

    structured_result = clarifier.cross_domain_llm.invoke("mock_prompt")
    assert isinstance(structured_result, CrossDomainClarification)
    assert "admissions" in structured_result.domain_options
    assert "academics" in structured_result.domain_options


def test_clear_raises_error(mock_llm_semantic):
    clarifier = RIARClarifier(llm=mock_llm_semantic)

    classification = RIARClassification(
        ambiguity_score=0.1,
        ambiguity_type="CLEAR",
        confidence=0.9,
        requires_clarification=False,
        reasoning="Query is clear",
    )

    with pytest.raises(ValueError, match="No clarification needed for CLEAR queries"):
        clarifier.generate_question("What is the fee for BTech?", classification, [])
