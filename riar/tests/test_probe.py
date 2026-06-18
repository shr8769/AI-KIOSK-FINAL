"""
Test suite for ProbeRetriever
Owner: Haseeb
"""
import pytest
import json
import os
from unittest.mock import MagicMock
from riar.retrievers.probe import ProbeRetriever, CONFIDENCE_MEDIUM

@pytest.fixture
def fixtures_data():
    fixtures_path = os.path.join(os.path.dirname(__file__), "fixtures.json")
    with open(fixtures_path, "r") as f:
        return json.load(f)

@pytest.fixture
def mock_chroma_client():
    client = MagicMock()
    mock_collection = MagicMock()
    
    # Mock return data: cosine distance = 0.2 (confidence = 0.8)
    mock_collection.query.return_value = {
        "documents": [["Chunk 1", "Chunk 2"]],
        "metadatas": [[{"domain": "academics", "chunk_id": "c1"}, {"domain": "admissions", "chunk_id": "c2"}]],
        "distances": [[0.2, 0.6]] # 0.6 distance = 0.4 confidence (should be filtered out since < 0.45)
    }
    
    client.get_collection.return_value = mock_collection
    return client

@pytest.fixture
def mock_embedding_model():
    model = MagicMock()
    model.encode.return_value = [[0.1, 0.2, 0.3]]
    return model

def test_probe_filters_low_confidence(mock_chroma_client, mock_embedding_model):
    probe = ProbeRetriever(chroma_client=mock_chroma_client, embedding_model=mock_embedding_model)
    
    chunks, domain_scores = probe.retrieve("When do classes start?")
    
    # Since there are 6 collections, and each returns 2 chunks (one with 0.8 conf, one with 0.4 conf)
    # The 0.4 conf chunks should be filtered out entirely.
    assert len(chunks) == 6  # 1 valid chunk per collection * 6 collections
    
    for chunk in chunks:
        assert chunk.score >= CONFIDENCE_MEDIUM
        assert chunk.score == 0.8
        
def test_probe_domain_score_normalization(mock_chroma_client, mock_embedding_model):
    probe = ProbeRetriever(chroma_client=mock_chroma_client, embedding_model=mock_embedding_model)
    chunks, domain_scores = probe.retrieve("Tell me about the CSE department")
    
    # Since every collection returned an "academics" chunk (mock is hardcoded),
    # the academics domain should have 100% of the normalized score.
    assert "academics" in domain_scores
    assert sum(domain_scores.values()) == pytest.approx(1.0)
    assert domain_scores["academics"] == 1.0

def test_probe_against_fixtures(fixtures_data, mock_chroma_client, mock_embedding_model):
    """
    Ensure probe runs successfully against all queries in fixtures.json without crashing.
    """
    probe = ProbeRetriever(chroma_client=mock_chroma_client, embedding_model=mock_embedding_model)
    
    all_queries = fixtures_data.get("clear_queries", []) + fixtures_data.get("ambiguous_queries", [])
    
    for q_data in all_queries:
        query = q_data["query"]
        chunks, scores = probe.retrieve(query)
        assert isinstance(chunks, list)
        assert isinstance(scores, dict)
