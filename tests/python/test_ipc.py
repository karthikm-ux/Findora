import unittest
import sys
import os
import tempfile
import json
from io import StringIO
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
from ipc_server import FastRetrivalIpcServer


class TestIpcServer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "ipc_test.db")
        self.server = FastRetrivalIpcServer(db_path=self.db_path)
        self.server.queue_manager.start()

        # Seed test files (including duplicates, spaces, unicode, unknown extensions)
        self.server.tree.insert("test_report.docx", "C:\\Reports\\test_report.docx")
        self.server.tree.insert("budget_2026.xlsx", "D:\\Finance\\budget_2026.xlsx")
        # Duplicate filename at different paths
        self.server.tree.insert("test_report.docx", "E:\\Backups\\test_report.docx")
        # Unicode filename and spaces
        self.server.tree.insert("отчёт за квартал.pdf", "C:\\Документы\\отчёт за квартал.pdf")
        self.server.tree.insert("custom_config.unknownext", "C:\\App\\custom_config.unknownext")

        self.server.storage.upsert_file("C:\\Reports\\test_report.docx", "test_report.docx", 25000, 1000.0, "C:\\")
        self.server.storage.upsert_file("D:\\Finance\\budget_2026.xlsx", "budget_2026.xlsx", 55000, 1100.0, "D:\\")
        self.server.storage.upsert_file("E:\\Backups\\test_report.docx", "test_report.docx", 25000, 1200.0, "E:\\")
        self.server.storage.upsert_file("C:\\Документы\\отчёт за квартал.pdf", "отчёт за квартал.pdf", 80000, 1300.0, "C:\\")
        self.server.storage.upsert_file("C:\\App\\custom_config.unknownext", "custom_config.unknownext", 1200, 1400.0, "C:\\")

    def tearDown(self):
        self.server.stop()
        self.temp_dir.cleanup()

    def _execute_request(self, req_dict):
        fake_stdout = StringIO()
        with patch("sys.stdout", fake_stdout):
            self.server.handle_request(json.dumps(req_dict))
        raw_output = fake_stdout.getvalue().strip()
        self.assertTrue(raw_output, "No output written to stdout")
        return json.loads(raw_output)

    def test_ping_method(self):
        res = self._execute_request({"id": 101, "method": "ping"})
        self.assertEqual(res["id"], 101)
        self.assertIsNone(res["error"])
        self.assertTrue(res["result"]["pong"])
        self.assertEqual(res["result"]["protocol"], FastRetrivalIpcServer.PROTOCOL_VERSION)

    def test_search_method(self):
        res = self._execute_request({
            "id": 102,
            "method": "search",
            "params": {"query": "report", "limit": 5}
        })
        self.assertEqual(res["id"], 102)
        self.assertIsNone(res["error"])
        items = res["result"]["items"]
        self.assertEqual(len(items), 2)  # Two duplicate test_report.docx entries
        paths = [item["full_path"] for item in items]
        self.assertIn("C:\\Reports\\test_report.docx", paths)
        self.assertIn("E:\\Backups\\test_report.docx", paths)
        # Latency metadata assertions
        self.assertIn("index_ms", res["result"])
        self.assertIn("meta_ms", res["result"])
        self.assertIn("total_ms", res["result"])
        self.assertGreaterEqual(res["result"]["total_ms"], 0.0)

    def test_search_empty_query(self):
        res = self._execute_request({
            "id": 103,
            "method": "search",
            "params": {"query": "   "}
        })
        self.assertEqual(res["id"], 103)
        self.assertEqual(res["result"]["items"], [])
        self.assertEqual(res["result"]["total_matches"], 0)

    def test_search_unicode_and_spaces(self):
        res = self._execute_request({
            "id": 104,
            "method": "search",
            "params": {"query": "отчёт за квартал"}
        })
        self.assertEqual(res["id"], 104)
        items = res["result"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["filename"], "отчёт за квартал.pdf")
        self.assertEqual(items[0]["extension"], ".pdf")

    def test_search_unknown_extension(self):
        res = self._execute_request({
            "id": 105,
            "method": "search",
            "params": {"query": "custom_config"}
        })
        self.assertEqual(res["id"], 105)
        items = res["result"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["extension"], ".unknownext")

    def test_reveal_existing_file(self):
        test_file = os.path.join(self.temp_dir.name, "real_file.txt")
        with open(test_file, "w") as f:
            f.write("content")

        with patch("subprocess.Popen") as mock_popen:
            res = self._execute_request({
                "id": 106,
                "method": "reveal",
                "params": {"path": test_file}
            })
            self.assertEqual(res["id"], 106)
            self.assertIsNone(res["error"])
            self.assertTrue(res["result"]["revealed"])
            self.assertEqual(res["result"]["path"], test_file)
            mock_popen.assert_called_once()
            cmd_arg = mock_popen.call_args[0][0]
            if isinstance(cmd_arg, list):
                self.assertEqual(cmd_arg[0], "explorer.exe")
                self.assertIn(test_file, cmd_arg[1])
            else:
                self.assertTrue(cmd_arg.startswith("explorer.exe"))
                self.assertIn(test_file, cmd_arg)

    def test_reveal_nonexistent_file_opens_folder(self):
        missing_file = os.path.join(self.temp_dir.name, "nonexistent.txt")
        # Parent directory self.temp_dir.name exists
        with patch("os.startfile", create=True) as mock_startfile:
            res = self._execute_request({
                "id": 107,
                "method": "reveal",
                "params": {"path": missing_file}
            })
            self.assertEqual(res["id"], 107)
            self.assertIsNone(res["error"])
            self.assertTrue(res["result"]["revealed"])
            self.assertEqual(res["result"]["path"], self.temp_dir.name)
            mock_startfile.assert_called_once_with(self.temp_dir.name)

    def test_reveal_completely_invalid_path(self):
        bad_path = "Z:\\NonExistentDrive\\FakeFolder\\FakeFile.txt"
        res = self._execute_request({
            "id": 108,
            "method": "reveal",
            "params": {"path": bad_path}
        })
        self.assertEqual(res["id"], 108)
        self.assertIsNotNone(res["error"])
        self.assertIn("Path not found", res["error"])

    def test_open_existing_file(self):
        test_file = os.path.join(self.temp_dir.name, "open_me.txt")
        with open(test_file, "w") as f:
            f.write("open test")

        with patch("os.startfile", create=True) as mock_startfile:
            res = self._execute_request({
                "id": 109,
                "method": "open",
                "params": {"path": test_file}
            })
            self.assertEqual(res["id"], 109)
            self.assertIsNone(res["error"])
            self.assertTrue(res["result"]["opened"])
            self.assertEqual(res["result"]["path"], test_file)
            mock_startfile.assert_called_once_with(test_file)

    def test_open_missing_file(self):
        bad_file = "Z:\\Missing\\file.txt"
        res = self._execute_request({
            "id": 110,
            "method": "open",
            "params": {"path": bad_file}
        })
        self.assertEqual(res["id"], 110)
        self.assertIsNotNone(res["error"])
        self.assertIn("File not found", res["error"])

    def test_status_method(self):
        res = self._execute_request({"id": 111, "method": "status"})
        self.assertEqual(res["id"], 111)
        self.assertIsNone(res["error"])
        stats = res["result"]["stats"]
        self.assertEqual(stats["total_files"], 5)
        self.assertEqual(res["result"]["tree_files_loaded"], 5)

    def test_exclusions_methods(self):
        # 1. Add exclusion
        res_add = self._execute_request({
            "id": 112,
            "method": "exclusions_add",
            "params": {"pattern": "C:\\Windows\\Temp"}
        })
        self.assertTrue(res_add["result"]["added"])

        # 2. Get exclusions
        res_get = self._execute_request({"id": 113, "method": "exclusions_get"})
        patterns = [e["pattern"] for e in res_get["result"]["exclusions"]]
        self.assertIn("C:\\Windows\\Temp", patterns)

        # 3. Remove exclusion
        res_rem = self._execute_request({
            "id": 114,
            "method": "exclusions_remove",
            "params": {"pattern": "C:\\Windows\\Temp"}
        })
        self.assertTrue(res_rem["result"]["removed"])

    def test_invalid_json_handling(self):
        fake_stdout = StringIO()
        with patch("sys.stdout", fake_stdout):
            self.server.handle_request("{invalid_json_content")
        raw_output = fake_stdout.getvalue().strip()
        res = json.loads(raw_output)
        self.assertIsNotNone(res["error"])


if __name__ == "__main__":
    unittest.main()

