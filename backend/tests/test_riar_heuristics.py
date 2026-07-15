from unittest.mock import MagicMock

import pytest
from riar.clarifiers.clarifier import RIARClarifier
from riar.classifiers.classifier import RIARClassifier
from riar.heuristics import get_heuristic_match
from riar.mergers.merger import RIARMerger

from app.services.query_pipeline import local_spelling_corrector


def test_heuristic_matching():
    # 1. Test microsoft pattern
    h1 = get_heuristic_match("what is microsoft?")
    assert h1 is not None
    assert h1["key"] == "microsoft"
    assert "Microsoft campus placements" in h1["question"]

    # 2. Test exclusions
    h2 = get_heuristic_match("what is microsoft placements?")
    assert h2 is None

    # 3. Test fees pattern
    h3 = get_heuristic_match("tell me about the fees")
    assert h3 is not None
    assert h3["key"] == "fees"

    # 4. Test admissions pattern
    h4 = get_heuristic_match("how to get admission")
    assert h4 is not None
    assert h4["key"] == "admissions"

    # 5. Test internships pattern
    h5 = get_heuristic_match("tell me about internships")
    assert h5 is not None
    assert h5["key"] == "internship"


def test_classifier_heuristics():
    # Even with a dummy LLM, classification should resolve matched heuristics fast-path
    mock_llm = MagicMock()
    classifier = RIARClassifier(llm=mock_llm)

    result = classifier.classify("what is microsoft?", {})
    assert result.requires_clarification is True
    assert result.ambiguity_type == "CROSS_DOMAIN"
    assert "heuristic" in result.reasoning.lower()


def test_clarifier_heuristics():
    mock_llm = MagicMock()
    clarifier = RIARClarifier(llm=mock_llm)

    classification = MagicMock()
    classification.ambiguity_type = "CROSS_DOMAIN"

    question = clarifier.generate_question("what is microsoft?", classification)
    assert "Microsoft campus placements" in question


def test_merger_heuristics():
    mock_llm = MagicMock()
    merger = RIARMerger(llm=mock_llm)

    # Placements response
    merged = merger.merge("what is microsoft?", "Are you interested in Microsoft...", "placements")
    assert "recruitment process for Microsoft" in merged

    # Internship response
    merged = merger.merge("what is microsoft?", "Are you interested in Microsoft...", "internships")
    assert "Engage mentorship and internship" in merged

    # Default fallback response
    merged = merger.merge("what is microsoft?", "Are you interested in Microsoft...", "random option")
    assert "tuition fee structures" not in merged
    assert "recruitment details, eligibility criteria, and internship" in merged


def test_local_spelling_corrector():
    # Test common typos
    assert local_spelling_corrector("what is micosoft?") == "what is microsoft?"
    assert local_spelling_corrector("admisions requirements") == "admissions requirements"
    assert local_spelling_corrector("pacement stats") == "placement stats"


@pytest.mark.anyio
async def test_single_word_forcing_ambiguity():
    # 1. Test classifier forcing ambiguity for 1 word
    mock_llm = MagicMock()
    classifier = RIARClassifier(llm=mock_llm)
    res = classifier.classify("placement", {})
    assert res.requires_clarification is True
    assert res.ambiguity_type == "SEMANTIC"
    assert "Single-word query" in res.reasoning

    # 2. Test correct_and_normalize_query bypasses LLM call for 1 word
    from app.services.query_pipeline import correct_and_normalize_query
    # Even if LLM isn't mocked/active, a single word should return immediately with spelling corrected
    res_query = await correct_and_normalize_query("placements")
    assert res_query == "placements"

