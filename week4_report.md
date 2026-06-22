# Sprint 4 Evaluation Report

This report summarizes the performance metrics of the **Campus AI Brain** coordinator routing and retrieval pipeline with Qwen3-8B local LLM, citation formatting, multilingual datasets, and custom evaluation metrics.

## Codebase Changes Summary

### Modified Files
- [prompt_templates.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/agents/concierge/prompt_templates.py)
- [base_agent.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/agents/domain/base_agent.py)
- [coordinator_agent.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/agents/coordinator/coordinator_agent.py)
- [benchmark_runner.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/scripts/benchmark_runner.py)
- [analyze_failures.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/scripts/analyze_failures.py)

### Created Files
- [qwen_client.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/agents/llm/qwen_client.py)
- [llm_config.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/config/llm_config.py)
- [kannada_queries.json](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/datasets/kannada_queries.json)
- [hindi_queries.json](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/datasets/hindi_queries.json)
- [custom_metrics.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/metrics/custom_metrics.py)
- [week4_multilingual.json](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/results/week4_multilingual.json)
- [llm_comparison.json](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/results/llm_comparison.json)
- [week4_report.md](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/week4_report.md)

### Deleted Files
- None

## Multilingual Dataset Verification

- **Kannada Query Count**: 100 queries
- **Hindi Query Count**: 100 queries

## Core RAG Synthesis Metrics

| Metric | Value |
| :--- | :--- |
| **Total Queries Evaluated** | 300 |
| **Routing Accuracy** | **86.67%** |
| **Average Query Latency** | 0.3425 seconds |
| **Faithfulness Score** | 0.9970 |
| **Context Precision** | 0.7328 |
| **Context Recall** | 0.7488 |
| **Grounding Score** | 0.9970 |
| **Hallucination Rate** | 0.0030 |

## Multilingual Performance

- **Dataset Evaluated**: hindi
- **Translation Success Rate**: 32.00%
- **Routing Accuracy**: 32.00%
- **Average Latency**: 3.1994s
- **Faithfulness**: 0.3455
- **Context Precision**: 0.2615
- **Context Recall**: 0.2662

### Domain Accuracy Breakdown
| Domain | Accuracy |
| :--- | :--- |
| **admissions** | 5.88% |
| **academics** | 11.76% |
| **placements** | 0.00% |
| **research** | 47.06% |
| **student_services** | 31.25% |
| **navigation** | 100.00% |

## Qwen3-8B vs Gemini Comparison

| Metric | Qwen3-8B (Ollama) | Gemini-2.5-flash |
| :--- | :---: | :---: |
| **Average Latency** | 21.8105s | 3.3103s |
| **Faithfulness Score** | 0.9927 | 0.9927 |
| **Grounding Score** | 0.9927 | 0.9927 |
| **Hallucination Rate** | 0.0073 | 0.0073 |

## Sample Responses with Citations

### Successful Query (Admissions)
```
Query: Can I apply using predicted grades?
Answer:
Yes, you can apply using predicted high school grades if final transcripts are delayed.

Sources:
    admissions.json
```

### Unknown Question Query
```
Query: What is the VC's home phone number?
Answer:
Sorry, I could not find information regarding this in the university knowledge base. Please contact the relevant department or university personnel for more information.

Sources:
    None
```

## Failure Analysis Breakdown

### Top Failure Reasons
- **No keywords matched (Defaulted to None)**: 26 time(s)
- **Keyword conflict / misrouting (Matched: apply, exam)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: credits, course, research)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: journals, research, books, off-campus, e-books)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: cgpa)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: grades)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: apply, visa, where)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: apply, placements)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: deadline, application, urop)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: credits, course, research, stipend)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: backlog)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: deadline, course)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: paper, professor)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: course, research)**: 1 time(s)
- **Keyword conflict / misrouting (Matched: fee, library)**: 1 time(s)

### Incorrect Routes
1. Query: 'How do I apply for a makeup exam if I missed a final exam due to a medical emergency?'
   - Expected Domain: academics
   - Predicted Domain: admissions
   - Failure Analysis: Keyword conflict / misrouting (Matched: apply, exam)

2. Query: 'Can I earn academic course credits for participating in research during the semester?'
   - Expected Domain: research
   - Predicted Domain: academics
   - Failure Analysis: Keyword conflict / misrouting (Matched: credits, course, research)

3. Query: 'How can I access online research journals, databases, and e-books from off-campus?'
   - Expected Domain: student_services
   - Predicted Domain: research
   - Failure Analysis: Keyword conflict / misrouting (Matched: journals, research, books, off-campus, e-books)

4. Query: 'Hey, what CGPA do I need to get in for the CS undergrad program?'
   - Expected Domain: admissions
   - Predicted Domain: academics
   - Failure Analysis: Keyword conflict / misrouting (Matched: cgpa)

5. Query: 'Am I automatically considered for a scholarship if my grades are high, or is there a separate form?'
   - Expected Domain: admissions
   - Predicted Domain: academics
   - Failure Analysis: Keyword conflict / misrouting (Matched: grades)

6. Query: 'I need an official transcript for my visa. Where do I apply for one?'
   - Expected Domain: academics
   - Predicted Domain: admissions
   - Failure Analysis: Keyword conflict / misrouting (Matched: apply, visa, where)

7. Query: 'Can I apply for placements if I am a PG student?'
   - Expected Domain: placements
   - Predicted Domain: admissions
   - Failure Analysis: Keyword conflict / misrouting (Matched: apply, placements)

8. Query: 'What is UROP and what is the deadline to submit the application?'
   - Expected Domain: research
   - Predicted Domain: admissions
   - Failure Analysis: Keyword conflict / misrouting (Matched: deadline, application, urop)

9. Query: 'Can I get course credits instead of a stipend for participating in research?'
   - Expected Domain: research
   - Predicted Domain: academics
   - Failure Analysis: Keyword conflict / misrouting (Matched: credits, course, research, stipend)

10. Query: 'Do I need to submit hard copies of my documents after online upload?'
   - Expected Domain: admissions
   - Predicted Domain: None
   - Failure Analysis: No keywords matched (Defaulted to None)
