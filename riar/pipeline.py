"""
RIAR Pipeline — Main Orchestrator
Owner: Haseeb (Research Lead)

This module implements the RIAR (Retrieval-Informed Ambiguity Resolution) framework.
It delegates all logic to specialized modules (Probe, Classifier, Clarifier, Router, Merger)
and acts purely as a stateless orchestrator.

CONTRACT (to Harsha):
    pipeline = RIARPipeline(vector_store, llm_client)
    result: RIARResult = pipeline.run(query, session_history, language)
    refined: RefinedQuery = pipeline.refine(original_query, clarification, ambiguity_type)
"""

import sys
import os
import time
import logging
from typing import List, Optional, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))

from backend.app.models.shared_models import (
    RIARResult, RefinedQuery, Turn
)

# Import specialized RIAR modules
from riar.retrievers.probe import ProbeRetriever
from riar.classifiers.classifier import RIARClassifier
from riar.clarifiers.clarifier import RIARClarifier
from riar.mergers.merger import RIARMerger

logger = logging.getLogger(__name__)


class RIARPipeline:
    """
    Main RIAR Pipeline Orchestrator.
    """

    MAX_LATENCY_MS = 2000  # Target SLA

    def __init__(self, vector_store: Any, llm_client: Any, embedding_model: Any = None):
        """
        Args:
            vector_store: ChromaDB client or compatible vector store.
            llm_client: A LangChain BaseChatModel (e.g. ChatOllama or ChatGoogleGenerativeAI).
            embedding_model: (Optional) sentence-transformers model.
        """
        self.vector_store = vector_store
        self.llm_client = llm_client
        
        logger.info("Initializing RIAR Pipeline modules...")
        self.probe = ProbeRetriever(chroma_client=vector_store, embedding_model=embedding_model)
        self.classifier = RIARClassifier(llm=llm_client)
        self.clarifier = RIARClarifier(llm=llm_client)
        self.merger = RIARMerger(llm=llm_client)
        logger.info("RIAR Pipeline initialized.")

    def run(
        self,
        query: str,
        session_history: List[Turn],
        language: str = "en",
        ab_condition: str = "riar"
    ) -> RIARResult:
        """
        Run the full RIAR pipeline on an initial query.
        ab_condition: "riar" (full pipeline) or "baseline" (bypass classification, route immediately).
        """
        start = time.time()
        logger.info(f"RIAR pipeline started | query='{query}' | language={language} | condition={ab_condition}")

        if ab_condition == "baseline":
            # BASELINE CONDITION: Bypass probe and classification, route directly via Coordinator downstream
            elapsed_ms = int((time.time() - start) * 1000)
            return RIARResult(
                ambiguity_detected=False,
                ambiguity_score=0.0,
                ambiguity_type="CLEAR",
                clarification_question=None,
                refined_query=query,
                probe_chunks=[]
            )

        # 1. Probe Retrieval
        probe_chunks, domain_scores = self.probe.retrieve(query)

        # 2 & 3. Ambiguity Detection & Classification
        classification = self.classifier.classify(query, domain_scores)

        # 4. Clarification Generation
        clarification_question = None
        if classification.requires_clarification:
            clarification_question = self.clarifier.generate_question(query, classification, probe_chunks)

        elapsed_ms = int((time.time() - start) * 1000)
        if elapsed_ms > self.MAX_LATENCY_MS:
            logger.warning(f"RIAR latency exceeded limit: {elapsed_ms}ms > {self.MAX_LATENCY_MS}ms")

        result = RIARResult(
            ambiguity_detected=classification.requires_clarification,
            ambiguity_score=classification.ambiguity_score,
            ambiguity_type=classification.ambiguity_type,
            clarification_question=clarification_question,
            refined_query=query,
            probe_chunks=probe_chunks
        )

        logger.info(f"RIAR complete in {elapsed_ms}ms | type={classification.ambiguity_type}")
        return result

    def refine(
        self,
        original_query: str,
        clarification_response: str,
        ambiguity_type: str
    ) -> RefinedQuery:
        """
        Refine the original query using the user's clarification response.
        """
        logger.info(f"Refining query | original='{original_query}' | response='{clarification_response}'")

        # In a real session, we'd pass the actual clarification question we asked.
        # Since we don't pass it into `refine()` explicitly, we provide a placeholder context.
        resolved_query = self.merger.merge(
            original_query=original_query,
            clarification_question="Can you clarify your intent?",
            user_response=clarification_response
        )

        return RefinedQuery(
            refined_query=resolved_query,
            ready_for_rag=True
        )
