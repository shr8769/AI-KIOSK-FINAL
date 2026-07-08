import asyncio
import sys
import os

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from app.services.query_pipeline import run_query_pipeline
from app.services.speech.translation_service import preprocess_and_detect_language

async def test():
    test_queries = [
        "Physics lab ellide?",
        "Microsoft company eligibility padeyalu eshtu CGPA beku?",
        "admission office kaha hai?",
        "attendance requirements kya hai?"
    ]
    
    output = ["=== VERIFYING ROMANIZED LANG DETECTION & TRANSLATION ==="]
    for q in test_queries:
        preprocessed, lang = preprocess_and_detect_language(q)
        output.append(f"\nOriginal: '{q}'")
        output.append(f"  Detected Lang : {lang}")
        output.append(f"  Preprocessed  : '{preprocessed}'")
        
        try:
            result = await run_query_pipeline(
                session_id="demo_session_id",
                text=q,
                language_hint=None
            )
            output.append(f"  Result Type   : {result.get('type')}")
            output.append(f"  Result Lang   : {result.get('language')}")
            output.append(f"  Result Text   : {result.get('text')}")
            if result.get("navigation"):
                output.append(f"  Navigation    : {result.get('navigation')}")
        except Exception as e:
            output.append(f"  Pipeline Exec Failed: {e}")
            
    with open("verify_results.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    print("Done! Output written to verify_results.txt")

if __name__ == "__main__":
    asyncio.run(test())
