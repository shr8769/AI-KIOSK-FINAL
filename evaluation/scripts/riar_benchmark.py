"""
RIAR Benchmark & Evaluation Script (Week 5)
Owner: Haseeb

Runs the RIAR pipeline against seed_queries.json and fixtures.json.
Measures latency per stage and exports a CSV report for ambiguity threshold calibration.
"""

import os
import sys
import json
import time
import argparse
import logging
from typing import List, Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from riar.pipeline import RIARPipeline
from backend.app.models.shared_models import Turn

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def load_queries(dataset_path: str) -> List[Dict]:
    with open(dataset_path, "r") as f:
        data = json.load(f)
    # Handle list of dicts (seed_queries) or dict of lists (fixtures)
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        queries = []
        for key in ["clear_queries", "ambiguous_queries"]:
            for q in data.get(key, []):
                q["expected_type"] = key.split("_")[0].upper() # CLEAR or AMBIGUOUS
                queries.append(q)
        return queries
    return []

def run_benchmark(pipeline: RIARPipeline, queries: List[Dict], condition: str, delay_s: float):
    results = []
    
    logger.info(f"Starting {condition.upper()} benchmark for {len(queries)} queries...")
    for i, q_data in enumerate(queries):
        query_text = q_data.get("query", "")
        expected_domain = q_data.get("domain", "unknown")
        expected_type = q_data.get("expected_type", "unknown")
        
        start_time = time.time()
        
        # Run Pipeline
        result = pipeline.run(query=query_text, session_history=[], ab_condition=condition)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        row = {
            "query_id": i + 1,
            "query": query_text,
            "condition": condition,
            "latency_ms": latency_ms,
            "expected_domain": expected_domain,
            "expected_type": expected_type,
            "predicted_domain": result.domain,
            "ambiguity_detected": result.ambiguity_detected,
            "ambiguity_score": result.ambiguity_score,
            "ambiguity_type": result.ambiguity_type,
            "clarification_question": result.clarification_question
        }
        results.append(row)
        
        # Respect rate limits
        if delay_s > 0:
            time.sleep(delay_s)
            
    return results

def save_report(results: List[Dict], output_path: str):
    import csv
    if not results:
        return
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    keys = results[0].keys()
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
    
    logger.info(f"Report saved to {output_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use mocked LLM to save API costs")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to sleep between queries (rate limit)")
    args = parser.parse_args()

    # 1. Initialize LLM
    if args.mock:
        logger.info("Using MOCK LLM")
        from unittest.mock import MagicMock
        llm = MagicMock()
    else:
        logger.info("Using ChatGoogleGenerativeAI (gemini-1.5-flash)")
        from langchain_google_genai import ChatGoogleGenerativeAI
        if "GOOGLE_API_KEY" not in os.environ:
            logger.error("GOOGLE_API_KEY environment variable is required.")
            sys.exit(1)
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

    # 2. Initialize Mocks for Vector DB and Embeddings
    from unittest.mock import MagicMock
    chroma_mock = MagicMock()
    mock_collection = MagicMock()
    # Mock ChromaDB returning high confidence chunks
    mock_collection.query.return_value = {
        "documents": [["Mock chunk"]],
        "metadatas": [[{"domain": "admissions", "chunk_id": "m1"}]],
        "distances": [[0.1]]
    }
    chroma_mock.get_collection.return_value = mock_collection
    
    embedding_mock = MagicMock()
    # Need to return an object that has a .tolist() or is a list
    embedding_mock.encode.return_value = [[0.1] * 384]
    
    # 3. Create Pipeline
    pipeline = RIARPipeline(vector_store=chroma_mock, llm_client=llm, embedding_model=embedding_mock)
    
    if args.mock:
        from riar.schemas.schemas import RIARClassification, RIARRouting
        pipeline.classifier.classify = MagicMock(return_value=RIARClassification(
            ambiguity_score=0.1, ambiguity_type="CLEAR", confidence=0.9, requires_clarification=False, reasoning="Mock"
        ))
        pipeline.router.route = MagicMock(return_value=RIARRouting(
            domain="admissions", confidence=0.9
        ))

    # 4. Load Datasets
    seed_path = os.path.join(os.path.dirname(__file__), "../datasets/seed_queries.json")
    fixtures_path = os.path.join(os.path.dirname(__file__), "../../riar/tests/fixtures.json")
    
    seed_queries = load_queries(seed_path)
    fixture_queries = load_queries(fixtures_path)
    
    if not seed_queries:
        logger.warning(f"Seed queries not found at {seed_path}. Make sure Gowtham's dataset is checked out.")
        
    all_queries = fixture_queries + seed_queries[:50] # Limit to 50 for time sake unless full run
    
    # 5. Run RIAR Condition
    riar_results = run_benchmark(pipeline, all_queries, condition="riar", delay_s=args.delay)
    
    # 6. Run Baseline Condition
    baseline_results = run_benchmark(pipeline, all_queries, condition="baseline", delay_s=args.delay)
    
    # 7. Export
    all_results = riar_results + baseline_results
    out_file = os.path.join(os.path.dirname(__file__), "../results/riar_benchmark_report.csv")
    save_report(all_results, out_file)
    
    # Compute basic calibration metric
    ambiguous_scores = [r["ambiguity_score"] for r in riar_results if r["expected_type"] == "AMBIGUOUS"]
    clear_scores = [r["ambiguity_score"] for r in riar_results if r["expected_type"] == "CLEAR"]
    
    if ambiguous_scores and clear_scores:
        avg_amb = sum(ambiguous_scores)/len(ambiguous_scores)
        avg_clr = sum(clear_scores)/len(clear_scores)
        logger.info(f"Calibration -> Avg Ambiguous Score: {avg_amb:.2f} | Avg Clear Score: {avg_clr:.2f}")
        logger.info(f"Suggested Threshold: {(avg_amb + avg_clr)/2:.2f}")

if __name__ == "__main__":
    main()
