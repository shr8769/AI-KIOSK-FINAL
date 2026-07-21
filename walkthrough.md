# Walkthrough — AI Kiosk Production Ready Integration

This walkthrough details the successful production integration of the PES University AI Kiosk. All startup path configuration issues, retrieval false-negatives, out-of-domain checks, conversation memory, interactive terminal chat interfaces, LLM offline fallbacks, and terminal cleanup are fully resolved and tested.

---

## 🛠️ Production Bugs Resolved

### 🐞 BUG 1: Wrong Chunk Retrieval (M.Tech instead of B.Tech)

#### **Root Cause Analysis**
1. **Search Space Limitation:** The retrieval pipeline queried ChromaDB for only `n_results=5`. In raw vector space, `Master of Technology (M.Tech)` returned a higher distance rank than `Bachelor of Technology (B.Tech)` (which was Result #8 in distance). Thus, the correct B.Tech chunk was filtered out before the re-ranker could compute keyword or metadata boosts.
2. **Missing Normalization:** Program acronyms like `B.Tech` and `M.Tech` were split by the tokenizer's word boundary check `\b\w+\b` into `["b", "tech"]` and `["m", "tech"]`. Dots `.` or unified forms (`btech`, `mtech`) were not normalized, leading to low metadata boost matching accuracy.

#### **Implementation Fixes**
- **Expanded Candidate Space:** Increased vector query capacity to `n_results=15` inside [base_agent.py](file:///c:/Users/acer/Documents/AI-KIOSK/agents/domain/base_agent.py). This guarantees the target program chunks are captured in the candidate list.
- **Acronym Normalization:** Normalised program acronyms (`b.tech`/`btech` -> `btech`, `m.tech`/`mtech` -> `mtech`, `b.sc`/`bsc` -> `bsc`, etc.) across queries, headings, titles, categories, and overlap calculations.
- **Result:** For query *"What is the eligibility for B.Tech?"*, the correct B.Tech chunk now scores **`2.4833`** and ranks **1st**, while M.Tech drops to **8th** (Score: `0.7061`).

---

### 🐞 BUG 2: Qwen Timeout & Gemini Quota Falls to Error/Contact Fallback

#### **Root Cause Analysis**
1. **No Degraded Caching on Startup:** If Ollama was offline at startup, it was checked on every query, causing minor blocking waits.
2. **120-Second Generation Timeout:** The request to `/api/generate` waited up to 120.0 seconds if Ollama hung on CPU loading.
3. **Fragile Fallback:** When Gemini hit free-tier rate limits (429 quota exhaustion) and Qwen was offline, the agent fell back to the contact fallback or raised an error, disrupting kiosk usability.

#### **Implementation Fixes**
- **Circuit Breaker Caching:** Added `check_health()` status caching with a 30-second cooldown in [qwen_client.py](file:///c:/Users/acer/Documents/AI-KIOSK/agents/llm/qwen_client.py). If Ollama is unavailable, the state is cached and Qwen is immediately skipped.
- **5-Second Timeout Limit:** Reduced generation urllib timeout to `5.0` seconds.
- **Offline Markdown Fallback:** If both LLMs are offline or degraded, [base_agent.py](file:///c:/Users/acer/Documents/AI-KIOSK/agents/domain/base_agent.py) executes `offline-markdown-fallback`. It parses and returns the raw answer text from the retrieved database chunk, keeping the kiosk 100% operational offline.

---

### 🧹 Production Cleanup & Console Silencing

#### **Root Cause Analysis**
- Standard python warnings, sentence-transformer weights loading bar (`tqdm`), and HF unauthenticated hub notices were leaking into standard error / standard output, cluttering the user interface.

#### **Implementation Fixes**
- **Redirected Stderr:** Stderr is redirected to `kiosk.log` in production mode (non-debug mode). This silences all C-level and Python-level stdout/stderr warning outputs.
- **Disabled progress bars:** Suppressed `tqdm` globally in `chat.py` by setting `TQDM_DISABLE=1` and `HF_HUB_DISABLE_SYMLINKS_WARNING=1` environment flags.
- **Suppressed Loggers:** Silenced python root logger and third-party loggers (`chromadb`, `urllib3`, `google`, `huggingface`, `sentence_transformers`) unless `--debug` is explicitly supplied.
- **Clean output loop:** The terminal prints only the `You:` and `AI:` dialogue blocks separated by a clean separator.

---

## 📊 Candidate Scores & Validation Run Details

Here is the top-10 candidate profile outputted during the validation run:

```text
Query 1: What is the eligibility for B.Tech?
* Routed Domain: admissions

Retrieved Documents:

Document 1:
* ID: admissions_admissions_bacheloroftechn_b8175bb7_c1
* Title: PES University Page
* Heading: Bachelor of Technology (B.Tech)
* Distance: 0.4635
* Similarity Score: 0.6833
* Keyword Score: 1.0000
* Final Score: 2.4833

Document 2:
* ID: admissions_admissions_bacheloroftechn_23ace518_c1
* Title: PES University Page
* Heading: Bachelor of Technology (B.Tech) - Diploma Lateral Entry
* Distance: 0.5165
* Similarity Score: 0.6594
* Keyword Score: 1.0000
* Final Score: 2.4594

Document 3:
* ID: admissions_comedk_eligibilitycrit_bd4bc160_c1
* Title: COMEDK Guidelines and Ingestion Support
* Heading: Eligibility Criteria
* Distance: 0.4593
* Similarity Score: 0.6852
* Keyword Score: 0.5000
* Final Score: 1.7352

Document 4:
* ID: admissions_docs_btech_072cedbe_c1
* Title: PES University Page
* Heading: B.Tech
* Distance: 0.4630
* Similarity Score: 0.6835
* Keyword Score: 0.5000
* Final Score: 1.7335

Document 8:
* ID: admissions_admissions_masteroftechnol_8aed98b8_c1
* Title: PES University Page
* Heading: Master of Technology (M.Tech)
* Distance: 0.4162
* Similarity Score: 0.7061
* Keyword Score: 0.0000
* Final Score: 0.7061

Selected Document:
* ID: admissions_admissions_bacheloroftechn_b8175bb7_c1
* Selected heading: Bachelor of Technology (B.Tech)
* LLM used: offline-markdown-fallback

ANSWER:
#### Bachelor of Technology (B.Tech)
**Eligibility Criteria**
60% aggregate marks in Physics + Math + Chemistry of 10+2 or equivalent...
```
All 8 mandatory target queries route, retrieve, and synthesize responses successfully without contact fallbacks.

---

## 🌐 Website Scraping Pipeline Audit & Upgrades

### 🐞 Audited Problems & Causes
1. **Missing Dynamic/Accordion Content:** The legacy scraper relied on static HTTP requests (`requests.get`). It could not render JavaScript-loaded elements, expand tabs, click nested accordions, or load AJAX-driven quota details. This led to incomplete page data ingestion (e.g. at `https://pes.edu/docs/`).
2. **Incorrect Heading De-duplication:** In `cleaner.py`, the `HTMLCleaner` maintained a global `self.seen_headings` set, which stripped all duplicate heading labels on a page. This caused valid identical headings under different degree sections (such as `#### KCET Quota` or `#### Eligibility Criteria` appearing in B.Tech, MBBS, B.Arch, and B.Pharm) to be completely deleted.
3. **Duplicate Chunk ID Conflicts:** `ingest_markdown.py` formatted unique chunk IDs using only the heading name and a hash. When duplicate headings occurred (e.g. `KCET Quota`), or when files existed in legacy folders (like `knowledge_new/general/docs.md` alongside the new `knowledge_new/admissions/docs.md`), it generated duplicate IDs, causing ChromaDB validation failures.

---

### ⚙️ Implementation Upgrades
- **Headless Selenium Edge Webdriver:** Integrated headless Microsoft Edge into `crawler.py` and `scrape_pes.py` to support dynamic rendering. Selenium 4 manages Edge WebDriver binaries automatically on Windows, requiring zero manual configuration.
- **Recursive Accordion & Tab Clicking:** Implemented `_expand_accordions_recursively(url)` in `crawler.py`. It loops and clicks collapsed headers and tab panels matching selectors like `.gdlr-core-accordion-item-title` and `[data-toggle='collapse']`, resolving nested collapsible trees dynamically.
- **Improved Cleaner Logic:** Disabled seen-heading de-duplication to prevent losing structured program checklists, and added quality checks to enforce minimum word count (>25) and structural tag presence, marking boilerplate/404 pages as `FAILED`.
- **Unique Chunk IDs:** Updated chunk ID generation to include the section index (`_s{section_idx}`), ensuring all program checklist chunks generate unique database records.
- **Legacy Folder Cleanup:** Deleted leftover directories (like `knowledge_new/general/`) to prevent conflict during vector database creation.

---

### 📊 Crawl & Database Verification Results

#### **Scraper Execution Metrics (Latest Run)**
* **Total Target URLs Attempted:** 40 (up from 15)
* **Successfully Processed Pages:** 37 (up from 12)
* **Failed Pages (404 / Empty):** 3 (correctly failed quality checks)
* **Accordions Successfully Expanded:** 239 (up from 115)
* **Characters Extracted:** 162,884 (up from 65,662 — +148%)
* **Duplicate Lines Removed:** 921
* **Execution Duration:** 625.05 seconds
* **Scraper Report File Saved:** [verification_report.md](file:///c:/Users/acer/Documents/AI-KIOSK/new_backend/scraper/output/verification_report.md)

#### **New Pages Discovered & Scraped**
The auto-discovery system found and scraped these sub-pages automatically:
- `pes.edu/fee/` — Fee details (6,427 bytes)
- `pes.edu/exams/` — Qualifying exams (2,823 bytes)
- `pes.edu/loyalty/` — Loyalty program (5,379 bytes)
- `pes.edu/hostel/boys` — Boys hostel (891 bytes)
- `pes.edu/transportation/rr/` — RR campus bus routes (6,563 bytes)
- `pes.edu/transportation/ec/` — EC campus bus routes (5,917 bytes)
- `pes.edu/btech/` — B.Tech program details (4,840 bytes)
- `pes.edu/mtech/` — M.Tech program details (10,525 bytes)
- `pes.edu/mca/` — MCA program details (15,303 bytes)
- `pes.edu/mba/` — MBA program details (11,240 bytes)
- `pes.edu/phd/` — PhD program details (7,654 bytes)
- `pes.edu/intake/rr/`, `/ec/`, `/hn/` — Intake data per campus
- `pes.edu/contact/` — Contact page (2,443 bytes)
- `pes.edu/academics/undergraduate/`, `/postgraduate/` — Academics listings

#### **Markdown Ingestion Summary**
* **Total Markdown Documents:** 43 (up from 18)
* **Total Chunks Ingested:** 608 (up from 296 — +105%)
* **Total Failed Chunks:** 0

| Collection | Before | After |
|---|---|---|
| admissions | 133 | **284** |
| academics | 53 | **179** |
| placements | 9 | 5 |
| student_services | 84 | **96** |
| navigation | 17 | **44** |

#### **Key Improvements**
1. **Boilerplate Footer Removal** — "Giving to PES", "Staying in Touch", "Discovering our Newsletters" sections stripped from all pages
2. **Auto Sub-Page Discovery** — Links on scraped pages are automatically followed (restricted to `pes.edu` main domain)
3. **Expanded URL Coverage** — TARGET_URLS expanded from 15 to 21, with auto-discovery finding 19 additional pages
4. **Removed 404 Pages** — `student-services/`, `library/`, `clubs/` removed from target list
