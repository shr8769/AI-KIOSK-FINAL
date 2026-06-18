import os
import sys
import json
import csv

# Reconfigure stdout/stderr to UTF-8 to handle Kannada, Hindi, and other Unicode characters on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add the project root directory to sys.path so we can import agents
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(project_root)

from agents.coordinator.coordinator_agent import CoordinatorAgent

def run_benchmark():
    # Resolve paths
    datasets_dir = os.path.join(project_root, "evaluation", "datasets")
    results_dir = os.path.join(project_root, "evaluation", "results")
    
    seed_queries_path = os.path.join(datasets_dir, "seed_queries.json")
    results_csv_path = os.path.join(results_dir, "benchmark_results.csv")
    
    # Ensure results directory exists
    os.makedirs(results_dir, exist_ok=True)
    
    if not os.path.exists(seed_queries_path):
        print(f"Error: {seed_queries_path} not found.")
        sys.exit(1)
        
    # Load queries
    with open(seed_queries_path, "r", encoding="utf-8") as f:
        queries_data = json.load(f)
        
    print(f"Loaded {len(queries_data)} queries from {seed_queries_path}.")
    
    # Initialize coordinator
    coordinator = CoordinatorAgent()
    
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
    
    for idx, item in enumerate(queries_data, 1):
        query = item.get("query", "")
        expected = item.get("domain", "")
        if not query:
            continue
            
        print(f"\n[{idx}/{len(queries_data)}] Running query: '{query}'")
        
        import time
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
        
        results.append({
            "Query": query,
            "Selected Agent": selected_agent,
            "Latency (s)": f"{latency:.4f}",
            "Answer": answer
        })
        
        predicted = agent_to_domain.get(selected_agent, "None")
        json_results.append({
            "query": query,
            "expected_domain": expected,
            "predicted_domain": predicted,
            "selected_agent": selected_agent,
            "is_correct": predicted == expected,
            "latency": latency,
            "answer": answer
        })
        
    # Save as CSV
    with open(results_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Query", "Selected Agent", "Latency (s)", "Answer"])
        writer.writeheader()
        writer.writerows(results)
        
    # Save as JSON (week3_baseline.json)
    baseline_json_path = os.path.join(results_dir, "week3_baseline.json")
    with open(baseline_json_path, "w", encoding="utf-8") as f:
        json.dump(json_results, f, indent=4, ensure_ascii=False)
        
    print(f"\nBenchmark completed successfully! Results saved to {results_csv_path} and {baseline_json_path}.")

if __name__ == "__main__":
    run_benchmark()
