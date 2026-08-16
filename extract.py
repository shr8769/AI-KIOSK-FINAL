with open('c:/AI-KIOSK/knowledge_new/faqs/faqs.md', 'r', encoding='utf-8') as f:
    lines = f.readlines()

header = [
    "---\n",
    "title: \"Academics FAQ\"\n",
    "category: academics\n",
    "---\n\n"
]

with open('c:/AI-KIOSK/knowledge_new/programs/academics_faq.md', 'w', encoding='utf-8') as f:
    f.writelines(header + lines[122:242])
