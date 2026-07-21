import os
import sys
import unittest

# Append workspace root to path for loading ingest_markdown
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from ingest_markdown import split_markdown_into_sections, chunk_markdown

class TestMarkdownIngestPipeline(unittest.TestCase):
    
    def test_split_headings_into_sections(self):
        """
        Verify that every H1-H4 heading starts its own logical section.
        """
        markdown = """# Admissions
This is general admissions intro.

## Eligibility
Detailed eligibility parameters go here.

### B.Tech Criteria
Physics, Math, and Chemistry 60%.

#### General FAQ
FAQs for admissions.
"""
        sections = split_markdown_into_sections(markdown)
        
        # We expect 4 sections: Admissions, Eligibility, B.Tech Criteria, General FAQ
        self.assertEqual(len(sections), 4)
        
        self.assertEqual(sections[0][0], "Admissions")
        self.assertIn("This is general admissions intro.", sections[0][1])
        
        self.assertEqual(sections[1][0], "Eligibility")
        self.assertIn("Detailed eligibility parameters go here.", sections[1][1])
        
        self.assertEqual(sections[2][0], "B.Tech Criteria")
        self.assertIn("Physics, Math, and Chemistry 60%.", sections[2][1])
        
        self.assertEqual(sections[3][0], "General FAQ")
        self.assertIn("FAQs for admissions.", sections[3][1])

    def test_small_section_remains_single_chunk(self):
        """
        Verify that a section with word count <= 500 is not split.
        """
        text = "This is a short section. It should remain as one single chunk."
        chunks = chunk_markdown(text, chunk_size=500, overlap=100)
        
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_large_section_split_with_overlap(self):
        """
        Verify that a section with word count > 500 is split correctly with overlap.
        """
        # Create a document of 600 words: 12 paragraphs of 50 words each
        para_words = ["word"] * 50
        paragraph_text = " ".join(para_words)
        
        # Join 12 paragraphs with paragraph breaks
        large_text = "\n\n".join([f"Paragraph {i}: " + paragraph_text for i in range(1, 13)])
        
        # Word count is roughly 600+ words
        self.assertGreater(len(large_text.split()), 500)
        
        chunks = chunk_markdown(large_text, chunk_size=500, overlap=100)
        
        # Should split into 2 chunks because 600 > 500
        self.assertEqual(len(chunks), 2)
        
        # First chunk should contain early paragraphs, second chunk should contain final paragraphs
        self.assertIn("Paragraph 1:", chunks[0])
        self.assertIn("Paragraph 12:", chunks[1])
        
        # Test that there is overlap: some paragraphs from the first chunk are carried over
        # Since overlap is 100 words, and each paragraph is ~50 words, we expect ~2 paragraphs overlap
        self.assertIn("Paragraph 9:", chunks[0])
        self.assertIn("Paragraph 9:", chunks[1])

if __name__ == "__main__":
    unittest.main()
