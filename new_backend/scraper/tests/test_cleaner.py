import unittest
from bs4 import BeautifulSoup
from new_backend.scraper.cleaner import HTMLCleaner

class TestHTMLCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = HTMLCleaner()

    def test_clean_tags_removed(self):
        html = "<html><body><header>Header Text</header><nav>Navigation</nav><main><p>Important Content</p></main><footer>Footer Text</footer></body></html>"
        soup = self.cleaner.clean_html(html)
        
        self.assertIsNone(soup.find("header"))
        self.assertIsNone(soup.find("nav"))
        self.assertIsNone(soup.find("footer"))
        self.assertIsNotNone(soup.find("p"))

    def test_clean_classes_ids_removed(self):
        html = """
        <html>
            <body>
                <div class="sidebar-wrapper">Sidebar Content</div>
                <div id="navigation-menu">Menu</div>
                <div class="main-content">
                    <p>Keep this text.</p>
                </div>
            </body>
        </html>
        """
        soup = self.cleaner.clean_html(html)
        text = soup.get_text()
        self.assertNotIn("Sidebar Content", text)
        self.assertNotIn("Menu", text)
        self.assertIn("Keep this text", text)

    def test_markdown_conversion(self):
        html = """
        <h1>Main Heading</h1>
        <p>This is a paragraph with <strong>bold</strong> and <em>italic</em> text.</p>
        <ul>
            <li>List Item 1</li>
            <li>List Item 2</li>
        </ul>
        """
        markdown, _ = self.cleaner.clean(html, "https://pes.edu/")
        
        self.assertIn("# Main Heading", markdown)
        self.assertIn("**bold**", markdown)
        self.assertIn("*italic*", markdown)
        self.assertIn("- List Item 1", markdown)
        self.assertIn("- List Item 2", markdown)

    def test_duplicate_line_removal(self):
        markdown_with_dups = """
        # Heading
        This is a unique line.
        This is a duplicate line that is very long and repeated.
        This is a duplicate line that is very long and repeated.
        Another unique line.
        """
        cleaned, stats = self.cleaner.remove_duplicate_lines(markdown_with_dups)
        
        self.assertEqual(stats["duplicates_removed"], 1)
        self.assertIn("This is a duplicate line that is very long and repeated.", cleaned)
        # Ensure it only occurs once
        self.assertEqual(cleaned.count("This is a duplicate line that is very long and repeated."), 1)

    def test_table_markdown(self):
        html = """
        <table>
            <tr><th>Header 1</th><th>Header 2</th></tr>
            <tr><td>Cell 1a</td><td>Cell 1b</td></tr>
        </table>
        """
        markdown, _ = self.cleaner.clean(html, "https://pes.edu/")
        self.assertIn("| Header 1 | Header 2 |", markdown)
        self.assertIn("| --- | --- |", markdown)
        self.assertIn("| Cell 1a | Cell 1b |", markdown)

if __name__ == "__main__":
    unittest.main()
