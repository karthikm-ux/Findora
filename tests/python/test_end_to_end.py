import unittest
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
from app import FastRetrivalApp


class TestEndToEnd(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "e2e_test.db")
        self.app = FastRetrivalApp(db_path=self.db_path)
        self.app.queue_manager.start()

        # Create mock data folder
        self.mock_data = os.path.join(self.temp_dir.name, "files")
        os.makedirs(self.mock_data, exist_ok=True)

        for i in range(20):
            p = os.path.join(self.mock_data, f"report_{i}.pdf")
            with open(p, "w") as f:
                f.write(f"Sample report {i}")

    def tearDown(self):
        self.app.queue_manager.stop()
        self.temp_dir.cleanup()

    def test_scan_and_search_workflow(self):
        # 1. Scan folder
        self.app.scanner.scan_folder(self.mock_data)
        self.app.queue_manager.wait_empty()
        time.sleep(0.2)

        # 2. Check persistence stats
        stats = self.app.storage.get_stats()
        self.assertEqual(stats["total_files"], 20)

        # 3. Check B+ Tree exact search
        node, idx = self.app.tree.findWithoutKeys("report_5.pdf")
        self.assertIsNotNone(node)
        self.assertIn(os.path.join(self.mock_data, "report_5.pdf"), node.keys[idx])

        # 4. Check B+ Tree prefix range search
        prefix_matches = self.app.tree.prefix_search("report_")
        self.assertEqual(len(prefix_matches), 20)

        # 5. Check Case-Insensitive multi-stage search query
        case_matches = self.app.tree.search_query("REPORT_1")
        names = [m[0] for m in case_matches]
        self.assertIn("report_1.pdf", names)
        self.assertIn("report_10.pdf", names)

    def test_hydration_on_restart(self):
        # Index files first
        self.app.scanner.scan_folder(self.mock_data)
        self.app.queue_manager.wait_empty()
        time.sleep(0.2)

        # Create a second App instance pointing to the same DB (simulating restart)
        app2 = FastRetrivalApp(db_path=self.db_path)
        # Hydrate without scanning filesystem
        app2._hydrate_tree_from_storage()

        # Verify B+ Tree was instantly restored from SQLite
        self.assertEqual(app2.tree.count_total_files(), 20)
        self.assertTrue(app2.tree.find("report_0.pdf", os.path.join(self.mock_data, "report_0.pdf")))


if __name__ == "__main__":
    unittest.main()

