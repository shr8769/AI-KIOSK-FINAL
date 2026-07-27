import os
import sys
import json
import time

# Reconfigure stdout/stderr to UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(project_root)

from agents.coordinator.coordinator_agent import CoordinatorAgent  # noqa: E402

def run_navigation_test():
    print("Initializing CoordinatorAgent...")
    coordinator = CoordinatorAgent()
    
    test_cases = [
        {"query": "Where is the MRD Auditorium?", "expected_landmark": "MRD Auditorium"},
        {"query": "How do I get to the Library?", "expected_landmark": "Library"},
        {"query": "Where is the Hostel Office located?", "expected_landmark": "Hostel Office"},
        {"query": "Can you give me directions to the Main Gate?", "expected_landmark": "Main Gate"},
        {"query": "Where is the Food Court?", "expected_landmark": "Food Court"},
        {"query": "How to reach the Admissions Office?", "expected_landmark": "Admissions Office"},
        {"query": "Where is the Placement Cell in the admin block?", "expected_landmark": "Placement Cell"},
        {"query": "How do I walk to the Research Block?", "expected_landmark": "Research Block"},
        {"query": "Where is the Academic Block located?", "expected_landmark": "Academic Block"},
        {"query": "Directions to the Medical Center", "expected_landmark": "Medical Center"}
    ]
    
    results = []
    success_count = 0
    
    print("\nStarting Navigation Agent Verification...")
    print("=" * 60)
    
    for idx, case in enumerate(test_cases, 1):
        query = case["query"]
        expected_landmark = case["expected_landmark"]
        
        print(f"\n[{idx}/10] Query: '{query}'")
        
        start_time = time.perf_counter()
        
        # Route query
        domain, confidence, reason, matches = coordinator.route(query)
        
        # Get answer
        full_answer = coordinator.answer(query)
        latency = time.perf_counter() - start_time
        
        # Parse answer and source
        answer_text = ""
        source = "None"
        if "\n\nSources:\n    " in full_answer:
            answer_text, source = full_answer.split("\n\nSources:\n    ", 1)
            source = source.strip()
            if answer_text.startswith("Answer:\n"):
                answer_text = answer_text[len("Answer:\n"):].strip()
        else:
            answer_text = full_answer.strip()
            
        is_routed_correctly = (domain == "navigation")
        has_correct_citation = (source == "locations.json")
        is_successful = is_routed_correctly and has_correct_citation
        
        if is_successful:
            success_count += 1
            
        print(f"   Routed Domain: {domain} (Confidence: {confidence:.2f})")
        print(f"   Citation:      {source}")
        print(f"   Latency:       {latency:.4f}s")
        print(f"   Status:        {'SUCCESS' if is_successful else 'FAILED'}")
        print(f"   Answer snippet: {answer_text[:120]}...")
        
        results.append({
            "query": query,
            "expected_landmark": expected_landmark,
            "predicted_domain": domain,
            "routing_confidence": confidence,
            "routing_reason": reason,
            "latency": latency,
            "citation": source,
            "answer": answer_text,
            "routed_correctly": is_routed_correctly,
            "correct_citation": has_correct_citation,
            "success": is_successful
        })
        
    print("\n" + "=" * 60)
    print(f"Navigation Verification Summary: {success_count}/10 Successful")
    print("=" * 60)
    
    results_dir = os.path.join(project_root, "evaluation", "results")
    os.makedirs(results_dir, exist_ok=True)
    results_path = os.path.join(results_dir, "navigation_validation.json")
    
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_tested": len(test_cases),
            "total_successful": success_count,
            "success_rate": success_count / len(test_cases),
            "runs": results
        }, f, indent=4, ensure_ascii=False)
        
    print(f"Results saved to: {results_path}")

if __name__ == "__main__":
    run_navigation_test()
