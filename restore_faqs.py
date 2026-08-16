import json
import os

with open('knowledge/faq.json', 'r', encoding='utf-8') as f:
    faqs = json.load(f)

markdown_content = "# Frequently Asked Questions\n\n"

for faq in faqs:
    q = faq.get('question', '')
    a = faq.get('answer', '')
    markdown_content += f"#### {q}\n\n{a}\n\n"

with open('knowledge_new/faqs/faqs.md', 'w', encoding='utf-8') as f:
    f.write(markdown_content)

print("faqs.md has been regenerated from faq.json!")
