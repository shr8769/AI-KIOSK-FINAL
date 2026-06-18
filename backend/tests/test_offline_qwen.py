"""
Tests for local Qwen (Ollama) offline fallback configuration.
"""

import os
import sys
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from agents.domain.gemini_rag import GeminiSynthesizer  # noqa: E402

from app.core.dependencies import get_riar_pipeline  # noqa: E402


@patch("langchain_community.chat_models.ChatOllama")
def test_get_riar_pipeline_offline_fallback(mock_chat_ollama):
    """Test get_riar_pipeline uses ChatOllama when GOOGLE_API_KEY is not set."""
    # Temporarily remove GOOGLE_API_KEY from environment
    with patch.dict(os.environ, {}, clear=True):
        # Clear the lru_cache of get_riar_pipeline to force re-evaluation
        get_riar_pipeline.cache_clear()

        pipeline = get_riar_pipeline()

        # Verify ChatOllama was instantiated with model "qwen3:latest"
        mock_chat_ollama.assert_called_once_with(model="qwen3:latest")
        assert pipeline.llm_client == mock_chat_ollama.return_value


@patch("langchain_community.chat_models.ChatOllama")
def test_gemini_synthesizer_offline_fallback_init(mock_chat_ollama):
    """Test GeminiSynthesizer falls back to local ChatOllama when GEMINI_API_KEY is missing."""
    # Temporarily remove GEMINI_API_KEY
    with patch.dict(os.environ, {}, clear=True):
        synthesizer = GeminiSynthesizer()

        assert synthesizer.client is None
        mock_chat_ollama.assert_called_once_with(model="qwen3:latest")
        assert synthesizer.ollama_client == mock_chat_ollama.return_value


@patch("langchain_community.chat_models.ChatOllama")
def test_gemini_synthesizer_synthesize_and_sufficiency_fallback(mock_chat_ollama):
    """Test GeminiSynthesizer.synthesize and check_sufficiency call ChatOllama fallback."""
    mock_ollama_instance = mock_chat_ollama.return_value

    # Mock return values for Ollama invoke
    mock_response = MagicMock()
    mock_response.content = "This is a synthesized test answer using local Qwen."
    mock_ollama_instance.invoke.return_value = mock_response

    with patch.dict(os.environ, {}, clear=True):
        synthesizer = GeminiSynthesizer()

        # 1. Test synthesize
        context_docs = [{"id": "doc1", "document": "Test content about Pes University admissions."}]
        answer = synthesizer.synthesize(
            query="How to apply?",
            context_docs=context_docs,
            domain="admissions"
        )

        assert answer == "This is a synthesized test answer using local Qwen."
        mock_ollama_instance.invoke.assert_called_once()

        # Reset mock call count
        mock_ollama_instance.invoke.reset_mock()

        # 2. Test check_sufficiency
        mock_response.content = "SUFFICIENT"
        decision = synthesizer.check_sufficiency(
            query="How to apply?",
            context_docs=context_docs,
            domain="admissions"
        )

        assert decision == "SUFFICIENT"
        mock_ollama_instance.invoke.assert_called_once()
