import os
import sys

try:
    import google.generativeai as genai
except ImportError:
    print("Missing SDK. Run: pip install google-generativeai --break-system-packages")
    sys.exit(1)

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("GEMINI_API_KEY not set in environment. Export it first:")
    print('  export GEMINI_API_KEY="your-key-here"')
    sys.exit(1)

genai.configure(api_key=API_KEY)

PINNED_MODEL = "gemini-1.5-flash-002"  # <-- change this if you re-pin

print("=" * 60)
print("STEP 1: SDK version check")
print("=" * 60)
print(f"google-generativeai version: {genai.__version__ if hasattr(genai, '__version__') else 'unknown'}")

print()
print("=" * 60)
print("STEP 2: Models actually available to YOUR key right now")
print("=" * 60)
available = []
try:
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            available.append(m.name)
            print(f"  OK  {m.name}")
except Exception as e:
    print(f"  FAILED to list models: {type(e).__name__}: {e}")
    sys.exit(1)

print()
print("=" * 60)
print(f"STEP 3: Testing your pinned model: {PINNED_MODEL}")
print("=" * 60)

pinned_full_name = f"models/{PINNED_MODEL}"
if pinned_full_name not in available and PINNED_MODEL not in [a.split("/")[-1] for a in available]:
    print(f"  ⚠️  '{PINNED_MODEL}' is NOT in your available models list.")
    print(f"      This model is likely deprecated/retired for your key.")
    print(f"      Any call to it is probably throwing, and if your code catches")
    print(f"      that exception broadly, it's silently falling back to Qwen")
    print(f"      every single time -- which would explain latency + inconsistent quality.")
else:
    try:
        model = genai.GenerativeModel(PINNED_MODEL)
        response = model.generate_content("Reply with exactly: OK")
        print(f"  Response: {response.text.strip()}")
        print("  PINNED MODEL IS WORKING.")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        print(f"  This confirms calls to {PINNED_MODEL} are erroring out.")

print()
print("=" * 60)
print("STEP 4: Recommended replacement (current, free-tier eligible)")
print("=" * 60)
candidates = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash", "gemini-3.1-flash-lite"]
for c in candidates:
    full = f"models/{c}"
    if full in available:
        try:
            model = genai.GenerativeModel(c)
            resp = model.generate_content("Reply with exactly: OK")
            print(f"  {c}: WORKS -> '{resp.text.strip()}'")
        except Exception as e:
            print(f"  {c}: listed but failed -> {type(e).__name__}: {e}")
    else:
        print(f"  {c}: not available to this key")

print()
print("Done. Use whichever model above printed 'WORKS' as your new pin.")
