import os
import json
import time
import logging
from typing import List, Dict, Any
from google import genai

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
SEED_PATH = os.path.join(DATASETS_DIR, "seed_queries.json")
AMBIGUOUS_PATH = os.path.join(DATASETS_DIR, "ambiguous_queries.json")
KANNADA_PATH = os.path.join(DATASETS_DIR, "kannada_queries.json")
HINDI_PATH = os.path.join(DATASETS_DIR, "hindi_queries.json")

# Initialize Gemini Client
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    # Try loading from .env file manually
    env_path = os.path.abspath(os.path.join(BASE_DIR, "..", ".env"))
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment or .env file.")

client = genai.Client(api_key=api_key)

def load_queries():
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        seed = json.load(f)
    with open(AMBIGUOUS_PATH, "r", encoding="utf-8") as f:
        ambiguous = json.load(f)
    return seed, ambiguous

def select_queries(seed: List[Dict[str, str]], ambiguous: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    # Organize seed queries by domain
    seed_by_domain = {}
    for item in seed:
        dom = item["domain"]
        if dom not in seed_by_domain:
            seed_by_domain[dom] = []
        seed_by_domain[dom].append(item["query"])

    # Organize ambiguous queries by domain
    amb_by_domain = {}
    for item in ambiguous:
        dom = item["domain"]
        if dom not in amb_by_domain:
            amb_by_domain[dom] = []
        amb_by_domain[dom].append(item["query"])

    domains = ["admissions", "academics", "placements", "research", "student_services", "navigation"]
    selected = []

    # Target counts per domain: admissions(17), academics(17), placements(17), research(17), student_services(16), navigation(16)
    target_counts = {
        "admissions": 17,
        "academics": 17,
        "placements": 17,
        "research": 17,
        "student_services": 16,
        "navigation": 16
    }

    # For each domain, select queries representing different difficulty levels
    # Simple (3), Medium (3), Complex (3), Conversational (4 or 5), Ambiguous (3)
    for dom in domains:
        target = target_counts[dom]
        seed_qs = seed_by_domain.get(dom, [])
        amb_qs = amb_by_domain.get(dom, [])

        dom_selected = []
        
        # Ambiguous (3 queries)
        for i in range(min(3, len(amb_qs))):
            dom_selected.append({"query": amb_qs[i], "domain": dom, "difficulty": "ambiguous"})

        # Simple (3 queries from early seed)
        for i in range(min(3, len(seed_qs))):
            dom_selected.append({"query": seed_qs[i], "domain": dom, "difficulty": "simple"})

        # Medium (3 queries from early-mid seed)
        start_idx = 3
        for i in range(min(3, len(seed_qs) - start_idx)):
            dom_selected.append({"query": seed_qs[start_idx + i], "domain": dom, "difficulty": "medium"})

        # Complex (3 queries from mid seed)
        start_idx = 6
        for i in range(min(3, len(seed_qs) - start_idx)):
            dom_selected.append({"query": seed_qs[start_idx + i], "domain": dom, "difficulty": "complex"})

        # Conversational (remaining target, from index 10+ which are conversational)
        start_idx = 10
        needed = target - len(dom_selected)
        for i in range(min(needed, len(seed_qs) - start_idx)):
            dom_selected.append({"query": seed_qs[start_idx + i], "domain": dom, "difficulty": "conversational"})
            
        # If still needed (fallback check)
        while len(dom_selected) < target and len(seed_qs) > len(dom_selected):
            for q in seed_qs:
                if q not in [x["query"] for x in dom_selected]:
                    dom_selected.append({"query": q, "domain": dom, "difficulty": "conversational"})
                    break

        selected.extend(dom_selected[:target])

    return selected

def translate_batch(queries: List[str], target_lang: str) -> List[str]:
    lang_name = "Kannada" if target_lang == "kn" else "Hindi"
    prompt = f"""You are a translation assistant for a university information kiosk.
Translate the following list of student queries into natural, conversational, and accurate {lang_name}.
Ensure university terminology (like CGPA, SGPA, placement, hostel, library, etc.) is translated in a way that local students would naturally speak it.

Input Queries (JSON list of strings):
{json.dumps(queries, indent=2, ensure_ascii=False)}

Return your response strictly as a JSON array of translated strings in the same order. Do not wrap the JSON in ```json markdown or include any explanations.
Example output format:
[
  "translation 1",
  "translation 2"
]
"""
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                }
            )
            result = json.loads(response.text.strip())
            if isinstance(result, list) and len(result) == len(queries):
                return result
            else:
                logger.warning(f"Response list size mismatch. Expected {len(queries)}, got {len(result)}. Retrying...")
        except Exception as e:
            logger.error(f"Error translating batch to {target_lang} (attempt {attempt+1}): {e}")
            time.sleep(5)
            
    # Fallback to copy original if all retries fail
    return queries

def main():
    logger.info("Loading seed and ambiguous queries...")
    seed, ambiguous = load_queries()
    
    logger.info("Selecting 100 representative queries...")
    selected_queries = select_queries(seed, ambiguous)
    logger.info(f"Selected {len(selected_queries)} queries.")

    kannada_queries = []
    hindi_queries = []

    # Batch queries in chunks of 10
    batch_size = 10
    total_batches = (len(selected_queries) + batch_size - 1) // batch_size
    
    logger.info(f"Translating in {total_batches} batches...")
    
    for b in range(total_batches):
        start_idx = b * batch_size
        end_idx = min(start_idx + batch_size, len(selected_queries))
        batch_items = selected_queries[start_idx:end_idx]
        batch_texts = [item["query"] for item in batch_items]
        
        logger.info(f"Processing batch {b+1}/{total_batches} (items {start_idx+1} to {end_idx})...")
        
        # Translate to Kannada
        logger.info(f"Translating batch {b+1} to Kannada...")
        kn_translations = translate_batch(batch_texts, "kn")
        
        # Translate to Hindi
        logger.info(f"Translating batch {b+1} to Hindi...")
        hi_translations = translate_batch(batch_texts, "hi")
        
        for idx, item in enumerate(batch_items):
            kannada_queries.append({
                "query": kn_translations[idx] if idx < len(kn_translations) else item["query"],
                "domain": item["domain"],
                "difficulty": item["difficulty"],
                "english_original": item["query"]
            })
            hindi_queries.append({
                "query": hi_translations[idx] if idx < len(hi_translations) else item["query"],
                "domain": item["domain"],
                "difficulty": item["difficulty"],
                "english_original": item["query"]
            })
            
        time.sleep(3.0)  # Moderate sleep to avoid Rate Limits

    # Ensure output directories exist
    os.makedirs(DATASETS_DIR, exist_ok=True)
    
    # Save files
    with open(KANNADA_PATH, "w", encoding="utf-8") as f:
        json.dump(kannada_queries, f, indent=4, ensure_ascii=False)
    logger.info(f"Saved Kannada queries to {KANNADA_PATH}")

    with open(HINDI_PATH, "w", encoding="utf-8") as f:
        json.dump(hindi_queries, f, indent=4, ensure_ascii=False)
    logger.info(f"Saved Hindi queries to {HINDI_PATH}")

if __name__ == "__main__":
    main()
