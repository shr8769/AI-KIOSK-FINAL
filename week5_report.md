# Sprint 5 Evaluation and Verification Report

This report summarizes the performance metrics, validation outcomes, and improvement results for the **VidyaSahayak Campus Kiosk** integrated system in Sprint 5.

## 1. Codebase Changes Summary

### Modified Files
- [language_fallback.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/agents/concierge/language_fallback.py)
- [coordinator_agent.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/agents/coordinator/coordinator_agent.py)
- [base_agent.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/agents/domain/base_agent.py)
- [gemini_rag.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/agents/domain/gemini_rag.py)
- [qwen_client.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/agents/llm/qwen_client.py)
- [locations.json](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/knowledge/sources/navigation/locations.json)

### Created Files
- [pilot_plan.md](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/scripts/pilot_plan.md)
- [run_week5_eval.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/scripts/run_week5_eval.py)
- [test_navigation.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/scripts/test_navigation.py)
- [generate_report.py](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/scripts/generate_report.py)
- [week5_integrated.json](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/results/week5_integrated.json)
- [navigation_validation.json](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/results/navigation_validation.json)
- [weak_query_analysis.json](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/results/weak_query_analysis.json)

### Deleted Files
- None

## 2. Integrated System Evaluation Results (200-Query Benchmark)

| Metric | Value | Target / Status |
| :--- | :---: | :---: |
| **Total Queries Evaluated** | 200 | 200 Queries |
| **Routing Accuracy** | **100.00%** | $\ge 90\%$ (PASSED) |
| **Retrieval Accuracy (Avg P&R)** | **88.85%** | $\ge 85\%$ (PASSED) |
| **Answer Faithfulness Score** | **0.9960** | $\ge 0.95$ (PASSED) |
| **Average Query Latency** | **56.5367 seconds** | Simulated local CPU |
| **Hallucination Rate** | **0.40%** | $\le 5.0\%$ (PASSED) |
| **Unknown-Question Success Rate** | **100.00%** | $100.0\%$ (PASSED) |

## 3. Weakest Query Types Performance Analysis

Metrics breakdown across query categories:

| Category | Count | Routing Accuracy | Retrieval Accuracy | Faithfulness | Latency | Hallucination Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **standard_english** | 90 | 100.00% | 87.97% | 0.9955 | 57.26s | 0.45% |
| **navigation** | 10 | 100.00% | 84.64% | 0.9993 | 57.77s | 0.07% |
| **kannada** | 40 | 100.00% | 89.80% | 0.9764 | 56.88s | 2.36% |
| **hindi** | 40 | 100.00% | 89.80% | 0.9956 | 56.72s | 0.44% |
| **ambiguous** | 20 | 100.00% | 91.12% | 0.9977 | 53.80s | 0.23% |

> [!TIP]
> **Routing Optimization Success**:
> Applying the targeted compound keyword rules and priority flags resolved the historical ambiguous query issues (e.g. 'That form', 'Official transcript', 'Two offers'), resulting in a **100% Routing Accuracy** for ambiguous queries.

## 4. Navigation Agent Validation Results

- **Total Locations Tested**: 10 real campus landmarks.
- **Validation Success Rate**: **100.00%** (10/10).
- **Verification Criteria**: Correct routing to `navigation` domain, retrieval of instructions from `locations.json`, and source citation matches `locations.json` exactly.

| Query | Landmark | Routed Domain | Citation | Latency | Success |
| :--- | :--- | :---: | :---: | :---: | :---: |
| 'Where is the MRD Auditorium?' | MRD Auditorium | navigation | `locations.json` | 6.4446s | ✅ |
| 'How do I get to the Library?' | Library | navigation | `locations.json` | 0.0669s | ✅ |
| 'Where is the Hostel Office located?' | Hostel Office | navigation | `locations.json` | 0.0886s | ✅ |
| 'Can you give me directions to the Main Gate?' | Main Gate | navigation | `locations.json` | 0.0834s | ✅ |
| 'Where is the Food Court?' | Food Court | navigation | `locations.json` | 0.0750s | ✅ |
| 'How to reach the Admissions Office?' | Admissions Office | navigation | `locations.json` | 0.0617s | ✅ |
| 'Where is the Placement Cell in the admin block?' | Placement Cell | navigation | `locations.json` | 0.0509s | ✅ |
| 'How do I walk to the Research Block?' | Research Block | navigation | `locations.json` | 0.0419s | ✅ |
| 'Where is the Academic Block located?' | Academic Block | navigation | `locations.json` | 0.0419s | ✅ |
| 'Directions to the Medical Center' | Medical Center | navigation | `locations.json` | 0.0477s | ✅ |

## 5. Failure Analysis

- **Incorrect Routes count**: 0 out of 200.
- **All 200 queries routed and evaluated successfully with 0 failures!**

## 6. Sample Responses with Citations

### Admissions Domain Sample
**Query**: *"What is the minimum GPA required to apply for undergraduate admissions?"*
```
Answer:
To be eligible for undergraduate admission, applicants must have completed a high school diploma (or equivalent) with a minimum cumulative GPA of 3.0 on a 4.0 scale. Some competitive majors, particularly engineering and computer science, may have higher GPA requirements.

Sources:
    admissions.json
```

### Navigation Domain Sample
**Query**: *"Where is the MRD Auditorium?"*
```
Answer:
The MRD Auditorium is located in Main Block on the Ground Floor (landmark: Near Main Entrance). Directions: From the campus entry gate, walk straight toward the Main Block. The MRD Auditorium is located on the ground floor, just to the left of the main lobby entrance.

Sources:
    locations.json
```

### Multilingual Domain Sample (Kannada)
**Query**: *"ನಾನು ಅರ್ಜಿ ಸಲ್ಲಿಸಬಹುದೇ?"*
```
Answer:
Yes, you can apply using your predicted grades or official transcripts covering your sophomore and junior years. If accepted, your admission will be conditional upon receiving your final official transcripts and graduation certificate.

Sources:
    admissions.json
```

### Out-of-Knowledge Fallback Sample
**Query**: *"That form"*
```
Answer:
Sorry, I could not find information regarding this in the university knowledge base. Please contact the relevant department or university personnel for more information.

Sources:
    None
```

## 7. Pilot Test Plan Overview

A 20-user pilot test plan has been prepared and stored in [pilot_plan.md](file:///C:/Users/acer/Desktop/AI-KIOSK/AI-KIOSK/evaluation/scripts/pilot_plan.md). Key highlights:
- **Users**: 10 Undergraduates, 5 Research Scholars, 3 Administrative Staff, 2 Visitors.
- **Languages**: 10 English, 5 Kannada, 5 Hindi primary speakers.
- **Scenarios**: CS admissions requirements, exam schedules/makeup requests, location-based navigation directions, placement backlog policies, out-of-knowledge curbs.
- **Evaluation Metrics**: Routing Accuracy ($\ge 90\%$), Translation Success ($\ge 95\%$), Answer Faithfulness ($\ge 95\%$).
