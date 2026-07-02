"""
Probe Retriever — RIAR Step 1
Owner: Haseeb

Executes a fast, broad retrieval across all domain collections in ChromaDB
to gather initial context and domain signals for ambiguity detection.
No LLM is used in this step.
"""

import logging
from typing import List, Dict, Any, Tuple
from collections import defaultdict

# Importing the shared model for returned chunks
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.models.shared_models import ProbeChunk

logger = logging.getLogger(__name__)

# Collections defined in CHROMADB_CONTRACT.md
COLLECTIONS = [
    "admissions_collection",
    "academics_collection",
    "placements_collection",
    "research_collection",
    "navigation_collection",
    "student_services_collection",
]

# Thresholds defined in CHROMADB_CONTRACT.md
CONFIDENCE_HIGH = 0.68
CONFIDENCE_MEDIUM = 0.45


class ProbeRetriever:
    def __init__(self, chroma_client: Any, embedding_model: Any = None):
        """
        Args:
            chroma_client: A chromadb.Client instance.
            embedding_model: A sentence-transformers model. If None, it initializes 'all-MiniLM-L6-v2'.
        """
        self.chroma_client = chroma_client

        if embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading default probe embedding model: all-MiniLM-L6-v2")
                self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            except ImportError:
                logger.warning(
                    "sentence-transformers not installed. Probe retrieval will fail if embeddings aren't pre-computed."
                )
                self.embedding_model = None
        else:
            self.embedding_model = embedding_model

    def retrieve(
        self, query: str, top_k_per_collection: int = 3, max_total_chunks: int = 10
    ) -> Tuple[List[ProbeChunk], Dict[str, float]]:
        """
        Probes all collections to gather domain signals and context chunks.

        Args:
            query: The raw user query.
            top_k_per_collection: Max chunks to fetch from EACH collection before global ranking.
            max_total_chunks: Max chunks to return globally to the RIAR pipeline.

        Returns:
            Tuple containing:
            1. List of ProbeChunk objects sorted by confidence (descending).
            2. Dict of aggregated domain scores (domain -> score).
        """
        if not self.embedding_model:
            raise RuntimeError("Embedding model is not initialized.")

        # 1. Embed the query
        encoded = self.embedding_model.encode([query])[0]
        query_embedding = encoded.tolist() if hasattr(encoded, "tolist") else encoded

        all_chunks: List[ProbeChunk] = []
        domain_scores: Dict[str, float] = defaultdict(float)

        # 2. Query each collection
        for collection_name in COLLECTIONS:
            try:
                collection = self.chroma_client.get_collection(name=collection_name)
            except Exception as e:
                logger.debug(f"Collection {collection_name} not found or error: {e}")
                continue

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k_per_collection,
                include=["documents", "metadatas", "distances"],
            )

            # 3. Process results per collection
            if results and results["documents"] and results["documents"][0]:
                for i in range(len(results["documents"][0])):
                    doc = results["documents"][0][i]
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i]

                    # Contract: confidence = 1 - distance (for cosine)
                    confidence = 1.0 - distance

                    # Ignore LOW confidence chunks entirely
                    if confidence < CONFIDENCE_MEDIUM:
                        continue

                    domain = meta.get(
                        "domain", collection_name.replace("_collection", "")
                    )
                    chunk_id = meta.get("chunk_id", f"{collection_name}_{i}")

                    chunk = ProbeChunk(
                        chunk_id=chunk_id,
                        text=doc,
                        score=confidence,
                        source=meta.get("source_file"),
                    )
                    all_chunks.append(chunk)

                    # Accumulate domain signal
                    domain_scores[domain] += confidence

        # 4. Global ranking
        # Sort all chunks by score descending and take the top N
        all_chunks.sort(key=lambda x: x.score, reverse=True)
        top_chunks = all_chunks[:max_total_chunks]

        # Normalize domain scores for logging/classification
        total_score = sum(domain_scores.values())
        if total_score > 0:
            domain_scores = {
                k: round(v / total_score, 3) for k, v in domain_scores.items()
            }

        return top_chunks, dict(domain_scores)
