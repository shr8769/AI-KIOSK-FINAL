import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any

# Ensure the repository root is in python path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import chromadb  # noqa: E402
from chromadb.utils import embedding_functions  # noqa: E402
import ingest_markdown  # noqa: E402

logger = logging.getLogger(__name__)

def get_chroma_client(db_path: str) -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=db_path)

def get_embedding_function():
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

def ingest_single_file(file_path: Path, db_path: str) -> Dict[str, Any]:
    """
    Parses, chunks, validates, and embeds a single Markdown file incrementally into ChromaDB.
    Before adding new chunks, it deletes any existing chunks with the same relative path
    to prevent duplicate or orphaned chunks.
    """
    logger.info(f"Incrementally ingesting file: {file_path}")
    
    # Reset seen file hashes lock tracking for this file so it doesn't get skipped as duplicate
    try:
        with ingest_markdown.hashes_lock:
            ingest_markdown.seen_file_hashes.clear()
    except Exception as e:
        logger.warning(f"Could not clear seen file hashes: {e}")
        
    # Process the file using the exact logic from ingest_markdown.py
    success, chunk_list, reason_code, reason_detail, ops = ingest_markdown.process_file_task(file_path)
    
    if not success:
        logger.error(f"Failed to process file [{file_path}]: {reason_code} - {reason_detail}")
        return {
            "status": "failed",
            "reason_code": reason_code,
            "reason_detail": reason_detail,
            "chunks_upserted": 0,
            "chunks_purged": 0
        }
        
    if not chunk_list:
        logger.warning(f"No chunks generated for file [{file_path}]")
        return {
            "status": "skipped",
            "reason_code": "NO_CHUNKS",
            "reason_detail": "No valid chunks could be generated.",
            "chunks_upserted": 0,
            "chunks_purged": 0
        }
        
    # Ingest the chunks into ChromaDB
    try:
        client = get_chroma_client(db_path)
        emb_fn = get_embedding_function()
        
        # We assume all chunks in the file list go to the same collection (standard design)
        target_collection_name = chunk_list[0]["collection"]
        collection = client.get_or_create_collection(
            name=target_collection_name,
            embedding_function=emb_fn
        )
        
        # 1. Purge existing chunks with the same relative path or slug
        relative_path_val = chunk_list[0]["metadata"]["relative_path"]
        slug_val = chunk_list[0]["metadata"]["slug"]
        
        purged_count = 0
        try:
            # Query count of existing docs with this relative path
            existing = collection.get(where={"relative_path": relative_path_val})
            if existing and existing["ids"]:
                purged_count = len(existing["ids"])
                logger.info(f"Purging {purged_count} existing chunks in '{target_collection_name}' for relative path '{relative_path_val}'")
                collection.delete(where={"relative_path": relative_path_val})
        except Exception as e:
            logger.warning(f"Error purging old chunks for '{relative_path_val}': {e}. Attempting slug purge...")
            try:
                collection.delete(where={"slug": slug_val})
            except Exception:
                pass
                
        # 2. Upsert the new chunks
        ids = [c["id"] for c in chunk_list]
        docs = [c["document"] for c in chunk_list]
        metas = [c["metadata"] for c in chunk_list]
        
        sub_batch_size = 100
        for i in range(0, len(chunk_list), sub_batch_size):
            collection.upsert(
                ids=ids[i:i+sub_batch_size],
                documents=docs[i:i+sub_batch_size],
                metadatas=metas[i:i+sub_batch_size]
            )
            
        logger.info(f"Successfully upserted {len(chunk_list)} new chunks into '{target_collection_name}' for '{relative_path_val}'")
        return {
            "status": "success",
            "chunks_upserted": len(chunk_list),
            "chunks_purged": purged_count,
            "chunk_ids": ids,
            "collection": target_collection_name
        }
    except Exception as e:
        logger.error(f"Database error during incremental ingestion of '{file_path}': {e}")
        return {
            "status": "db_error",
            "reason_detail": str(e),
            "chunks_upserted": 0,
            "chunks_purged": 0
        }

def delete_single_file_chunks(relative_path: str, category: str, db_path: str) -> Dict[str, Any]:
    """
    Cleans up all database chunks associated with a relative file path.
    """
    logger.info(f"Incrementally deleting chunks for relative path: {relative_path} (category: {category})")
    
    target_collection_name = ingest_markdown.get_legacy_collection(category)
    
    try:
        client = get_chroma_client(db_path)
        emb_fn = get_embedding_function()
        
        collection = client.get_collection(
            name=target_collection_name,
            embedding_function=emb_fn
        )
        
        existing = collection.get(where={"relative_path": relative_path})
        purged_count = 0
        if existing and existing["ids"]:
            purged_count = len(existing["ids"])
            logger.info(f"Purging {purged_count} chunks in '{target_collection_name}' for deleted relative path '{relative_path}'")
            collection.delete(where={"relative_path": relative_path})
            
        return {
            "status": "success",
            "chunks_deleted": purged_count,
            "collection": target_collection_name
        }
    except Exception as e:
        logger.error(f"Database error during deletion of chunks for '{relative_path}': {e}")
        return {
            "status": "db_error",
            "reason_detail": str(e),
            "chunks_deleted": 0
        }
