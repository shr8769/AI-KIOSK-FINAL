import os
import sys
import json
import csv

# Reconfigure stdout/stderr to UTF-8 to handle Kannada, Hindi, and other Unicode characters on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(project_root)

from agents.coordinator.coordinator_agent import CoordinatorAgent

def analyze_failures():
    datasets_dir = os.path.join(project_root, "evaluation", "datasets")
    results_dir = os.path.join(project_root, "evaluation", "results")
    
    seed_queries_path = os.path.join(datasets_dir, "seed_queries.json")
    results_csv_path = os.path.join(results_dir, "benchmark_results.csv")
    failure_report_path = os.path.join(results_dir, "failure_analysis.txt")
    
    if not os.path.exists(seed_queries_path):
        print(f"Error: {seed_queries_path} not found.")
        sys.exit(1)
        
    if not os.path.exists(results_csv_path):
        print(f"Error: {results_csv_path} not found.")
        sys.exit(1)
        
    # Load expected domains
    with open(seed_queries_path, "r", encoding="utf-8") as f:
        seed_data = json.load(f)
        
    ground_truth = {}
    for item in seed_data:
        q = item.get("query", "").strip()
        d = item.get("domain", "").strip()
        if q:
            ground_truth[q] = d
            
    # Load results
    results = []
    with open(results_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)
            
    # Mapping agent to domain
    agent_to_domain = {
        "AdmissionsAgent": "admissions",
        "AcademicsAgent": "academics",
        "PlacementsAgent": "placements",
        "ResearchAgent": "research",
        "StudentServicesAgent": "student_services",
        "NavigationAgent": "navigation",
        "None": "None"
    }
    
    # Initialize coordinator to check matches
    coordinator = CoordinatorAgent()
    
    # Initialize metrics variables
    domains = ["admissions", "academics", "placements", "research", "student_services", "navigation", "None"]
    tp = {d: 0 for d in domains}
    fp = {d: 0 for d in domains}
    fn = {d: 0 for d in domains}
    
    failures = []
    failures_by_domain = {}
    failure_reasons = {}
    
    for row in results:
        query = row.get("Query", "").strip()
        selected_agent = row.get("Selected Agent", "").strip()
        
        predicted = agent_to_domain.get(selected_agent, "unknown")
        gt = ground_truth.get(query, None)
        
        # Fuzzy match query if needed
        if gt is None:
            for q_gt, d_gt in ground_truth.items():
                if query.lower() == q_gt.lower():
                    gt = d_gt
                    break
        if gt is None:
            gt = "None"
            
        if predicted == gt:
            if gt in tp:
                tp[gt] += 1
        else:
            if predicted in fp:
                fp[predicted] += 1
            if gt in fn:
                fn[gt] += 1
                
            # Failure detected!
            # Analyze keywords matched
            _, confidence, reason, all_matches = coordinator.route(query)
            
            # Formulate failure reason category
            if not all_matches:
                fail_reason = "No keywords matched (Defaulted to None)"
            else:
                fail_reason = f"Keyword conflict / misrouting (Matched: {', '.join(all_matches)})"
                
            failure_item = {
                "query": query,
                "expected": gt,
                "predicted": predicted,
                "matched_keywords": all_matches,
                "reason": fail_reason
            }
            
            failures.append(failure_item)
            
            # Group by domain (expected)
            failures_by_domain[gt] = failures_by_domain.get(gt, 0) + 1
            
            # Count failure reasons
            failure_reasons[fail_reason] = failure_reasons.get(fail_reason, 0) + 1
            
    total_queries = len(results)
    correct_queries = total_queries - len(failures)
    accuracy = correct_queries / total_queries if total_queries > 0 else 0
    
    # Calculate latency statistics
    latencies = []
    for row in results:
        lat = row.get("Latency (s)")
        if lat:
            latencies.append(float(lat))
            
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    min_lat = min(latencies) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0
            
    # Generate failure analysis text report
    report = []
    report.append("============================================================")
    report.append("                   ROUTING FAILURE ANALYSIS")
    report.append("============================================================")
    report.append(f"Total Queries  : {total_queries}")
    report.append(f"Total Correct  : {correct_queries}")
    report.append(f"Total Failures : {len(failures)}")
    report.append(f"Routing Accuracy: {accuracy * 100:.2f}%")
    report.append(f"Average Latency: {avg_lat:.4f}s")
    report.append("")
    
    report.append("PER-DOMAIN METRICS:")
    report.append("-" * 65)
    report.append(f"{'Domain':<20} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10}")
    report.append("-" * 65)
    for d in domains[:-1]:
        p_val = tp[d] / (tp[d] + fp[d]) if (tp[d] + fp[d]) > 0 else 0.0
        r_val = tp[d] / (tp[d] + fn[d]) if (tp[d] + fn[d]) > 0 else 0.0
        f1_val = 2 * p_val * r_val / (p_val + r_val) if (p_val + r_val) > 0 else 0.0
        report.append(f"{d:<20} | {p_val * 100:>8.2f}% | {r_val * 100:>8.2f}% | {f1_val * 100:>8.2f}%")
    report.append("-" * 65)
    report.append("")
    
    # 2. Group failures by domain
    report.append("FAILURES BY DOMAIN:")
    report.append("-" * 30)
    for dom, count in sorted(failures_by_domain.items(), key=lambda x: x[1], reverse=True):
        report.append(f"  * {dom}: {count} failure(s)")
    report.append("")
    
    # 4. Print top failure reasons
    report.append("TOP FAILURE REASONS:")
    report.append("-" * 30)
    for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True):
        report.append(f"  * {reason}: {count} time(s)")
    report.append("")
    
    # 1. Show all incorrect routes
    report.append("ALL INCORRECT ROUTES:")
    report.append("=" * 60)
    for idx, item in enumerate(failures, 1):
        report.append(f"{idx}. Query: '{item['query']}'")
        report.append(f"   Expected Domain: {item['expected']}")
        report.append(f"   Predicted Domain: {item['predicted']}")
        report.append(f"   Failure Analysis: {item['reason']}")
        report.append("-" * 60)
        
    report_text = "\n".join(report)
    
    # Print the report
    print(report_text)
    
    # Generate Markdown report (week3_report.md)
    md_report = []
    md_report.append("# Sprint 3 Evaluation Pass Report")
    md_report.append("")
    md_report.append("This report summarizes the performance metrics of the **Campus AI Brain** coordinator routing and retrieval pipeline with integrated Gemini RAG synthesis and language fallback translation.")
    md_report.append("")
    md_report.append("## Executive Summary")
    md_report.append("")
    md_report.append("| Metric | Value |")
    md_report.append("| :--- | :--- |")
    md_report.append(f"| **Total Queries Evaluated** | {total_queries} |")
    md_report.append(f"| **Successful Routes** | {correct_queries} |")
    md_report.append(f"| **Routing Failures** | {len(failures)} |")
    md_report.append(f"| **Routing Accuracy** | **{accuracy * 100:.2f}%** |")
    md_report.append(f"| **Average Query Latency** | {avg_lat:.4f} seconds |")
    md_report.append(f"| **Min / Max Latency** | {min_lat:.4f}s / {max_lat:.4f}s |")
    md_report.append("")
    md_report.append("## Per-Domain Routing Accuracy")
    md_report.append("")
    md_report.append("| Domain | Precision | Recall | F1-Score |")
    md_report.append("| :--- | :---: | :---: | :---: |")
    
    for d in domains[:-1]:
        p_val = tp[d] / (tp[d] + fp[d]) if (tp[d] + fp[d]) > 0 else 0.0
        r_val = tp[d] / (tp[d] + fn[d]) if (tp[d] + fn[d]) > 0 else 0.0
        f1_val = 2 * p_val * r_val / (p_val + r_val) if (p_val + r_val) > 0 else 0.0
        md_report.append(f"| **{d}** | {p_val * 100:.2f}% | {r_val * 100:.2f}% | {f1_val * 100:.2f}% |")
        
    md_report.append("")
    md_report.append("## Failure Analysis Breakdown")
    md_report.append("")
    md_report.append("### Failures by Domain")
    if failures_by_domain:
        for dom, count in sorted(failures_by_domain.items(), key=lambda x: x[1], reverse=True):
            md_report.append(f"- **{dom}**: {count} failure(s)")
    else:
        md_report.append("- No domain failures.")
    md_report.append("")
    
    md_report.append("### Top Failure Reasons")
    if failure_reasons:
        for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True):
            md_report.append(f"- **{reason}**: {count} time(s)")
    else:
        md_report.append("- No failure reasons identified.")
    md_report.append("")
    
    # Save to files
    os.makedirs(results_dir, exist_ok=True)
    with open(failure_report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
        
    week3_report_path = os.path.join(results_dir, "week3_report.md")
    with open(week3_report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_report))
        
    print(f"\nFailure analysis report saved to: {failure_report_path}")
    print(f"Sprint 3 Baseline Report saved to: {week3_report_path}")

if __name__ == "__main__":
    analyze_failures()
