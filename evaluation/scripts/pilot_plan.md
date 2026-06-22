# Pilot Test Plan - VidyaSahayak Campus Kiosk

This document details the pilot test plan for evaluating the **VidyaSahayak Campus Kiosk** with a group of 20 representative users.

---

## 1. Objectives
- Validate user experience, routing accuracy, and answer synthesis quality under realistic deployment conditions.
- Measure average and peak latencies to assess system performance on the integrated hardware.
- Evaluate the effectiveness of language fallback (English, Kannada, Hindi) on kiosk interactions.
- Identify edge cases, out-of-knowledge queries, and routing failures in a live environment.
- Collect quantitative and qualitative feedback to prioritize future improvements.

---

## 2. Participant Profile
- **Total Users**: 20 participants.
- **Demographics**:
  - 10 Undergraduate Students (various majors/years).
  - 5 Post-graduate/Research Scholars.
  - 3 Admissions/Office Administrative Staff.
  - 2 Visitors/Parents.
- **Language Preferences**:
  - 10 English primary speakers.
  - 5 Kannada primary speakers.
  - 5 Hindi primary speakers.

---

## 3. Test Scenarios
Each participant will be asked to complete 5 tasks representing different student journeys:

### Scenario A: New Admission (Admissions Domain)
- **Task**: Find out the eligibility requirements for the computer science program and check if letters of recommendation are mandatory.
- **Expected Outcome**: Correct routing to AdmissionsAgent, retrieval of admissions FAQs, and accurate Qwen3-8B synthesis with citations.

### Scenario B: Exam Schedule & Grades (Academics Domain)
- **Task**: Check the attendance requirement to write final exams and how to apply for a makeup exam if missed.
- **Expected Outcome**: Correct routing to AcademicsAgent and accurate response with academic handbook sources cited.

### Scenario C: Campus Navigation (Navigation Domain)
- **Task**: Ask the kiosk where the MRD Auditorium is and how to walk to the Central Library from the entrance.
- **Expected Outcome**: Correct routing to NavigationAgent, retrieve physical instructions from locations database, and display accurate landmarks.

### Scenario D: Placement Registration (Placements Domain)
- **Task**: Verify if backlogs affect placement eligibility and check how to upload a resume.
- **Expected Outcome**: Correct routing to PlacementsAgent and accurate registration procedures returned.

### Scenario E: General Inquiry / Unknown (Out-of-Knowledge)
- **Task**: Ask the kiosk about the VC's home phone number or the menu at the hostel dinner today.
- **Expected Outcome**: Correct detection of insufficient database context, returning the standardized fallback message gracefully with a "None" source.

---

## 4. Question Categories
To test the language fallback and processing pipelines, participants will query in different formats:
1. **Standard English Queries**: Direct, factual questions.
2. **Multilingual Queries**: Questions phrased in Kannada or Hindi.
3. **Ambiguous/Conversational Queries**: Informal or poorly structured phrasing (e.g. "where class?" or "how pay?").
4. **Out-of-Knowledge Queries**: Questions outside the kiosk's knowledge base.

---

## 5. Success Metrics
The pilot will be evaluated against the following key performance indicators:

| Metric | Target | Description |
| :--- | :--- | :--- |
| **Routing Accuracy** | $\ge 90\%$ | Coordinator correctly routes the query to the correct domain agent. |
| **Translation Success** | $\ge 95\%$ | Kannada and Hindi queries are correctly detected and translated to English. |
| **Answer Faithfulness** | $\ge 95\%$ | Synthesized responses contain no hallucinations or unsupported claims. |
| **Source Citation Rate** | $100\%$ | Every answer must include a valid source file citation (or `None` for fallbacks). |
| **Average Response Latency**| $\le 3.0$ seconds | The response is generated and displayed on screen (excluding local model load time). |

---

## 6. Expected Response Times
- **Cached/Retrieval-Only Queries**: $\le 0.5$ seconds.
- **Standard English RAG Queries (Qwen local)**: $\le 5.0$ seconds (assuming warm cache).
- **Translated RAG Queries (Kannada/Hindi)**: $\le 7.0$ seconds.
- **Fallback / Out-of-Knowledge Queries**: $\le 1.0$ seconds.

---

## 7. Known Limitations
- **Ollama Warmup Latency**: The first query after startup may take up to 60 seconds as the Qwen3-8B model loads into memory. A background warmup call is implemented to mitigate this.
- **Gemini Free Tier Quota Limits**: Translation and fallback API calls are subject to rate limiting (e.g. 15 requests per minute). Clean fallback to similarity-only filters is triggered if quotas are exhausted.
- **Local CPU/GPU Performance**: Response times are heavily dependent on kiosk hardware specs.

---

## 8. Error Reporting Procedure
If the kiosk displays an incorrect answer, hangs, or fails to route:
1. The moderator will note down the exact query and timestamp.
2. Check the system log file at `C:\Users\acer\Desktop\AI-KIOSK\AI-KIOSK\ingestion.log` and `evaluation/results/evaluation_log.jsonl` for error tracebacks.
3. Report bugs using the issue template including:
   - Query text and language.
   - Screen screenshot/recording.
   - Error logs / traceback if available.

---

## 9. Evaluation Criteria (Participant Questionnaire)
Participants will complete the following feedback form after testing (Likert Scale 1-5):

1. **Information Accuracy**: Did the kiosk provide the correct answer? (1: Not at all - 5: Completely)
2. **Speed**: Was the response time acceptable? (1: Too slow - 5: Very fast)
3. **Ease of Use**: Was it easy to interact with the kiosk? (1: Difficult - 5: Very easy)
4. **Language Support**: Did the Kannada/Hindi translation feel natural? (1: Poor - 5: Excellent)
5. **Aesthetics & UI**: Was the screen layout clear and readable? (1: Cluttered - 5: Clean and premium)

---

## 10. Future Improvements
- Deploy offline machine translation pipeline (IndicTrans2) to completely remove external internet dependencies.
- Implement streaming tokens on the frontend UI to reduce perceived latency during LLM synthesis.
- Integrate voice-to-text (ASR) and text-to-speech (TTS) pipelines for hands-free operations.
- Dynamically update vector databases from Google Drive/OneDrive syncs.
