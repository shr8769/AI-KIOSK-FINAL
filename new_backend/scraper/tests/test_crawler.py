import unittest
from new_backend.scraper.crawler import PESCrawler

class TestPESCrawler(unittest.TestCase):
    def setUp(self):
        # Initialize crawler with low limits for testing
        self.crawler = PESCrawler(max_pages=2, max_depth=1)

    def test_url_normalization(self):
        url1 = "HTTPS://PES.EDU/admissions/eligibility/"
        url2 = "https://pes.edu/admissions/eligibility#fragment"
        self.assertEqual(self.crawler._normalize_url(url1), "https://pes.edu/admissions/eligibility")
        self.assertEqual(self.crawler._normalize_url(url2), "https://pes.edu/admissions/eligibility")

    def test_is_same_domain(self):
        self.assertTrue(self.crawler._is_same_domain("https://pes.edu/admissions"))
        self.assertTrue(self.crawler._is_same_domain("https://www.pes.edu/placements"))
        self.assertFalse(self.crawler._is_same_domain("https://google.com"))
        self.assertFalse(self.crawler._is_same_domain("https://cetonline.karnataka.gov.in/kea/"))

    def test_ignored_patterns(self):
        # Ignored paths
        self.assertTrue(self.crawler._check_ignored_patterns("https://pes.edu/faculty-members")[0])
        self.assertTrue(self.crawler._check_ignored_patterns("https://pes.edu/research/projects")[0])
        self.assertTrue(self.crawler._check_ignored_patterns("https://pes.edu/careers/jobs")[0])
        self.assertTrue(self.crawler._check_ignored_patterns("https://pes.edu/assets/document.pdf")[0])
        
        # Valid paths
        self.assertFalse(self.crawler._check_ignored_patterns("https://pes.edu/admissions/eligibility")[0])
        self.assertFalse(self.crawler._check_ignored_patterns("https://pes.edu/placements/recruiters")[0])

    def test_news_older_than_one_year(self):
        # Current year is 2026, news older than 1 year (< 2025) is ignored
        self.assertTrue(self.crawler._check_ignored_patterns("https://pes.edu/news/2023/annual-fest")[0])
        self.assertTrue(self.crawler._check_ignored_patterns("https://pes.edu/news/2024/placement-record")[0])
        self.assertFalse(self.crawler._check_ignored_patterns("https://pes.edu/news/2025/admission-start")[0])
        self.assertFalse(self.crawler._check_ignored_patterns("https://pes.edu/news/2026/convocation")[0])

    def test_url_categorization(self):
        self.assertEqual(self.crawler.get_url_category("https://pes.edu/admissions/btech"), "admissions")
        self.assertEqual(self.crawler.get_url_category("https://pes.edu/placement-statistics"), "placements")
        self.assertEqual(self.crawler.get_url_category("https://pes.edu/departments/cse"), "departments")
        self.assertEqual(self.crawler.get_url_category("https://pes.edu/hostels/rules"), "hostels")
        self.assertEqual(self.crawler.get_url_category("https://pes.edu/scholarships/mrd"), "scholarships")
        self.assertEqual(self.crawler.get_url_category("https://pes.edu/"), "general")
        self.assertIsNone(self.crawler.get_url_category("https://pes.edu/some-unknown-random-path"))

if __name__ == "__main__":
    unittest.main()
