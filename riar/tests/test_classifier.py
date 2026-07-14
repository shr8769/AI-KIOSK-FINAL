"""
Test suite for RIARClassifier
Owner: Haseeb
"""

import pytest
import json
import os
from unittest.mock import MagicMock
from langchain_core.language_models.chat_models import BaseChatModel

from riar.classifiers.classifier import RIARClassifier
from riar.schemas.schemas import RIARClassification


@pytest.fixture
def fixtures_data():
    fixtures_path = os.path.join(os.path.dirname(__file__), "fixtures.json")
    with open(fixtures_path, "r") as f:
        return json.load(f)


@pytest.fixture
def mock_llm_clear():
    """Mocks an LLM that always classifies as CLEAR"""
    llm = MagicMock(spec=BaseChatModel)
    structured_mock = MagicMock()

    expected_output = RIARClassification(
        ambiguity_score=0.1,
        ambiguity_type="CLEAR",
        confidence=0.95,
        requires_clarification=False,
        reasoning="The query is highly specific and maps cleanly to one domain.",
    )

    structured_mock.invoke.return_value = expected_output
    llm.with_structured_output.return_value = structured_mock
    return llm


@pytest.fixture
def mock_llm_error():
    """Mocks an LLM that throws an exception to trigger the fallback path"""
    llm = MagicMock(spec=BaseChatModel)
    structured_mock = MagicMock()

    structured_mock.invoke.side_effect = Exception("Ollama connection timeout")
    llm.with_structured_output.return_value = structured_mock
    return llm


def test_classifier_clear_query(mock_llm_clear):
    classifier = RIARClassifier(llm=mock_llm_clear)
    domain_scores = {"admissions": 0.9, "general": 0.1}

    result = classifier.classify("What is the B.Tech fee structure?", domain_scores)

    assert isinstance(result, RIARClassification)
    assert result.ambiguity_type == "CLEAR"
    assert result.requires_clarification is False
    assert result.ambiguity_score < 0.5


def test_classifier_fallback_path(mock_llm_error):
    classifier = RIARClassifier(llm=mock_llm_error)
    domain_scores = {"research": 0.5, "academics": 0.5}

    # Even though LLM raises an Exception, classify() should gracefully catch it and fallback
    result = classifier.classify("Tell me about it", domain_scores)

    assert isinstance(result, RIARClassification)
    assert result.requires_clarification is True
    assert result.ambiguity_type == "CROSS_DOMAIN"
    assert (
        result.reasoning
        == "Fallback triggered due to LLM failure. Query marked ambiguous for safety."
    )


def test_classifier_against_fixtures(fixtures_data, mock_llm_clear):
    """
    Ensure the classifier gracefully handles all fixture inputs without crashing.
    """
    classifier = RIARClassifier(llm=mock_llm_clear)
    all_queries = fixtures_data.get("clear_queries", []) + fixtures_data.get(
        "ambiguous_queries", []
    )

    for q_data in all_queries:
        query = q_data["query"]
        domain_scores = {"test_domain": 1.0}

        result = classifier.classify(query, domain_scores)
        assert isinstance(result, RIARClassification)
