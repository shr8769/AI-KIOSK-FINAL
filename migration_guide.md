# Migration Guide: Switching to the Authentic Markdown Knowledge Base

This guide outlines how to safely transition the AI Kiosk backend from the synthetic ChatGPT-generated FAQ JSON database to the new authentic knowledge base built from official university web scrapes and documents.

---

## 1. Pipeline Comparison

| Step | Legacy Ingestion Pipeline (`ingest.py`) | Improved Ingestion Pipeline (`ingest_markdown.py`) |
| :--- | :--- | :--- |
| **Input Source** | Synthetic static JSON files under `knowledge/sources/` | Scraped Markdown official pages under `knowledge_new/` |
| **Parsing** | Direct Q&A lists or facility lists parsing | YAML Frontmatter extraction + heading-based logical section splitting |
| **Chunking** | **None** (Each JSON item maps 1:1 to a document) | **Heading-Aware Paragraph-Safe Chunker**: Splits text by headings (H1–H4) into sections. Sections $\le$ 500 words stay single. Large sections are split with 100-word overlap. Different headings are **never** merged. |
| **Embeddings** | `all-MiniLM-L6-v2` | `all-MiniLM-L6-v2` (Unchanged for compatibility) |
| **Vector Store** | ChromaDB stored in `knowledge/vectorstore/` | ChromaDB stored in `knowledge/vectorstore_new/` (parallel testing) |

---

## 2. Heading-Aware Logical Section Chunking Strategy

To prevent topic mixing in single vector embeddings, the improved chunker structures documents by markdown headings (`#`, `##`, `###`, `####`):

1. **Section Isolation**: Every heading marks the beginning of a separate logical topic section. 
2. **Coherence Preservation**: Sections that are smaller than 500 words are left as a single chunk. Large sections (> 500 words) are split into multiple chunks with a 100-word overlap.
3. **No Cross-Topic Leakage**: The chunker is strictly scoped to each section. Text from different headings is never merged into a single chunk.
4. **Collision-Safe Unique IDs**: Chunk IDs are computed as `f"{collection}_{slug}_{heading_clean}_{heading_hash}_c{chunk_number}"` where `heading_hash` is an MD5 hash of the heading text. This prevents duplicate ID collisions during database upserts.

---

## 3. Metadata Structure

Every chunk in the new vector store contains the following metadata:

* `title`: Document main title (from YAML frontmatter or filename).
* `heading`: Heading of the section the chunk belongs to (e.g. `Bachelor of Technology (B.Tech)`).
* `category`: Document category folder name.
* `source_url`: Page source URL.
* `document_name`: Filename (e.g. `admissions.md`).
* `chunk_id`: Unique chunk identifier.
* `chunk_number`: 1-based index of this chunk within the section.
* `total_chunks`: Total chunks count for this section.

---

## 4. Legacy Collections Mapping

To ensure the existing RAG agents continue working without any code modifications, the new 18 categories/folders are grouped into the 6 legacy ChromaDB collections:

* **`admissions`**: `admissions`, `scholarships`, `orientation`, `important_dates`, `government_sources`
* **`academics`**: `programs`, `departments`, `academic_calendar`
* **`placements`**: `placements`
* **`research`**: `research`
* **`student_services`**: `hostels`/`hostel`, `transportation`, `student_services`, `library`, `events`, `campus_life`, `student_support`, `clubs`
* **`navigation`**: `campus_facilities`, `campus_maps`, `navigation`

---

## 5. Step-by-Step Switchover Steps

### Step 1: Run the Scraper to Update Markdown Files
Run the sequential target-list scraper to fetch, clean, and populate the `knowledge_new/` directory:
```bash
python -m new_backend.scraper.scrape_pes
```

### Step 2: Build the New Parallel Vector Database
Run `ingest_markdown.py` targeting a parallel directory. This keeps the active production database untouched during the ingestion run:
```bash
python ingest_markdown.py --db-path knowledge/vectorstore_new --reset
```
*Wait for the script to load the SentenceTransformer model and complete chunk upserts.*

### Step 3: Run Verification Queries
Test the parallel database using the query portal to check similarity distance and chunk relevance:
```bash
# On Windows Command Prompt/PowerShell (forces UTF-8 console output to prevent encoding crashes):
$env:PYTHONIOENCODING="utf-8"
python query.py --db-path knowledge/vectorstore_new --collection admissions --query "admission eligibility criteria B.Tech"
```

### Step 4: Promote to Production
To switch the active agent backend to use the new markdown database, rename the folders in your filesystem. This does not require any code modifications:
1. Stop the active backend server.
2. Rename the old folder:
   * `knowledge/vectorstore` $\rightarrow$ `knowledge/vectorstore_old`
3. Rename the new folder:
   * `knowledge/vectorstore_new` $\rightarrow$ `knowledge/vectorstore`
4. Restart the backend server. The agents will now retrieve context from the new chunked Markdown documents.
