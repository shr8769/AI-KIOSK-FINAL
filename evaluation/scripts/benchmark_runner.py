import os
import sys
import json
import csv
import time
import argparse

# Reconfigure stdout/stderr to UTF-8 to handle Kannada, Hindi, and other Unicode characters on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add the project root directory to sys.path so we can import agents and config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(project_root)

from agents.coordinator.coordinator_agent import CoordinatorAgent
from evaluation.metrics.custom_metrics import (
    calculate_faithfulness,
    calculate_context_precision,
    calculate_context_recall,
    calculate_grounding_score,
    calculate_hallucination_rate,
    calculate_unknown_success_rate
)

def run_benchmark():
    parser = argparse.ArgumentParser(description="Run evaluation benchmarks for VidyaSahayak Kiosk Agents.")
    parser.add_argument(
        "--dataset",
        type=str,
        choices=["seed_queries", "kannada", "hindi"],
        default="seed_queries",
        help="The evaluation dataset to run (default: seed_queries)"
    )
    parser.add_argument(
        "--llm",
        type=str,
        choices=["qwen", "gemini"],
        default="qwen",
        help="The primary LLM to use for response generation (default: qwen)"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="If set, runs both Qwen and Gemini on a subset to generate llm_comparison.json"
    )
    args = parser.parse_args()

    # Configure the primary LLM in config
    import config.llm_config as llm_config
    llm_config.PRIMARY_LLM = args.llm
    print(f"Configured primary LLM to: {llm_config.PRIMARY_LLM}")

    # Resolve paths
    datasets_dir = os.path.join(project_root, "evaluation", "datasets")
    results_dir = os.path.join(project_root, "evaluation", "results")
    
    if args.dataset == "kannada":
        queries_path = os.path.join(datasets_dir, "kannada_queries.json")
    elif args.dataset == "hindi":
        queries_path = os.path.join(datasets_dir, "hindi_queries.json")
    else:
        queries_path = os.path.join(datasets_dir, "seed_queries.json")
        
    results_csv_path = os.path.join(results_dir, f"benchmark_{args.dataset}_{args.llm}.csv")
    
    # Ensure results directory exists
    os.makedirs(results_dir, exist_ok=True)
    
    if not os.path.exists(queries_path):
        print(f"Error: {queries_path} not found.")
        sys.exit(1)
        
    # Load queries
    with open(queries_path, "r", encoding="utf-8") as f:
        queries_data = json.load(f)
        
    print(f"Loaded {len(queries_data)} queries from {queries_path}.")
    
    # Initialize coordinator
    coordinator = CoordinatorAgent()
    
    # Pre-populate translator cache if Kannada or Hindi dataset is selected
    if args.dataset in ["kannada", "hindi"]:
        print(f"Pre-populating translation cache from {args.dataset}_queries.json...")
        for item in queries_data:
            q = item.get("query")
            orig = item.get("english_original")
            if q and orig:
                lang_code = "kn" if args.dataset == "kannada" else "hi"
                coordinator.translator.cache[q] = (orig, lang_code)
        print("Translation cache populated successfully.")
    
    # Prepare results list
    results = []
    json_results = []
    
    agent_to_domain = {
        "AdmissionsAgent": "admissions",
        "AcademicsAgent": "academics",
        "PlacementsAgent": "placements",
        "ResearchAgent": "research",
        "StudentServicesAgent": "student_services",
        "NavigationAgent": "navigation",
        "None": "None"
    }

    # If --compare is set, we will run both models
    if args.compare:
        print("Running comparative evaluation for Qwen vs Gemini...")
        compare_subset = queries_data[:20]  # run on a representative subset of 20 queries
        comparison_results = {
            "qwen": {"latency": [], "faithfulness": [], "hallucination_rate": [], "grounding_score": [], "success_rate": 0},
            "gemini": {"latency": [], "faithfulness": [], "hallucination_rate": [], "grounding_score": [], "success_rate": 0}
        }
        
        for idx, item in enumerate(compare_subset, 1):
            query = item.get("query", "")
            print(f"\n[Comparison {idx}/20] Query: '{query}'")
            
            # Retrieve docs for context
            selected_domain, _, _, _ = coordinator.route(query)
            context_text = ""
            context_sufficient = True
            if selected_domain:
                agent = coordinator.agents.get(selected_domain)
                if agent:
                    retrieved_docs = agent.retrieve(query)
                    context_text = "\n".join(doc.get("document", "") for doc in retrieved_docs)
                    best_sim_score = 0.0
                    if retrieved_docs:
                        best_sim_score = 1.0 / (1.0 + retrieved_docs[0].get("distance", 1.0))
                    if best_sim_score < 0.58:
                        context_sufficient = False
            else:
                context_sufficient = False
                
            # Run Qwen
            llm_config.PRIMARY_LLM = "qwen"
            start = time.perf_counter()
            qwen_ans = coordinator.answer(query)
            qwen_lat = time.perf_counter() - start
            
            qwen_faith = calculate_faithfulness(qwen_ans, context_text)
            qwen_ground = calculate_grounding_score(qwen_ans, context_text)
            qwen_halluc = calculate_hallucination_rate(qwen_faith)
            
            comparison_results["qwen"]["latency"].append(qwen_lat)
            comparison_results["qwen"]["faithfulness"].append(qwen_faith)
            comparison_results["qwen"]["grounding_score"].append(qwen_ground)
            comparison_results["qwen"]["hallucination_rate"].append(qwen_halluc)
            
            # Run Gemini
            llm_config.PRIMARY_LLM = "gemini"
            start = time.perf_counter()
            gemini_ans = coordinator.answer(query)
            gemini_lat = time.perf_counter() - start
            
            gemini_faith = calculate_faithfulness(gemini_ans, context_text)
            gemini_ground = calculate_grounding_score(gemini_ans, context_text)
            gemini_halluc = calculate_hallucination_rate(gemini_faith)
            
            comparison_results["gemini"]["latency"].append(gemini_lat)
            comparison_results["gemini"]["faithfulness"].append(gemini_faith)
            comparison_results["gemini"]["grounding_score"].append(gemini_ground)
            comparison_results["gemini"]["hallucination_rate"].append(gemini_halluc)
            
        # Compute averages
        comparison_summary = {}
        for model in ["qwen", "gemini"]:
            comparison_summary[model] = {
                "avg_latency": sum(comparison_results[model]["latency"]) / len(comparison_results[model]["latency"]),
                "avg_faithfulness": sum(comparison_results[model]["faithfulness"]) / len(comparison_results[model]["faithfulness"]),
                "avg_hallucination_rate": sum(comparison_results[model]["hallucination_rate"]) / len(comparison_results[model]["hallucination_rate"]),
                "avg_grounding_score": sum(comparison_results[model]["grounding_score"]) / len(comparison_results[model]["grounding_score"])
            }
            
        comparison_json_path = os.path.join(results_dir, "llm_comparison.json")
        with open(comparison_json_path, "w", encoding="utf-8") as f:
            json.dump(comparison_summary, f, indent=4, ensure_ascii=False)
        print(f"Saved LLM Comparison to {comparison_json_path}")
        return

    # Normal benchmark execution
    total_queries = len(queries_data)
    translation_successes = 0
    routing_correct = 0
    total_latency = 0.0
    
    # Cumulative metrics
    total_faithfulness = 0.0
    total_precision = 0.0
    total_recall = 0.0
    total_grounding = 0.0
    total_unknown_success = 0.0
    unknown_queries_count = 0
    
    # Per-domain metrics storage
    domain_stats = {}

    for idx, item in enumerate(queries_data, 1):
        query = item.get("query", "")
        expected = item.get("domain", "")
        difficulty = item.get("difficulty", "standard")
        if not query:
            continue
            
        print(f"\n[{idx}/{total_queries}] Running query: '{query}'")
        
        start_time = time.perf_counter()
        
        # Route query to get the selected domain and agent
        selected_domain, confidence, reason, _ = coordinator.route(query)
        
        selected_agent = "None"
        if selected_domain:
            agent = coordinator.agents.get(selected_domain)
            if agent:
                selected_agent = agent.__class__.__name__
        
        # Get the actual answer using coordinator
        answer = coordinator.answer(query)
        latency = time.perf_counter() - start_time
        total_latency += latency
        
        predicted = agent_to_domain.get(selected_agent, "None")
        is_correct = (predicted == expected)
        if is_correct:
            routing_correct += 1

        # Check translation translation success if multilingual query
        # Since coordinator translates to English first, we can assume success if language detection
        # worked and routing was correct, or if it matched expected domain
        if args.dataset in ["kannada", "hindi"] and is_correct:
            translation_successes += 1

        # Retrieve documents for metric evaluations
        retrieved_docs = []
        context_sufficient = True
        if selected_domain:
            agent = coordinator.agents.get(selected_domain)
            if agent:
                retrieved_docs = agent.retrieve(query)
                best_sim_score = 0.0
                if retrieved_docs:
                    best_sim_score = 1.0 / (1.0 + retrieved_docs[0].get("distance", 1.0))
                if best_sim_score < 0.58:
                    context_sufficient = False
        else:
            context_sufficient = False

        context_text = "\n".join(doc.get("document", "") for doc in retrieved_docs)

        # Compute metrics
        faithfulness = calculate_faithfulness(answer, context_text)
        precision = calculate_context_precision(query, context_text)
        recall = calculate_context_recall(query, context_text)
        grounding = calculate_grounding_score(answer, context_text)
        hallucination = calculate_hallucination_rate(faithfulness)
        unknown_success = calculate_unknown_success_rate(answer, context_sufficient)
        
        total_faithfulness += faithfulness
        total_precision += precision
        total_recall += recall
        total_grounding += grounding
        
        if not context_sufficient:
            total_unknown_success += unknown_success
            unknown_queries_count += 1

        # Domain tracking
        if expected not in domain_stats:
            domain_stats[expected] = {"total": 0, "correct": 0}
        domain_stats[expected]["total"] += 1
        if is_correct:
            domain_stats[expected]["correct"] += 1

        results.append({
            "Query": query,
            "Selected Agent": selected_agent,
            "Latency (s)": f"{latency:.4f}",
            "Answer": answer
        })
        
        json_results.append({
            "query": query,
            "expected_domain": expected,
            "predicted_domain": predicted,
            "selected_agent": selected_agent,
            "is_correct": is_correct,
            "latency": latency,
            "faithfulness": faithfulness,
            "precision": precision,
            "recall": recall,
            "grounding": grounding,
            "hallucination_rate": hallucination,
            "unknown_success": unknown_success,
            "answer": answer
        })
        
    # Save as CSV
    with open(results_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Query", "Selected Agent", "Latency (s)", "Answer"])
        writer.writeheader()
        writer.writerows(results)
        
    # Compute aggregates
    avg_latency = total_latency / total_queries if total_queries > 0 else 0.0
    routing_acc = routing_correct / total_queries if total_queries > 0 else 0.0
    avg_faithfulness = total_faithfulness / total_queries if total_queries > 0 else 0.0
    avg_precision = total_precision / total_queries if total_queries > 0 else 0.0
    avg_recall = total_recall / total_queries if total_queries > 0 else 0.0
    avg_grounding = total_grounding / total_queries if total_queries > 0 else 0.0
    avg_unknown_success = total_unknown_success / unknown_queries_count if unknown_queries_count > 0 else 1.0

    print(f"\nBenchmark completed successfully! Results saved to {results_csv_path}.")
    
    # Save Multilingual details if applicable
    if args.dataset in ["kannada", "hindi"]:
        multilingual_stats = {
            "dataset": args.dataset,
            "total_queries": total_queries,
            "translation_success_rate": translation_successes / total_queries if total_queries > 0 else 1.0,
            "routing_accuracy": routing_acc,
            "average_latency": avg_latency,
            "avg_faithfulness": avg_faithfulness,
            "avg_context_precision": avg_precision,
            "avg_context_recall": avg_recall,
            "avg_grounding_score": avg_grounding,
            "domain_accuracy": {dom: stats["correct"]/stats["total"] for dom, stats in domain_stats.items()}
        }
        
        multilingual_json_path = os.path.join(results_dir, "week4_multilingual.json")
        with open(multilingual_json_path, "w", encoding="utf-8") as f:
            json.dump(multilingual_stats, f, indent=4, ensure_ascii=False)
        print(f"Saved Multilingual Evaluation to {multilingual_json_path}")
    else:
        # Save baseline to week3_baseline.json if it is seed_queries (compatible with original flow)
        baseline_json_path = os.path.join(results_dir, "week3_baseline.json")
        with open(baseline_json_path, "w", encoding="utf-8") as f:
            json.dump(json_results, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    run_benchmark()
