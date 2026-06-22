# VidyaSahayak: Multilingual Campus AI Kiosk
**Final Presentation — June 2026**

This document outlines the **15-slide deck** prepared for the final project presentation and demo day.

---

## Slide 1: Title Slide
* **Title:** VidyaSahayak: A Multilingual AI Kiosk System with Refined Interactive Ambiguity Resolution (RIAR)
* **Subtitle:** Final Sprint Release & Evaluation
* **Presenters:** Haseeb (Project Lead), Gowtham (Knowledge Systems Lead), Harsha (Engineering Lead)
* **Affiliation:** PES University, Department of Computer Science & Engineering
* **Visual:** Project logo, sleek dark theme with gold accent, system mockup.

---

## Slide 2: The Problem
* **Bullet Points:**
  * Navigating a modern campus is challenging for new students, parents, and visitors.
  * Static digital portals and touch kiosks lack interactive, natural conversation.
  * Natural language queries are often vague, ambiguous, or multilingual.
  * Off-the-shelf LLMs hallucinate and lack specific, cited campus data.
* **Visual:** A diagram showing the "Information Gap" (User query vs. fragmented campus documents).

---

## Slide 3: The Solution
* **Bullet Points:**
  * **VidyaSahayak**: A physical conversational AI kiosk.
  * **Key Capabilities:**
    * Computer vision-based user detection (YOLOv8) triggers a responsive avatar greeting.
    * Voice interaction using Whisper ASR and Text-to-Speech (TTS).
    * Refined Interactive Ambiguity Resolution (RIAR) to handle vague inputs.
    * Multilingual fallback (English, Kannada, Hindi).
    * Domain-specific multi-agent coordinator for grounded Retrieval-Augmented Generation (RAG).

---

## Slide 4: System Architecture
* **Bullet Points:**
  * E2E modular design: Hardware interfaces $\rightarrow$ Backend APIs $\rightarrow$ Agent Pipeline $\rightarrow$ Knowledge Base.
  * FastAPI server running on `:8000` with WebSocket support for real-time transcription.
  * SQLite database for persistent session storage and turn logging.
* **Visual:** Block diagram showing inputs (camera, microphone), coordinator routing, vector database, and outputs (screen, avatar, speaker).

---

## Slide 5: Real-Time Detection & ASR
* **Bullet Points:**
  * **Detection:** YOLOv8 running locally detects human presence and activates the greeting sequence.
  * **Avatar State Machine:** `IDLE` $\rightarrow$ `GREETING` $\rightarrow$ `LISTENING` $\rightarrow$ `SPEAKING`.
  * **ASR:** Microphone stream processed through Voice Activity Detection (VAD) and Whisper ASR.
* **Visual:** Screen grab of the avatar interface and presence-bounding boxes from the YOLO detector.

---

## Slide 6: Refined Interactive Ambiguity Resolution (RIAR)
* **Bullet Points:**
  * Traditional search fails on ambiguous queries like *"How do I apply?"*.
  * **RIAR Pipeline Steps:**
    1. Probe Retrieval
    2. Ambiguity Scoring
    3. Ambiguity Classification (Scope, Referent, Language, Domain)
    4. Clarification Dialog Generation
    5. Query Refinement
* **Visual:** Flowchart showing an ambiguous query splitting into choices, user input, and the refined query.

---

## Slide 7: Coordinator & Domain-Specific Agents
* **Bullet Points:**
  * The **Coordinator Agent** acts as a central router utilizing semantic classification.
  * Routes queries to six dedicated domain experts:
    * **AdmissionsAgent**: Requirements, GPA rules, and fee schedules.
    * **AcademicsAgent**: Attendance policies, repeating courses, transcripts.
    * **PlacementsAgent**: Corporate processes, "One Student, One Job" rules.
    * **ResearchAgent**: Funded assistantships, lab access, UROP.
    * **StudentServicesAgent**: Hostel allocation, library, counseling.
    * **NavigationAgent**: STEP-BY-STEP landmark directions.

---

## Slide 8: Multilingual Concierge (Kannada & Hindi)
* **Bullet Points:**
  * Ingests speech/text in Kannada and Hindi.
  * Language Fallback translates queries to English to maximize semantic search quality.
  * Retrieves documents and generates the cited response.
  * Translates the response back to the user's primary language.
* **Visual:** Diagram of the translation loop showing the user asking in Kannada, routing in English, and reading the answer in Kannada.

---

## Slide 9: Knowledge Base & Vector Ingestion
* **Bullet Points:**
  * Sources: Admissions FAQs, Academic regulations handbook, Placement policy document, Research lab guides, Hostel & library manuals, Campus GIS coordinates.
  * Ingested into **ChromaDB** using semantic chunking.
  * Metadata tagging by domain to enforce agent security and partitioning.

---

## Slide 10: Quantitative Evaluation Setup (Gowtham)
* **Bullet Points:**
  * Evaluated on a curated, benchmark dataset of **530 annotated queries**.
  * **Query Distribution:**
    * English Seed: 300 queries
    * Kannada: 100 queries
    * Hindi: 100 queries
    * Ambiguous: 30 queries
  * **Metrics tracked:** Routing Accuracy, Context Precision & Recall, Faithfulness (RAGAS), Latency, and Unknown-Question handling.

---

## Slide 11: Quantitative Results (Gowtham)
* **Bullet Points:**
  * **Routing Accuracy:** **93.40%** (Target: $\ge 90\%$)
  * **Retrieval Accuracy (Avg P&R):** **81.57%** (Target: $\ge 75\%$)
  * **Answer Faithfulness:** **0.9554** (Target: $\ge 0.90$)
  * **Hallucination Rate:** **4.46%** (Target: $< 10\%$)
  * **Unknown-Question Success Rate:** **31.25%** (Target: $\ge 30\%$)
* **Visual:** Bar chart comparing targeted vs. achieved scores.

---

## Slide 12: Performance & Latency Analysis (Gowtham)
* **Bullet Points:**
  * **Average Latency (CPU fallback):** **53.34 seconds**.
  * **GPU Acceleration Latency:** **<3.0 seconds** (E2E Whisper ASR + Local Qwen RAG + TTS).
  * **Optimization implemented:** Async parallelism in routing and retrieval; LLM warmup caches.
* **Visual:** Latency distribution chart.

---

## Slide 13: 20-User Pilot Test Feedback (Gowtham)
* **Bullet Points:**
  * Pilot demographics: 10 undergraduates, 5 postgraduates, 3 administrative staff, 2 visitors/parents.
  * **Average user satisfaction ratings (out of 5.0):**
    * Information Accuracy: **4.65**
    * Response Speed: **4.45**
    * Ease of Use: **4.80**
    * Language Support: **4.55**
    * Aesthetics & UI: **4.70**
* **Visual:** Pie chart showing demographic breakdown and a radial chart of ratings.

---

## Slide 14: Core Achievements & Implementation Progress
* **Bullet Points:**
  * Merged all weekly goals for Weeks 1 to 5 into the main branch.
  * Finished Week 6 benchmark evaluation freeze and user pilot tests.
  * Finished Week 7 packaging, deployment guides, and git tagging.
  * **Release version `v1.0.0`** is fully live and operational.
* **Visual:** GitHub release badge, git tree showing branches merged.

---

## Slide 15: Conclusion & Q&A
* **Bullet Points:**
  * VidyaSahayak demonstrates a highly accurate, accessible, and robust AI Kiosk system.
  * Future work includes local multilingual TTS synthesis and 3D visual SLAM map navigation.
  * Open source repository is fully documented.
* **Text:** "Thank you! Any Questions?"
* **Contact:** research@pesu.edu
