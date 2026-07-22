#!/usr/bin/env python3
"""
ingest_markdown.py

A production-grade, heading-aware, semantic RAG ingestion pipeline for the AI Kiosk.
Ingests crawled PES University Markdown documents under knowledge_new/ recursively into ChromaDB.
"""

import os
import sys
import re
import yaml
import logging
import time
import argparse
import hashlib
import random
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List, Tuple

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    print("Error: chromadb is not installed. Please install it using 'pip install chromadb'")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, *args, **kwargs):
        return iterable

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("ingestion_markdown.log", mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_DB_PATH = os.path.join("knowledge_new", "vectorstore")
DEFAULT_KNOWLEDGE_DIR = "knowledge_new"

# Configurable Mapping Layer from directories/categories to 6 legacy ChromaDB collections
LEGACY_MAPPING = {
    # Admissions
    "admissions": "admissions",
    "scholarships": "admissions",
    "orientation": "admissions",
    "important_dates": "admissions",
    "government_sources": "admissions",
    "docs": "admissions",
    
    # Academics
    "academics": "academics",
    "programs": "academics",
    "departments": "academics",
    "academic_calendar": "academics",
    
    # Placements
    "placements": "placements",
    
    # Research
    "research": "research",
    
    # Student Services
    "student_services": "student_services",
    "hostels": "student_services",
    "hostel": "student_services",
    "transportation": "student_services",
    "library": "student_services",
    "events": "student_services",
    "campus_life": "student_services",
    "student_support": "student_services",
    "clubs": "student_services",
    "faqs": "student_services",
    
    # Navigation
    "navigation": "navigation",
    "campus_facilities": "navigation",
    "campus_maps": "navigation",
    
    # General fallback
    "general": "admissions"
}

VALID_COLLECTIONS = ["admissions", "academics", "placements", "research", "student_services", "navigation"]

import threading  # noqa: E402
seen_file_hashes = set()
hashes_lock = threading.Lock()

class LogicalBlock:
    def __init__(self, block_type: str, content: str, heading_level: int = None, heading_text: str = ""):
        self.block_type = block_type  # 'heading', 'table', 'list', 'code', 'paragraph'
        self.content = content
        self.words = len(content.split())
        self.heading_level = heading_level
        self.heading_text = heading_text

def clean_markdown_content(content: str) -> str:
    """
    Cleans raw markdown text by stripping theme toggles, language selectors,
    layout switchers, and duplicate whitespaces while preserving structural formatting.
    """
    lines = content.split("\n")
    cleaned_lines = []
    
    # Boilerplate patterns to exclude (case-insensitive)
    boilerplate_patterns = [
        r"Theme Color Mode",
        r"Navigation Styles",
        r"Vertical\s+Horizontal",
        r"Vertical\s*&\s*Horizontal",
        r"\bRTL\b.*\bLTR\b",
        r"\bLight\b.*\bDark\b.*\bSwitcher\b",
        r"^\s*Light\s*$",
        r"^\s*Dark\s*$",
        r"^\s*Switcher\s*$",
        r"^\s*RTL\s*$",
        r"^\s*LTR\s*$",
        r"^\s*Vertical\s*$",
        r"^\s*Horizontal\s*$",
        r"^\s*Toggle theme\s*$",
        r"^\s*English\s*$",
        r"^\s*Kannada\s*$",
        r"^\s*Skip to main content\s*$",
        r"^\s*Select language\s*$",
        r"Search\.\.\.",
        r"^\s*Main menu\s*$",
        r"^\s*Toggle navigation\s*$",
        r"Copyright\s+©",
        r"All\s+rights\s+reserved",
    ]
    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in boilerplate_patterns]
    
    chrome_substrings = [
        "back to pes.edu",
        "select a campus to explore",
        "explore news from every academic department",
        "browse by department",
        "find stories by topic and interest",
        "pressenterto search",
        "browse news →",
        "popular tags",
        "choose a campus",
        "choose a department",
        "choose a tag",
        "menu click",
        "menu hover",
        "icon click",
        "icon hover",
        "sidemenu layout",
        "default menu",
        "closed menu",
        "icon text",
        "icon overlay",
        "detacheddouble menu",
        "page styles:",
        "regularclassicmodern",
        "layout width styles",
        "full widthboxed",
        "menu positions:",
        "fixedscrollable",
        "loader:enabledisable",
        "menu colors:",
        "if you want to change color",
        "dynamically change from below",
        "theme primary color picker",
        "theme primary:",
        "theme background:",
        "menu with background image",
        "resetcategory",
        "support links",
        "important links",
        "pesu mobile apps",
        "download ios app",
        "download android app",
        "follow us on :",
        "powered bynithsearch"
    ]
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
            
        # Check word count of the line to decide if we can skip the whole line or just clean it
        line_word_count = len(stripped.split())
        
        is_boilerplate = False
        # Substring search
        line_lower = stripped.lower()
        for sub in chrome_substrings:
            if sub in line_lower:
                if line_word_count < 25:
                    is_boilerplate = True
                    break
                else:
                    # Just remove the boilerplate substring from the line
                    pattern = re.compile(re.escape(sub), re.IGNORECASE)
                    stripped = pattern.sub("", stripped).strip()
                    line_lower = stripped.lower()
                    
        if is_boilerplate:
            continue
            
        for pattern in compiled_patterns:
            if pattern.search(stripped):
                if line_word_count < 25:
                    is_boilerplate = True
                    break
                else:
                    # Just remove the boilerplate match from the line
                    stripped = pattern.sub("", stripped).strip()
        
        if is_boilerplate:
            continue
            
        # If after cleaning the line is empty, skip it
        if not stripped:
            continue
            
        cleaned_lines.append(stripped)
        
    cleaned_text = "\n".join(cleaned_lines)
    # Remove duplicate blank lines
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    return cleaned_text.strip()

def split_large_paragraph(text: str, max_words: int = 150) -> List[str]:
    """
    Splits a large paragraph by sentences to keep blocks small and manageable.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sub_paras = []
    curr_para = []
    curr_words = 0
    
    for sentence in sentences:
        sentence_words = len(sentence.split())
        if curr_para and curr_words + sentence_words > max_words:
            sub_paras.append(" ".join(curr_para).strip())
            curr_para = []
            curr_words = 0
        curr_para.append(sentence)
        curr_words += sentence_words
        
    if curr_para:
        sub_paras.append(" ".join(curr_para).strip())
        
    return [p for p in sub_paras if p]

def split_giant_table(table_text: str, max_words: int = 180) -> List[str]:
    """
    Splits a giant markdown table into multiple smaller tables, repeating the headers and separators.
    """
    lines = [line.strip() for line in table_text.split("\n") if line.strip()]
    if len(lines) < 3:
        return [table_text]
        
    header = lines[0]
    separator = lines[1]
    data_rows = lines[2:]
    
    # Check if lines[1] is a separator row (contains dashes and pipe characters)
    if not (separator.startswith("|") and ("-" in separator or ":" in separator)):
        return [table_text]
        
    sub_tables = []
    curr_rows = []
    curr_words = len(header.split()) + len(separator.split())
    
    for row in data_rows:
        row_words = len(row.split())
        if curr_rows and curr_words + row_words > max_words:
            sub_tables.append("\n".join([header, separator] + curr_rows))
            curr_rows = []
            curr_words = len(header.split()) + len(separator.split())
        curr_rows.append(row)
        curr_words += row_words
        
    if curr_rows:
        sub_tables.append("\n".join([header, separator] + curr_rows))
        
    return sub_tables

def split_giant_list(list_text: str, max_words: int = 150) -> List[str]:
    """
    Splits a giant markdown list into multiple smaller list blocks based on word count.
    """
    lines = list_text.split("\n")
    sub_lists = []
    curr_list_lines = []
    curr_words = 0
    
    list_item_pattern = re.compile(r"^(\s*)([\*\-\+>]|\d+\.)\s+(.+)$")
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if curr_list_lines:
                curr_list_lines.append(line)
            continue
            
        if list_item_pattern.match(line):
            line_words = len(line.split())
            if curr_list_lines and curr_words + line_words > max_words:
                sub_lists.append("\n".join(curr_list_lines).strip())
                curr_list_lines = []
                curr_words = 0
            curr_words += line_words
        else:
            curr_words += len(line.split())
            
        curr_list_lines.append(line)
        
    if curr_list_lines:
        sub_lists.append("\n".join(curr_list_lines).strip())
        
    return [sl for sl in sub_lists if sl]

def split_into_logical_blocks(content: str) -> List[LogicalBlock]:
    """
    Parses a markdown string into logical components like headings, tables,
    lists, code blocks, or paragraphs to avoid breaking their structure during chunking.
    Automatically splits giant tables, giant lists, and giant paragraphs.
    Also repairs wrapped table cell rows.
    """
    lines = content.split("\n")
    blocks = []
    
    in_code = False
    code_lines = []
    
    in_table = False
    table_lines = []
    
    in_list = False
    list_lines = []
    
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
    list_item_pattern = re.compile(r"^(\s*)([\*\-\+>]|\d+\.)\s+(.+)$")
    
    def add_paragraph_block(lines_list):
        if not lines_list:
            return
        para_text = "\n".join(lines_list).strip()
        if not para_text:
            return
        words = len(para_text.split())
        if words > 180:
            sub_ps = split_large_paragraph(para_text, max_words=120)
            for sub_p in sub_ps:
                blocks.append(LogicalBlock('paragraph', sub_p))
        else:
            blocks.append(LogicalBlock('paragraph', para_text))

    def flush_current_block():
        nonlocal in_code, in_table, in_list, code_lines, table_lines, list_lines
        if in_code and code_lines:
            blocks.append(LogicalBlock('code', "\n".join(code_lines)))
            code_lines = []
            in_code = False
        elif in_table and table_lines:
            table_str = "\n".join(table_lines)
            sub_tables = split_giant_table(table_str, max_words=180)
            for sub_t in sub_tables:
                blocks.append(LogicalBlock('table', sub_t))
            table_lines = []
            in_table = False
        elif in_list and list_lines:
            list_str = "\n".join(list_lines)
            sub_lists = split_giant_list(list_str, max_words=150)
            for sub_l in sub_lists:
                blocks.append(LogicalBlock('list', sub_l))
            list_lines = []
            in_list = False

    current_para_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # 1. Code blocks
        if stripped.startswith("```"):
            if in_code:
                code_lines.append(line)
                flush_current_block()
            else:
                add_paragraph_block(current_para_lines)
                current_para_lines = []
                flush_current_block()
                in_code = True
                code_lines.append(line)
            continue
            
        if in_code:
            code_lines.append(line)
            continue
            
        # Table row continuation repair
        if in_table and table_lines and not table_lines[-1].strip().endswith("|"):
            if stripped == "":
                flush_current_block()
            else:
                table_lines[-1] = table_lines[-1].rstrip() + " " + line.lstrip()
                continue
            
        # 2. Headings
        heading_match = heading_pattern.match(stripped)
        if heading_match:
            add_paragraph_block(current_para_lines)
            current_para_lines = []
            flush_current_block()
            
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            blocks.append(LogicalBlock('heading', line, heading_level=level, heading_text=heading_text))
            continue
            
        # 3. Tables
        is_table_line = stripped.startswith("|") or (stripped.count("|") >= 2 and (stripped.startswith("-") or stripped.startswith(":") or stripped.startswith("|")))
        if is_table_line:
            add_paragraph_block(current_para_lines)
            current_para_lines = []
            if not in_table:
                flush_current_block()
                in_table = True
            table_lines.append(line)
            continue
        elif in_table:
            flush_current_block()
            
        # 4. Lists
        is_list_line = list_item_pattern.match(line)
        if is_list_line:
            add_paragraph_block(current_para_lines)
            current_para_lines = []
            if not in_list:
                flush_current_block()
                in_list = True
            list_lines.append(line)
            continue
        elif in_list:
            if stripped == "":
                pass
            elif not line.startswith(" "):
                flush_current_block()
                
        if in_list:
            list_lines.append(line)
            continue
            
        # 5. Standard paragraph
        if stripped == "":
            add_paragraph_block(current_para_lines)
            current_para_lines = []
        else:
            current_para_lines.append(line)
            
    # Final flush
    add_paragraph_block(current_para_lines)
    flush_current_block()
    
    return [b for b in blocks if b.content.strip() != ""]

def chunk_logical_blocks(
    blocks: List[LogicalBlock], 
    doc_title: str,
    metrics_tracker: Dict[str, int]
) -> List[Tuple[str, str, str]]:
    """
    Groups logical blocks into semantic chunks with a target word average of 220-280 words.
    Ensures headings and parent context are carried forward.
    """
    chunks = []
    current_heading_path = []
    
    def get_heading_context() -> Tuple[str, str]:
        if not current_heading_path:
            return "Introduction", ""
        immediate = current_heading_path[-1][1]
        if len(current_heading_path) > 1:
            parents = " - ".join([h[1] for h in current_heading_path[:-1]])
            return immediate, parents
        return immediate, ""

    def build_chunk_text(heading: str, subheading: str, chunk_blocks: List[LogicalBlock]) -> str:
        body = "\n\n".join(b.content for b in chunk_blocks)
        q_text = f"{doc_title} - {subheading} - {heading}" if subheading else f"{doc_title} - {heading}"
        return f"Question: {q_text}\nAnswer: {body}"

    current_chunk_blocks = []
    current_word_count = 0
    
    for block in blocks:
        # If this block is giant on its own (> 230 words)
        if block.words > 230:
            if current_chunk_blocks:
                chunk_heading, chunk_subheading = get_heading_context()
                chunk_text = build_chunk_text(chunk_heading, chunk_subheading, current_chunk_blocks)
                chunks.append((chunk_heading, chunk_subheading, chunk_text))
                current_chunk_blocks = []
                current_word_count = 0
                
            chunk_heading, chunk_subheading = get_heading_context()
            chunk_text = build_chunk_text(chunk_heading, chunk_subheading, [block])
            chunks.append((chunk_heading, chunk_subheading, chunk_text))
            metrics_tracker["split"] += 1
            continue
            
        if block.block_type == 'heading':
            # Semantic chunking: flush if current chunk has actual content BEFORE updating heading path
            if current_chunk_blocks and any(b.block_type != 'heading' for b in current_chunk_blocks):
                chunk_heading, chunk_subheading = get_heading_context()
                chunk_text = build_chunk_text(chunk_heading, chunk_subheading, current_chunk_blocks)
                chunks.append((chunk_heading, chunk_subheading, chunk_text))
                
                # Setup overlap (only carry over the last 40 words, no headings)
                overlap_blocks = []
                overlap_count = 0
                for b in reversed(current_chunk_blocks):
                    if b.block_type == 'heading':
                        continue
                    if overlap_count + b.words > 40:
                        if not overlap_blocks:
                            overlap_blocks.insert(0, b)
                        break
                    overlap_blocks.insert(0, b)
                    overlap_count += b.words
                
                current_chunk_blocks = overlap_blocks
                current_word_count = sum(b.words for b in overlap_blocks)
                metrics_tracker["split"] += 1
                
            level = block.heading_level
            text = block.heading_text
            current_heading_path = [h for h in current_heading_path if h[0] < level]
            current_heading_path.append((level, text))
            
            current_chunk_blocks.append(block)
            current_word_count += block.words
            continue
            
        # If adding this block exceeds 290 words, flush the chunk
        if current_chunk_blocks and current_word_count + block.words > 290:
            chunk_heading, chunk_subheading = get_heading_context()
            chunk_text = build_chunk_text(chunk_heading, chunk_subheading, current_chunk_blocks)
            chunks.append((chunk_heading, chunk_subheading, chunk_text))
            
            # Setup overlap
            overlap_blocks = []
            overlap_count = 0
            for b in reversed(current_chunk_blocks):
                if b.block_type == 'heading':
                    continue
                if overlap_count + b.words > 40:
                    if not overlap_blocks:
                        overlap_blocks.insert(0, b)
                    break
                overlap_blocks.insert(0, b)
                overlap_count += b.words
                
            current_chunk_blocks = overlap_blocks
            current_word_count = sum(b.words for b in overlap_blocks)
            metrics_tracker["split"] += 1
            
        current_chunk_blocks.append(block)
        current_word_count += block.words
        
    if current_chunk_blocks:
        chunk_heading, chunk_subheading = get_heading_context()
        chunk_text = build_chunk_text(chunk_heading, chunk_subheading, current_chunk_blocks)
        chunks.append((chunk_heading, chunk_subheading, chunk_text))
        
    # --- Post-Processing Pass: Tiny Chunk Merging ---
    # We want to merge any chunk that is < 40 words with its neighbor
    merged_chunks = []
    i = 0
    while i < len(chunks):
        heading, subheading, text = chunks[i]
        
        # Extract the Answer body
        answer_text = ""
        lines = text.split("\n")
        for line in lines:
            if line.startswith("Answer:"):
                answer_text = text[text.find("Answer:") + 7:].strip()
                break
        if not answer_text:
            answer_text = text
            
        words = len(answer_text.split())
        
        # If this is a tiny chunk
        if words < 40:
            # Try to merge with the previous chunk in merged_chunks
            if merged_chunks:
                prev_h, prev_sub, prev_text = merged_chunks[-1]
                prev_ans = prev_text[prev_text.find("Answer:") + 7:].strip() if "Answer:" in prev_text else prev_text
                prev_words = len(prev_ans.split())
                
                # Check if total word count remains reasonable (< 350 words)
                if prev_words + words < 350:
                    # Merge it!
                    new_body = prev_ans + "\n\n" + answer_text
                    new_q = prev_text[:prev_text.find("Answer:")].strip()
                    merged_chunks[-1] = (prev_h, prev_sub, f"{new_q}\nAnswer: {new_body}")
                    metrics_tracker["merged"] += 1
                    i += 1
                    continue
            
            # If we couldn't merge with previous, try to merge with the next chunk
            if i + 1 < len(chunks):
                next_h, next_sub, next_text = chunks[i+1]
                next_ans = next_text[next_text.find("Answer:") + 7:].strip() if "Answer:" in next_text else next_text
                next_words = len(next_ans.split())
                
                if next_words + words < 350:
                    new_body = answer_text + "\n\n" + next_ans
                    new_q = next_text[:next_text.find("Answer:")].strip()
                    chunks[i+1] = (next_h, next_sub, f"{new_q}\nAnswer: {new_body}")
                    metrics_tracker["merged"] += 1
                    i += 1
                    continue
                    
            # If we can't merge with either, we only remove it if it is truly tiny (< 8 words)
            if words < 8:
                metrics_tracker["removed"] += 1
                i += 1
                continue
            
        merged_chunks.append((heading, subheading, text))
        i += 1
        
    return merged_chunks

def parse_markdown_file(file_path: Path) -> Tuple[Dict[str, Any], str]:
    """
    Reads markdown, extracts YAML frontmatter, and strips it from the body.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
        
    frontmatter = {}
    content = text
    
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
                content = parts[2].strip()
            except Exception as e:
                logger.warning(f"Failed to parse YAML frontmatter in {file_path}: {e}")
                
    return frontmatter, content

def get_legacy_collection(category: str) -> str:
    cat_lower = category.lower().strip()
    return LEGACY_MAPPING.get(cat_lower, "student_services")

# ----------------- Automated validation & metrics -----------------

class IngestionMetrics:
    def __init__(self):
        self.files_discovered = 0
        self.files_parsed = 0
        self.files_skipped_invalid = 0
        self.chunks_generated = 0
        self.chunks_embedded = 0
        self.chunks_skipped_duplicate = 0
        
        # Operation counts
        self.chunks_removed = 0
        self.chunks_merged = 0
        self.chunks_split = 0
        self.chunks_skipped = 0
        
        # Chunk quality categories
        self.short_chunks = 0
        self.long_chunks = 0
        self.heading_only_chunks = 0
        self.table_only_chunks = 0
        self.duplicate_chunks_count = 0
        
        self.collection_counts = {name: 0 for name in VALID_COLLECTIONS}
        self.chunk_sizes = []

def validate_chunk(chunk_text: str) -> Tuple[bool, str]:
    """
    Validates a chunk of text. Rejects chunks with low words, blank content,
    heading-only, or containing remaining UI navigation menu boilerplate.
    """
    lines = chunk_text.split("\n")
    answer_text = ""
    for line in lines:
        if line.startswith("Answer:"):
            answer_text = chunk_text[chunk_text.find("Answer:") + 7:].strip()
            break
            
    if not answer_text:
        answer_text = chunk_text
        
    words = len(answer_text.split())
    if words < 8:
        return False, f"Too short ({words} words)"
        
    raw_lines = [line.strip() for line in answer_text.split("\n") if line.strip()]
    if not raw_lines:
        return False, "Blank content"
        
    # Check heading-only
    if all(line.startswith("#") for line in raw_lines):
        return False, "Heading-only content"
        
    # Check remaining UI boilerplate keywords
    ui_keywords = [
        "Theme Color Mode", "Navigation Styles", "Vertical Horizontal", 
        "RTL LTR", "Light Dark Switcher", "Toggle theme", "Search..."
    ]
    for kw in ui_keywords:
        if kw.lower() in answer_text.lower():
            return False, f"Contains UI boilerplate: '{kw}'"
            
    # Check if only navigation options or links
    if words < 12 and all(w.istitle() or w.isupper() or w == "|" for w in answer_text.split() if w.isalnum()):
        return False, "Contains navigation options only"
        
    return True, ""

def compute_statistics(sizes: List[int]) -> Tuple[float, int, int, int, int]:
    if not sizes:
        return 0.0, 0, 0, 0, 0
    sorted_sizes = sorted(sizes)
    n = len(sorted_sizes)
    
    avg = sum(sorted_sizes) / n
    smallest = sorted_sizes[0]
    largest = sorted_sizes[-1]
    
    if n % 2 == 1:
        median = sorted_sizes[n // 2]
    else:
        median = int((sorted_sizes[n // 2 - 1] + sorted_sizes[n // 2]) / 2)
        
    idx_95 = int(0.95 * (n - 1))
    p95 = sorted_sizes[idx_95]
    
    return avg, median, p95, smallest, largest

def filter_existing_chunks(collection, batch: List[Dict[str, Any]], metrics: IngestionMetrics) -> List[Dict[str, Any]]:
    if not batch:
        return []
    
    ids = [item["id"] for item in batch]
    try:
        existing = collection.get(ids=ids, include=["metadatas"])
        existing_metas = {eid: emeta for eid, emeta in zip(existing["ids"], existing["metadatas"])}
    except Exception as e:
        logger.warning(f"Failed to fetch existing records from collection: {e}. Performing full write.")
        return batch
        
    filtered_batch = []
    for item in batch:
        cid = item["id"]
        curr_hash = item["metadata"]["content_hash"]
        if cid in existing_metas:
            ex_meta = existing_metas[cid]
            if ex_meta and ex_meta.get("content_hash") == curr_hash:
                metrics.chunks_skipped += 1
                continue
        filtered_batch.append(item)
    return filtered_batch

# ----------------- Pipeline orchestrator -----------------

def process_file_task(file_path: Path) -> Tuple[bool, List[Dict[str, Any]], str, str, Dict[str, int]]:
    """
    Threaded function to parse, clean, block, chunk and validate a single Markdown file.
    """
    ops = {"merged": 0, "split": 0, "removed": 0}
    try:
        frontmatter, content = parse_markdown_file(file_path)
    except Exception as e:
        return False, [], "PARSING_ERROR", f"Error parsing: {e}", ops
        
    raw_content_stripped = content.strip()
    if not raw_content_stripped:
        return False, [], "EMPTY_FILE", "File is empty (0 bytes or whitespace)", ops
        
    content_hash = hashlib.md5(raw_content_stripped.encode("utf-8")).hexdigest()
    is_duplicate = False
    with hashes_lock:
        if content_hash in seen_file_hashes:
            is_duplicate = True
        else:
            seen_file_hashes.add(content_hash)
            
    if is_duplicate:
        return False, [], "DUPLICATE_CONTENT", "Duplicate file content", ops
        
    cleaned_content = clean_markdown_content(content)
    cleaned_stripped = cleaned_content.strip()
    
    if not cleaned_stripped:
        content_lower = raw_content_stripped.lower()
        is_footer = "copyright" in content_lower or "rights reserved" in content_lower
        is_nav = any(kw in content_lower for kw in [
            "main menu", "toggle theme", "select language", 
            "choose a campus", "select a campus to explore",
            "browse by department", "quick filters", "popular tags"
        ])
        if is_nav:
            return False, [], "ONLY_NAVIGATION", "Content contains only navigation elements", ops
        elif is_footer:
            return False, [], "ONLY_FOOTER", "Content contains only footer elements", ops
        else:
            return False, [], "NO_SEMANTIC_CONTENT", "No semantic content left after boilerplate removal", ops
            
    # Boilerplate filters to skip pages with no semantic content
    doc_title = frontmatter.get("title") or file_path.stem.replace("_", " ").title()
    if "Let's get you registered for Admissions" in cleaned_stripped:
        if "MAT / CAT / CMAT" not in cleaned_stripped and "NEET and KCET" not in cleaned_stripped:
            return False, [], "NO_SEMANTIC_CONTENT", "Registration placeholder page with no semantic content", ops
            
    if "calendar" in str(file_path).lower() or "calendar" in doc_title.lower():
        cleaned_no_days = re.sub(r'\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', '', cleaned_stripped, flags=re.IGNORECASE)
        cleaned_no_digits = re.sub(r'\d+', '', cleaned_no_days).strip()
        if len(cleaned_no_digits.split()) < 5:
            return False, [], "NO_SEMANTIC_CONTENT", "Calendar placeholder listing with no events", ops
            
    if "maintenance" in cleaned_stripped.lower() and "inconvenience" in cleaned_stripped.lower():
        return False, [], "NO_SEMANTIC_CONTENT", "Site maintenance page placeholder", ops
        
    if "Login to Your Account" in cleaned_stripped or "Login Id/Email" in cleaned_stripped:
        if "162+ Active Clubs" not in cleaned_stripped and "Research @ PES University" not in cleaned_stripped:
            return False, [], "NO_SEMANTIC_CONTENT", "Generic login page placeholder", ops
            
    if "Index of /" in cleaned_stripped or "Parent Directory" in cleaned_stripped:
        return False, [], "NO_SEMANTIC_CONTENT", "Directory listing index page", ops
        
    if "grab the buck" in cleaned_stripped.lower() and len(cleaned_stripped.split()) < 40:
        return False, [], "NO_SEMANTIC_CONTENT", "Bug bounty placeholder page", ops
            
    words_count = len(cleaned_stripped.split())
    if words_count < 8:
        return False, [], "TOO_SHORT", f"Cleaned content too short ({words_count} words)", ops
        
    parent_dir = file_path.parent.name
    category = frontmatter.get("category") or parent_dir
    target_collection = get_legacy_collection(category)
    
    doc_title = frontmatter.get("title") or file_path.stem.replace("_", " ").title()
    source_url = frontmatter.get("url") or ""
    
    blocks = split_into_logical_blocks(cleaned_stripped)
    chunks = chunk_logical_blocks(blocks, doc_title, ops)
    
    total_chunks = len(chunks)
    slug = file_path.stem
    
    chunk_list = []
    for chunk_number, (heading, subheading, chunk_text) in enumerate(chunks, 1):
        # Validate chunk before mapping
        is_valid, reason = validate_chunk(chunk_text)
        if not is_valid:
            ops["removed"] += 1
            continue
            
        heading_clean = re.sub(r'[^a-zA-Z0-9]', '', heading.lower())[:15]
        if not heading_clean:
            heading_clean = "intro"
        heading_hash = hashlib.md5(heading.encode("utf-8")).hexdigest()[:8]
        chunk_id = f"{target_collection}_{slug}_{heading_clean}_{heading_hash}_s{chunk_number}"
        
        content_hash_val = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()
        
        metadata = {
            "title": doc_title,
            "heading": heading,
            "subheading": subheading,
            "category": category,
            "folder": parent_dir,
            "parent_folder": file_path.parent.parent.name,
            "relative_path": str(file_path.relative_to(Path("knowledge_new").parent)),
            "slug": slug,
            "document_name": file_path.name,
            "source_url": source_url,
            "chunk_number": chunk_number,
            "total_chunks": total_chunks,
            "word_count": len(chunk_text.split()),
            "character_count": len(chunk_text),
            "content_hash": content_hash_val,
            "ingestion_timestamp": str(time.time())
        }
        
        chunk_list.append({
            "id": chunk_id,
            "document": chunk_text,
            "metadata": metadata,
            "collection": target_collection
        })
        
    if not chunk_list:
        if words_count < 8:
            return False, [], "TOO_SHORT", f"Content too short to form chunks ({words_count} words)", ops
        else:
            return False, [], "NO_SEMANTIC_CONTENT", "All chunks rejected by validator (boilerplate/short)", ops
            
    return True, chunk_list, "", "", ops

# ----------------- Self-Audit & Retrieval Tester -----------------

def run_self_audit(client, emb_fn):
    logger.info("Starting Self-Audit sampling of ChromaDB chunks...")
    for col_name in VALID_COLLECTIONS:
        try:
            collection = client.get_collection(name=col_name, embedding_function=emb_fn)
            count = collection.count()
            if count == 0:
                print(f"Collection '{col_name}' is empty.")
                continue
                
            results = collection.get(limit=10)
            if results and results["ids"]:
                idx = random.randint(0, len(results["ids"]) - 1)
                cid = results["ids"][idx]
                doc = results["documents"][idx]
                meta = results["metadatas"][idx]
                print(f"\n--- Random Sample from [{col_name}] ---")
                print(f"ID: {cid}")
                print(f"Document Name: {meta.get('document_name')}")
                print(f"Heading: {meta.get('heading')}")
                print(f"Source URL: {meta.get('source_url')}")
                print(f"Word Count: {meta.get('word_count')}")
                print(f"Character Count: {meta.get('character_count')}")
                # Safe terminal print of sample content
                content_safe = doc[:150].encode('ascii', errors='replace').decode('ascii')
                print(f"Sample Content: {content_safe}...")
        except Exception as e:
            logger.error(f"Audit failed for collection '{col_name}': {e}")

def run_random_chunk_inspection(chunks: List[Dict[str, Any]], count: int = 50):
    print("\n" + "="*80)
    print("                    PROGRAMMATIC 50-CHUNK QUALITY INSPECTION")
    print("="*80)
    
    if len(chunks) < count:
        sample_chunks = chunks
    else:
        sample_chunks = random.sample(chunks, count)
        
    violations = 0
    for idx, item in enumerate(sample_chunks, 1):
        doc = item["document"]
        meta = item["metadata"]
        
        is_valid, reason = validate_chunk(doc)
        
        backtick_count = doc.count("```")
        is_broken_code = (backtick_count % 2 != 0)
        
        is_broken_table = False
        lines = [line.strip() for line in doc.split("\n") if line.strip()]
        for line in lines:
            if line.startswith("|"):
                if not line.endswith("|"):
                    is_broken_table = True
                    break
        
        error_msg = ""
        if not is_valid:
            error_msg = f"Validation fail: {reason}"
        elif is_broken_code:
            error_msg = "Broken code block (odd number of backticks)"
        elif is_broken_table:
            error_msg = "Malformed table (unclosed pipe symbol)"
            
        if error_msg:
            violations += 1
            print(f"  [VIOLATION #{violations}] File: {meta.get('relative_path')}")
            print(f"    Chunk ID: {item['id']}")
            print(f"    Issue   : {error_msg}")
            print(f"    Content snippet: {doc[:100]}...\n")
            
    if violations == 0:
        print("  => SUCCESS: Programmatic check completed. 0 quality violations found!")
    else:
        print(f"  => AUDIT FAILED: Found {violations} quality violations.")
    print("="*80)

def run_rag_retrieval_validation(client, emb_fn):
    logger.info("\n" + "="*80)
    logger.info("                    AUTOMATED END-TO-END RAG RETRIEVAL AUDIT")
    logger.info("="*80)
    
    test_queries = [
        {"q": "What documents are required for PESU Merit Quota?", "col": "admissions"},
        {"q": "What is the hostel fee?", "col": "student_services"},
        {"q": "Tell me about RR Campus bus routes.", "col": "student_services"},
        {"q": "Do I need migration certificate?", "col": "admissions"},
        {"q": "What scholarships are available?", "col": "admissions"},
        {"q": "What is the B.Tech fee?", "col": "admissions"}
    ]
    
    stop_words = {
        "what", "is", "are", "the", "for", "in", "to", "do", "how", "a", "of", "on", 
        "and", "or", "about", "with", "where", "you", "i", "can", "my", "your",
        "does", "did", "at", "by", "an", "this", "that"
    }
    
    def tokenize(text: str) -> set:
        text_norm = text.lower()
        text_norm = text_norm.replace("b.tech", "btech").replace("m.tech", "mtech")
        text_norm = text_norm.replace("b.sc", "bsc").replace("m.sc", "msc")
        text_norm = text_norm.replace("ph.d", "phd").replace("ll.m", "llm")
        words = re.findall(r'\b\w+\b', text_norm)
        tokens = set()
        for w in words:
            if w not in stop_words:
                tokens.add(w)
                if w.endswith('s') and len(w) > 3:
                    tokens.add(w[:-1])
        return tokens

    def calculate_overlap_score(query: str, question: str) -> float:
        query_tokens = tokenize(query)
        question_tokens = tokenize(question)
        if not query_tokens:
            return 0.0
        intersection = query_tokens.intersection(question_tokens)
        return len(intersection) / len(query_tokens)
        
    for test in test_queries:
        query = test["q"]
        col_name = test["col"]
        
        print(f"\nQUERY: '{query}' -> Target Collection: [{col_name}]")
        try:
            collection = client.get_collection(name=col_name, embedding_function=emb_fn)
            results = collection.query(
                query_texts=[query],
                n_results=30
            )
        except Exception as e:
            print(f"  [ERROR] Failed to query collection '{col_name}': {e}")
            continue
            
        if not results or not results.get('documents') or not results['documents'][0]:
            print("  [WARN] No documents retrieved.")
            continue
            
        docs = results['documents'][0]
        ids = results['ids'][0]
        metadatas = results['metadatas'][0]
        distances = results['distances'][0]
        
        query_norm = query.lower().replace("b.tech", "btech").replace("m.tech", "mtech").replace("b.sc", "bsc").replace("m.sc", "msc").replace("ph.d", "phd").replace("ll.m", "llm")
        query_words = [w for w in re.findall(r'\b\w+\b', query_norm) if w not in stop_words]
        
        candidates = []
        for doc, doc_id, meta, dist in zip(docs, ids, metadatas, distances):
            meta = meta if isinstance(meta, dict) else {}
            
            q_text = doc
            lines = doc.split("\n")
            for line in lines:
                if line.startswith("Question:"):
                    q_text = line[9:].strip()
                    break
                    
            heading_raw = meta.get("heading", "")
            title_raw = meta.get("title", "")
            overlap_text = f"{title_raw} {heading_raw} {q_text}"
            kw_score = calculate_overlap_score(query, overlap_text)
            
            heading = heading_raw.lower().replace("b.tech", "btech").replace("m.tech", "mtech").replace("b.sc", "bsc").replace("m.sc", "msc").replace("ph.d", "phd").replace("ll.m", "llm")
            title = title_raw.lower().replace("b.tech", "btech").replace("m.tech", "mtech").replace("b.sc", "bsc").replace("m.sc", "msc").replace("ph.d", "phd").replace("ll.m", "llm")
            category = meta.get("category", "").lower().replace("b.tech", "btech").replace("m.tech", "mtech").replace("b.sc", "bsc").replace("m.sc", "msc").replace("ph.d", "phd").replace("ll.m", "llm")
            
            heading_words = re.findall(r'\b\w+\b', heading)
            title_words = re.findall(r'\b\w+\b', title)
            category_words = re.findall(r'\b\w+\b', category)
            
            heading_boost = min(sum(0.3 for w in query_words if w in heading_words), 0.9)
            title_boost = min(sum(0.1 for w in query_words if w in title_words), 0.3)
            category_boost = min(sum(0.1 for w in query_words if w in category_words), 0.2)
            
            metadata_boost = heading_boost + title_boost + category_boost
            similarity_score = 1.0 / (1.0 + (dist if dist is not None else 0.0))
            
            combined_score = 1.0 * similarity_score + 1.5 * kw_score + metadata_boost
            
            candidates.append({
                "id": doc_id,
                "similarity_score": similarity_score,
                "keyword_score": kw_score,
                "combined_score": combined_score,
                "heading": heading_raw,
                "title": title_raw,
                "doc_name": meta.get("document_name", "")
            })
            
        candidates.sort(key=lambda x: x["combined_score"], reverse=True)
        
        seen_headings = set()
        deduplicated = []
        for cand in candidates:
            heading_key = (cand["heading"].lower(), cand["doc_name"].lower())
            if heading_key in seen_headings:
                continue
            seen_headings.add(heading_key)
            deduplicated.append(cand)
            
        print(f"  {'Rank':<4} | {'Chunk ID':<50} | {'Sim':<6} | {'KW':<6} | {'Rerank':<6}")
        print(f"  {'-'*4}+----+{'-'*50}+----+{'-'*6}+----+{'-'*6}+----+{'-'*6}")
        for rank, cand in enumerate(deduplicated[:10], 1):
            print(f"  {rank:<4} | {cand['id'][:50]:<50} | {cand['similarity_score']:.4f} | {cand['keyword_score']:.4f} | {cand['combined_score']:.4f}")
            print(f"       Heading: '{cand['heading']}' | Title: '{cand['title']}'")
            
        if deduplicated:
            selected = deduplicated[0]
            print(f"  => Selected chunk: {selected['id']}")
            print(f"  => Reason: Combined score of {selected['combined_score']:.4f} ranked #1 (Similarity={selected['similarity_score']:.4f}, Keyword={selected['keyword_score']:.4f})")
        else:
            print("  => No candidates found.")
            
    print("="*80)

# ----------------- Main script -----------------

def main():
    parser = argparse.ArgumentParser(description="Ingest PES University Markdown pages into ChromaDB.")
    parser.add_argument(
        "--db-path",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"Path to persistent ChromaDB storage (default: {DEFAULT_DB_PATH})"
    )
    parser.add_argument(
        "--knowledge-dir",
        type=str,
        default=DEFAULT_KNOWLEDGE_DIR,
        help=f"Directory containing Markdown pages (default: {DEFAULT_KNOWLEDGE_DIR})"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing collections before ingesting new data"
    )
    args = parser.parse_args()

    start_time = time.time()
    logger.info("Initializing production-grade Ingestion Pipeline...")

    # Check input knowledge directory
    source_dir = Path(args.knowledge_dir)
    if not source_dir.exists():
        logger.critical(f"Source knowledge directory not found: {source_dir.resolve()}")
        sys.exit(1)

    # Initialize client
    try:
        client = chromadb.PersistentClient(path=args.db_path)
    except Exception as e:
        logger.critical(f"Failed to connect to ChromaDB: {e}")
        sys.exit(1)

    # Initialize SentenceTransformer embedding function (all-MiniLM-L6-v2)
    logger.info("Loading SentenceTransformer embedding function (all-MiniLM-L6-v2)...")
    try:
        emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2",
            device="cpu"
        )
    except Exception as e:
        logger.critical(f"Failed to load local SentenceTransformer function: {e}")
        sys.exit(1)

    # Reset collections if requested
    if args.reset:
        logger.warning("Reset option detected. Deleting existing ChromaDB collections...")
        for col_name in VALID_COLLECTIONS:
            try:
                client.delete_collection(name=col_name)
                logger.info(f"Deleted collection '{col_name}' successfully.")
            except Exception:
                pass

    metrics = IngestionMetrics()
    
    # 1. Discover files
    md_files = list(source_dir.rglob("*.md"))
    metrics.files_discovered = len(md_files)
    logger.info(f"Discovered {metrics.files_discovered} Markdown files in '{source_dir.resolve()}' recursively.")
    
    # 2. Parallel processing of files
    chunks_to_ingest = []
    skipped_files_details = []
    
    logger.info("Parsing markdown files and extracting chunks...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_file_task, f): f for f in md_files}
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Parsing Files"):
            file_path = futures[future]
            try:
                success, chunk_list, reason_code, reason_detail, ops = future.result()
                metrics.chunks_merged += ops["merged"]
                metrics.chunks_split += ops["split"]
                metrics.chunks_removed += ops["removed"]
                
                if success:
                    metrics.files_parsed += 1
                    chunks_to_ingest.extend(chunk_list)
                else:
                    metrics.files_skipped_invalid += 1
                    skipped_files_details.append({
                        "file_path": file_path,
                        "reason_code": reason_code,
                        "reason_detail": reason_detail
                    })
                    logger.warning(f"File skipped [{file_path}]: {reason_code} - {reason_detail}")
            except Exception as e:
                metrics.files_skipped_invalid += 1
                skipped_files_details.append({
                    "file_path": file_path,
                    "reason_code": "OTHER",
                    "reason_detail": f"Uncaught exception: {e}"
                })
                logger.error(f"Failed processing file [{file_path}]: {e}")
                
    metrics.chunks_generated = len(chunks_to_ingest)
    logger.info(f"Successfully chunked {metrics.files_parsed}/{metrics.files_discovered} files into {metrics.chunks_generated} chunks.")

    # 3. Group chunks by target collection
    collection_batches: Dict[str, List[Dict[str, Any]]] = {name: [] for name in VALID_COLLECTIONS}
    seen_hashes = set()
    
    for item in chunks_to_ingest:
        col = item["collection"]
        chash = item["metadata"]["content_hash"]
        
        # Check duplicate hashes in memory
        if chash in seen_hashes:
            metrics.duplicate_chunks_count += 1
            metrics.chunks_removed += 1
            continue
            
        seen_hashes.add(chash)
        collection_batches[col].append(item)
        
        # Record sizes for validation statistics
        answer_text = item["document"]
        if "Answer:" in item["document"]:
            answer_text = item["document"][item["document"].find("Answer:") + 7:].strip()
        metrics.chunk_sizes.append(len(answer_text.split()))

    # 4. Ingest Chunks in Batches
    summary_report = []
    
    for col_name, batch in collection_batches.items():
        try:
            collection = client.get_or_create_collection(
                name=col_name,
                embedding_function=emb_fn
            )
        except Exception as e:
            logger.error(f"Failed to load collection '{col_name}': {e}")
            metrics.chunks_skipped += len(batch)
            summary_report.append({
                "collection": col_name,
                "ingested": 0,
                "skipped": len(batch),
                "failures": len(batch),
                "total_in_db": 0
            })
            continue
            
        # Incremental filter
        filtered_batch = filter_existing_chunks(collection, batch, metrics)
        
        ingested_count = 0
        failed_count = 0
        
        sub_batch_size = 100
        for i in range(0, len(filtered_batch), sub_batch_size):
            sub_batch = filtered_batch[i:i+sub_batch_size]
            sub_ids = [s["id"] for s in sub_batch]
            sub_docs = [s["document"] for s in sub_batch]
            sub_metas = [s["metadata"] for s in sub_batch]
            
            try:
                collection.upsert(
                    ids=sub_ids,
                    documents=sub_docs,
                    metadatas=sub_metas
                )
                ingested_count += len(sub_batch)
                metrics.collection_counts[col_name] += len(sub_batch)
            except Exception as e:
                logger.error(f"Upsert failed in collection '{col_name}': {e}")
                failed_count += len(sub_batch)
                
        metrics.chunks_embedded += ingested_count
        db_count = 0
        try:
            db_count = collection.count()
        except Exception:
            pass
            
        summary_report.append({
            "collection": col_name,
            "ingested": ingested_count,
            "skipped": len(batch) - len(filtered_batch),
            "failures": failed_count,
            "total_in_db": db_count
        })

    duration = time.time() - start_time
    avg_size, median_size, p95_size, smallest_size, largest_size = compute_statistics(metrics.chunk_sizes)

    # Output Summary Report
    print("\n" + "="*80)
    print("                     MARKDOWN PIPELINE INGESTION REPORT")
    print("="*80)
    print(f"ChromaDB Persistent Path: {os.path.abspath(args.db_path)}")
    print(f"Source Markdown Folder  : {source_dir.resolve()}")
    print(f"Time Taken              : {duration:.2f} seconds")
    print(f"Total Files Discovered  : {metrics.files_discovered}")
    print(f"Total Files Ingested    : {metrics.files_parsed}")
    print(f"Total Files Skipped     : {metrics.files_skipped_invalid}")
    print(f"Total Chunks Generated  : {metrics.chunks_generated}")
    print(f"Total Chunks Embedded   : {metrics.chunks_embedded}")
    print(f"Chunks Incremental Skip : {metrics.chunks_skipped} (Hash match)")
    print(f"Duplicate Chunks Skipped: {metrics.duplicate_chunks_count} (In-memory match)")
    print("-"*80)
    print(f"{'Legacy Collection':<18} | {'Ingested':<9} | {'Skipped':<9} | {'Failed':<6} | {'Total Docs in DB':<16}")
    print("-"*80)
    for row in summary_report:
        print(f"{row['collection']:<18} | {row['ingested']:<9} | {row['skipped']:<9} | {row['failures']:<6} | {row['total_in_db']:<16}")
    print("-"*80)
    print(f"Average Chunk Size      : {avg_size:.1f} words  (Target: 220–280 words)")
    print(f"Median Chunk Size       : {median_size} words")
    print(f"95th Percentile Size    : {p95_size} words")
    print(f"Largest Chunk Size      : {largest_size} words   (Target: <350 words)")
    print(f"Smallest Chunk Size     : {smallest_size} words   (Target: >40 words)")
    print("-"*80)
    print(f"Pipeline Quality Stats  : Chunks Split   : {metrics.chunks_split}")
    print(f"                          Chunks Merged  : {metrics.chunks_merged}")
    print(f"                          Chunks Removed : {metrics.chunks_removed}")
    print("="*80)

    # Skipped file audit report
    if skipped_files_details:
        print("\n" + "="*80)
        print("                           SKIPPED FILE AUDIT REPORT")
        print("="*80)
        for idx, item in enumerate(skipped_files_details, 1):
            fpath = item["file_path"]
            rel_path = str(fpath.relative_to(source_dir.parent))
            print(f"File #{idx}:")
            print(f"- filename     : {fpath.name}")
            print(f"- relative path: {rel_path.replace(chr(92), '/')}")
            print(f"- reason skipped: {item['reason_code']}")
            print()
            
        print("-"*80)
        print("SKIPPED FILE SUMMARY:")
        print("-"*80)
        counts = {
            "EMPTY_FILE": 0,
            "DUPLICATE": 0,
            "TOO_SHORT": 0,
            "ONLY_NAVIGATION": 0,
            "PARSING_ERROR": 0,
            "OTHER": 0
        }
        for item in skipped_files_details:
            code = item["reason_code"]
            if code == "EMPTY_FILE":
                counts["EMPTY_FILE"] += 1
            elif code == "DUPLICATE_CONTENT":
                counts["DUPLICATE"] += 1
            elif code == "TOO_SHORT":
                counts["TOO_SHORT"] += 1
            elif code in ("ONLY_NAVIGATION", "ONLY_FOOTER", "NO_SEMANTIC_CONTENT"):
                counts["ONLY_NAVIGATION"] += 1
            elif code in ("PARSING_ERROR", "INVALID_MARKDOWN"):
                counts["PARSING_ERROR"] += 1
            else:
                counts["OTHER"] += 1
                
        print("EMPTY_FILE .......... " + str(counts["EMPTY_FILE"]))
        print("DUPLICATE ........... " + str(counts["DUPLICATE"]))
        print("TOO_SHORT ........... " + str(counts["TOO_SHORT"]))
        print("ONLY_NAVIGATION ..... " + str(counts["ONLY_NAVIGATION"]))
        print("PARSING_ERROR ....... " + str(counts["PARSING_ERROR"]))
        print("OTHER ............... " + str(counts["OTHER"]))
        print("="*80)

    empty_count = sum(1 for item in skipped_files_details if item["reason_code"] == "EMPTY_FILE")
    nav_count = sum(1 for item in skipped_files_details if item["reason_code"] in ("ONLY_NAVIGATION", "ONLY_FOOTER", "NO_SEMANTIC_CONTENT"))
    dup_count = sum(1 for item in skipped_files_details if item["reason_code"] == "DUPLICATE_CONTENT")
    
    print("\n" + "="*80)
    print("                     FINAL FILE INGESTION DISTINCTIONS")
    print("="*80)
    print(f"Discovered files          : {metrics.files_discovered}")
    print(f"Useful files              : {metrics.files_parsed}")
    print(f"Empty files               : {empty_count}")
    print(f"Navigation-only files     : {nav_count}")
    print(f"Duplicate files           : {dup_count}")
    print(f"Successfully ingested files: {metrics.files_parsed}")
    print("="*80)

    # 5. Programmatic random inspection of 50 chunks
    run_random_chunk_inspection(chunks_to_ingest, 50)

    # 6. Run Self-Audit Sampling
    run_self_audit(client, emb_fn)

    # 7. Run Automated End-to-End RAG Retrieval Audit
    run_rag_retrieval_validation(client, emb_fn)

if __name__ == "__main__":
    main()
