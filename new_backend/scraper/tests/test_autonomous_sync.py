import os
import sys
import unittest
import tempfile
import json
import hashlib
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

# Ensure paths are set up correctly
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from new_backend.scraper.autonomous_sync import (
    calculate_hash, load_tracker, save_tracker, check_url_headers, run_sync_cycle
)
from new_backend.scraper.incremental_ingester import ingest_single_file, delete_single_file_chunks

class TestAutonomousSync(unittest.TestCase):

    def setUp(self):
        # Create temporary tracker path
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tracker_path = os.path.join(self.temp_dir.name, "crawler_tracker.json")
        self.knowledge_dir = os.path.join(self.temp_dir.name, "knowledge_new")
        
        # Patch config values
        self.config_patches = {
            "TRACKER_FILE_PATH": patch("new_backend.scraper.autonomous_sync.TRACKER_FILE_PATH", self.tracker_path),
            "KNOWLEDGE_NEW_DIR": patch("new_backend.scraper.autonomous_sync.KNOWLEDGE_NEW_DIR", self.knowledge_dir),
            "TARGET_URLS": patch("new_backend.scraper.autonomous_sync.TARGET_URLS", ["https://pes.edu/admissions/"]),
        }
        for name, p in self.config_patches.items():
            p.start()

    def tearDown(self):
        for p in self.config_patches.values():
            p.stop()
        self.temp_dir.cleanup()

    def test_calculate_hash(self):
        text = "Hello PES University"
        expected = hashlib.md5(text.encode("utf-8")).hexdigest()
        self.assertEqual(calculate_hash(text), expected)

    def test_load_save_tracker(self):
        tracker_data = {
            "https://pes.edu/admissions/": {
                "content_hash": "abc123hash",
                "last_modified": "Mon, 20 Jul 2026 12:00:00 GMT"
            }
        }
        save_tracker(tracker_data)
        loaded = load_tracker()
        self.assertEqual(loaded, tracker_data)

    @patch("requests.get")
    def test_check_url_headers_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {
            "Last-Modified": "Mon, 20 Jul 2026 12:00:00 GMT",
            "ETag": "w/\"etag12345\""
        }
        mock_get.return_value = mock_resp

        success, last_mod, etag, resp = check_url_headers("https://pes.edu/admissions/")
        self.assertTrue(success)
        self.assertEqual(last_mod, "Mon, 20 Jul 2026 12:00:00 GMT")
        self.assertEqual(etag, "w/\"etag12345\"")

    @patch("requests.get")
    def test_check_url_headers_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        success, last_mod, etag, resp = check_url_headers("https://pes.edu/admissions/")
        self.assertFalse(success)
        self.assertEqual(resp.status_code, 404)

    @patch("new_backend.scraper.autonomous_sync.ingest_single_file")
    @patch("new_backend.scraper.autonomous_sync.check_url_headers")
    @patch("new_backend.scraper.autonomous_sync.PESCrawler")
    def test_run_sync_cycle_no_change_headers(self, mock_crawler_class, mock_check_headers, mock_ingest):
        # 1. Setup mock headers that MATCH the tracker data
        mock_check_headers.return_value = (True, "Mon, 20 Jul 2026 12:00:00 GMT", "etag123", MagicMock(status_code=200))
        
        # Seed tracker
        tracker_data = {
            "https://pes.edu/admissions/": {
                "url": "https://pes.edu/admissions/",
                "last_modified": "Mon, 20 Jul 2026 12:00:00 GMT",
                "etag": "etag123",
                "content_hash": "hash123",
                "chunk_ids": ["c1"]
            }
        }
        save_tracker(tracker_data)

        stats = run_sync_cycle(db_path="mock_db")
        
        # Check that we skipped crawling/ingesting
        self.assertEqual(stats["checked"], 1)
        self.assertEqual(stats["added"], 0)
        self.assertEqual(stats["updated"], 0)
        self.assertEqual(stats["failed"], 0)
        mock_crawler_class.assert_called_once()
        mock_ingest.assert_not_called()

    @patch("new_backend.scraper.autonomous_sync.ingest_single_file")
    @patch("new_backend.scraper.autonomous_sync.check_url_headers")
    @patch("new_backend.scraper.autonomous_sync.PESCrawler")
    def test_run_sync_cycle_content_changed(self, mock_crawler_class, mock_check_headers, mock_ingest):
        # 1. Headers indicate mismatch, triggering full fetch
        mock_check_headers.return_value = (True, "Tue, 21 Jul 2026 10:00:00 GMT", "etag_new", MagicMock(status_code=200))
        
        # Mock crawler instance
        mock_crawler = MagicMock()
        mock_crawler.get_url_category.return_value = "admissions"
        # Mock clean_url returning new content
        new_content = "# Admissions Info\nHere is updated content."
        mock_crawler.cleaner.clean_url.return_value = (new_content, [])
        mock_crawler_class.return_value = mock_crawler
        
        # Mock incremental ingester response
        mock_ingest.return_value = {
            "status": "success",
            "chunks_upserted": 2,
            "chunks_purged": 1,
            "chunk_ids": ["c1", "c2"],
            "collection": "admissions"
        }

        # Seed tracker with old content
        tracker_data = {
            "https://pes.edu/admissions/": {
                "url": "https://pes.edu/admissions/",
                "last_modified": "Mon, 20 Jul 2026 12:00:00 GMT",
                "etag": "etag_old",
                "content_hash": "hash_old",
                "chunk_ids": ["c_old"]
            }
        }
        save_tracker(tracker_data)

        stats = run_sync_cycle(db_path="mock_db")
        
        # Verify stats show update was performed
        self.assertEqual(stats["checked"], 1)
        self.assertEqual(stats["added"], 0)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["chunks_added"], 2)
        self.assertEqual(stats["chunks_removed"], 1)
        
        # Verify tracker updated
        updated_tracker = load_tracker()
        self.assertEqual(updated_tracker["https://pes.edu/admissions/"]["etag"], "etag_new")
        self.assertEqual(updated_tracker["https://pes.edu/admissions/"]["last_modified"], "Tue, 21 Jul 2026 10:00:00 GMT")
        self.assertEqual(updated_tracker["https://pes.edu/admissions/"]["chunk_ids"], ["c1", "c2"])

if __name__ == "__main__":
    unittest.main()
