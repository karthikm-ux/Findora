import unittest
import sys
import os
import tempfile
import time
from unittest.mock import patch, MagicMock
import tkinter as tk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
from tree import BplusTree
from storage import StorageManager
from gui import GlassmorphismSearchWidget, FileIconRenderer
from system_integration import SingleInstanceChecker


class MockAppCore:
    def __init__(self, storage):
        self.tree = BplusTree(order=16)
        self.storage = storage


class TestGlassmorphismWidget(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "glass_widget_test.db")
        self.storage = StorageManager(self.db_path)
        self.mock_app = MockAppCore(self.storage)

        # Seed sample files matching the screenshot reference
        self.mock_app.tree.insert("Project_Report.docx", "D:\\College\\Final Year\\Project_Report.docx")
        self.mock_app.tree.insert("Annual Report 2024.pdf", "D:\\Work\\Reports\\Annual Report 2024.pdf")
        self.mock_app.tree.insert("report.xlsx", "C:\\Users\\Student\\Documents\\report.xlsx")
        self.mock_app.tree.insert("system_report.txt", "C:\\Windows\\Logs\\system_report.txt")
        self.mock_app.tree.insert("report.xlsx", "D:\\Backup\\report.xlsx")  # duplicate filename across drives

        self.storage.upsert_file("D:\\College\\Final Year\\Project_Report.docx", "Project_Report.docx", 45000, 1000.0, "D:\\")
        self.storage.upsert_file("D:\\Work\\Reports\\Annual Report 2024.pdf", "Annual Report 2024.pdf", 120000, 1100.0, "D:\\")
        self.storage.upsert_file("C:\\Users\\Student\\Documents\\report.xlsx", "report.xlsx", 35000, 1200.0, "C:\\")
        self.storage.upsert_file("C:\\Windows\\Logs\\system_report.txt", "system_report.txt", 1500, 1300.0, "C:\\")
        self.storage.upsert_file("D:\\Backup\\report.xlsx", "report.xlsx", 35000, 1400.0, "D:\\")

        self.widget = GlassmorphismSearchWidget(
            parent=self.root,
            app_core=self.mock_app,
            on_open_settings=lambda: None,
            on_status=lambda: None,
            on_rescan=lambda: None,
            on_exit=lambda: None
        )

    def tearDown(self):
        try:
            self.widget.destroy()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_idle_and_expanded_state_transitions(self):
        # Starts in IDLE state
        self.assertEqual(self.widget.state, "IDLE")
        self.assertEqual(self.widget.canvas.winfo_reqheight(), GlassmorphismSearchWidget.IDLE_HEIGHT)

        # Expand to EXPANDED state
        self.widget.expand_search()
        self.assertEqual(self.widget.state, "EXPANDED")
        self.assertGreater(self.widget.canvas.winfo_reqheight(), GlassmorphismSearchWidget.IDLE_HEIGHT)

        # Collapse back to IDLE state
        self.widget.collapse_to_idle()
        self.assertEqual(self.widget.state, "IDLE")

        # Toggle switches between states
        self.widget.toggle_widget()
        self.assertEqual(self.widget.state, "EXPANDED")
        self.widget.toggle_widget()
        self.assertEqual(self.widget.state, "IDLE")

    def test_file_icon_renderer(self):
        icon_docx = FileIconRenderer.get_icon("docx")
        self.assertIsNotNone(icon_docx)

        icon_pdf = FileIconRenderer.get_icon("pdf")
        self.assertIsNotNone(icon_pdf)

        icon_xlsx = FileIconRenderer.get_icon("xlsx")
        self.assertIsNotNone(icon_xlsx)

        icon_txt = FileIconRenderer.get_icon("txt")
        self.assertIsNotNone(icon_txt)

        # Test caching
        icon_docx_cached = FileIconRenderer.get_icon(".DOCX")
        self.assertIs(icon_docx, icon_docx_cached)

    def test_duplicate_filenames_displayed_as_multiple_results(self):
        self.widget.expand_search()
        self.widget.search_var.set("report")
        self.widget._execute_search()

        # Results should contain report.xlsx from both drives C: and D:
        paths = [r["full_path"] for r in self.widget.results]
        self.assertIn("C:\\Users\\Student\\Documents\\report.xlsx", paths)
        self.assertIn("D:\\Backup\\report.xlsx", paths)
        self.assertIn("D:\\College\\Final Year\\Project_Report.docx", paths)

    def test_keyboard_arrow_navigation(self):
        self.widget.expand_search()
        self.widget.search_var.set("report")
        self.widget._execute_search()

        self.assertGreater(len(self.widget.results), 1)
        self.assertEqual(self.widget.selected_index, 0)

        # Down arrow moves to next item
        self.widget._on_key_down(None)
        self.assertEqual(self.widget.selected_index, 1)

        # Up arrow moves back
        self.widget._on_key_up(None)
        self.assertEqual(self.widget.selected_index, 0)

    @patch("subprocess.Popen")
    @patch("os.path.exists", return_value=True)
    def test_enter_key_reveals_in_explorer_and_collapses(self, mock_exists, mock_popen):
        self.widget.expand_search()
        self.widget.search_var.set("Project_Report")
        self.widget._execute_search()

        selected_path = self.widget.get_selected_path()
        self.assertIn("Project_Report.docx", selected_path)

        # Press Enter key
        self.widget._on_key_enter(None)

        # Verifies explorer.exe was called with /select,"path"
        mock_popen.assert_called_once()
        cmd_args = mock_popen.call_args[0][0]
        self.assertEqual(cmd_args[0], "explorer.exe")
        self.assertTrue(cmd_args[1].startswith("/select,"))
        self.assertIn("Project_Report.docx", cmd_args[1])

        # Verifies widget collapsed back to IDLE state
        self.assertEqual(self.widget.state, "IDLE")

    def test_single_instance_checker(self):
        c1 = SingleInstanceChecker(mutex_name="FastRetrival_Test_Exclusive_Glass")
        self.assertFalse(c1.is_already_running())

        c2 = SingleInstanceChecker(mutex_name="FastRetrival_Test_Exclusive_Glass")
        self.assertTrue(c2.is_already_running())

        c1.cleanup()
        c2.cleanup()


if __name__ == "__main__":
    unittest.main()

