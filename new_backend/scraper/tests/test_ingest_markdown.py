import os
import sys
import unittest

# Append workspace root to path for loading ingest_markdown
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from ingest_markdown import split_into_logical_blocks, chunk_logical_blocks

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
        blocks = split_into_logical_blocks(markdown, "fake_url")
        
        # We expect 4 sections: Admissions, Eligibility, B.Tech Criteria, General FAQ
        self.assertEqual(len(blocks), 4)
        
        self.assertEqual(blocks[0].heading_text, "Admissions")
        self.assertIn("This is general admissions intro.", blocks[0].content)
        
        self.assertEqual(blocks[1].heading_text, "Eligibility")
        self.assertIn("Detailed eligibility parameters go here.", blocks[1].content)
        
        self.assertEqual(blocks[2].heading_text, "B.Tech Criteria")
        self.assertIn("Physics, Math, and Chemistry 60%.", blocks[2].content)
        
        self.assertEqual(blocks[3].heading_text, "General FAQ")
        self.assertIn("FAQs for admissions.", blocks[3].content)

    def test_small_section_remains_single_chunk(self):
        """
        Verify that a section with word count <= 500 is not split.
        """
        text = "This is a short section. It should remain as one single chunk."
        blocks = split_into_logical_blocks(text, "fake_url")
        chunks = chunk_logical_blocks(blocks, chunk_size=500, overlap=100)
        
        self.assertEqual(len(chunks), 1)
        self.assertIn(text, chunks[0].text)

    def test_large_section_split_with_overlap(self):
        """
        Verify that a section with word count > 500 is split correctly with overlap.
        """
        para_words = ["word"] * 50
        paragraph_text = " ".join(para_words)
        
        large_text = "\n\n".join([f"Paragraph {i}: " + paragraph_text for i in range(1, 13)])
        
        blocks = split_into_logical_blocks(large_text, "fake_url")
        chunks = chunk_logical_blocks(blocks, chunk_size=500, overlap=100)
        
        # Should split into 2 chunks
        self.assertEqual(len(chunks), 2)
        
        self.assertIn("Paragraph 1:", chunks[0].text)
        self.assertIn("Paragraph 12:", chunks[1].text)
        
        # Overlap test
        self.assertIn("Paragraph 9:", chunks[0].text)
        self.assertIn("Paragraph 9:", chunks[1].text)

if __name__ == "__main__":
    unittest.main()
