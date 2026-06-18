# check_unicode.py
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

kws = ["ಪ್ರವೇಶ", "ಅಡ್ಮಿಷನ್", "ಅರ್ಜಿ", "ಸೀಟು", "ನೋಂದಣಿ", "ಅರ್ಹತೆ"]

output = []
for kw in kws:
    output.append(f"Keyword: {kw}")
    output.append(f"  Unicode: {[hex(ord(c)) for c in kw]}")

# Test some variations
test_queries = [
    "ವಿಶ್ವವಿದ್ಯಾಲಯದಲ್ಲಿ ಪ್ರವೇಶಾತಿ ಹೇಗಿದೆ?",
    "ಪ್ರವೇಶಾತಿ ವಿಧಾನ ಏನು?",
    "ವಿಶ್ವವಿದ್ಯಾಲಯದಲ್ಲಿ ಪ್ರವೇಶ ಹೇಗೆ?"
]

output.append("\n=== Substring matching tests ===")
for q in test_queries:
    output.append(f"Query: {q}")
    output.append(f"  Unicode: {[hex(ord(c)) for c in q]}")
    for kw in kws:
        match = kw in q
        output.append(f"  Contains '{kw}': {match}")

with open("scratch_unicode_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))
print("Done!")
