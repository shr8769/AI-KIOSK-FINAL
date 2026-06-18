# ChromaDB Collection Contract — VidyaSahayak
# Version 1.0 — June 2026

## Collection Names
admissions_collection
academics_collection
placements_collection
research_collection
navigation_collection
student_services_collection

## Chunk Metadata Schema (every chunk in every collection)
{
  "domain":      string,   # collection domain name
  "source_file": string,   # original PDF or document name
  "page":        int,      # page number if applicable
  "chunk_id":    string,   # uuid
  "indexed_at":  string    # ISO timestamp
}

## Query Interface
collection.query(
  query_embeddings=[embedding],  # list of one float array
  n_results=int,                 # max chunks to return
  include=["documents","metadatas","distances"]
)

## Distance Metric
cosine  # confidence = 1 - distance

## Embedding Model
all-MiniLM-L6-v2  # or whichever model — must match indexing model

## Confidence Thresholds (agreed values)
HIGH:   >= 0.68   # strong domain signal
MEDIUM: 0.45-0.67 # weak signal
LOW:    < 0.45    # treat as no hit
