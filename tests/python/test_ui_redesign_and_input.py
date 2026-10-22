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
from gui import GlassmorphismSearchWidget, DesktopIdleWidget


class MockAppCore:
    def __init__(self, storage):
        self.tree = BplusTree(order=16)
        self.storage = storage


class TestUIRedesignAndInputFix(unittest.TestCase):

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
        self.db_path = os.path.join(self.temp_dir.name, "ui_redesign_test.db")
        self.storage = StorageManager(self.db_path)
        self.mock_app = MockAppCore(self.storage)

        # Seed data
        self.mock_app.tree.insert("Quarterly_Report_2026.docx", "C:\\Work\\Quarterly_Report_2026.docx")
        self.mock_app.tree.insert("Budget_2026.xlsx", "C:\\Finance\\Budget_2026.xlsx")
        self.mock_app.tree.insert("notes.txt", "D:\\Notes\\notes.txt")
        self.mock_app.tree.insert("test_script.py", "D:\\Dev\\test_script.py")

        self.storage.upsert_file("C:\\Work\\Quarterly_Report_2026.docx", "Quarterly_Report_2026.docx", 50000, 1000.0, "C:\\")
        self.storage.upsert_file("C:\\Finance\\Budget_2026.xlsx", "Budget_2026.xlsx", 85000, 1100.0, "C:\\")
        self.storage.upsert_file("D:\\Notes\\notes.txt", "notes.txt", 1200, 1200.0, "D:\\")
        self.storage.upsert_file("D:\\Dev\\test_script.py", "test_script.py", 3400, 1300.0, "D:\\")

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

    def test_search_entry_permanence_and_no_deletion_on_results_update(self):
        """
        REGRESSION TEST FOR HIGHEST PRIORITY BUG:
        Verifies that typing and search results updates NEVER delete, recreate,
        or detach the search input widget from the canvas.
        """
        self.widget.expand_search()
        initial_entry = self.widget.search_entry
        self.assertIsNotNone(initial_entry)

        # Simulate typing
        self.widget.search_var.set("Quarterly")
        self.widget._execute_search()

        # The search entry instance must remain the EXACT same object
        self.assertIs(self.widget.search_entry, initial_entry)
        self.assertEqual(self.widget.search_var.get(), "Quarterly")
        self.assertEqual(self.widget.search_entry.get(), "Quarterly")

        # Verify entry window item is still on the canvas
        header_items = self.widget.canvas.find_withtag("header")
        self.assertGreater(len(header_items), 0)

        # Execute multiple consecutive rapid searches (simulate rapid typing)
        for term in ["Q", "Qu", "Quar", "Report", "notes"]:
            self.widget.search_var.set(term)
            self.widget._execute_search()
            self.assertIs(self.widget.search_entry, initial_entry)
            self.assertEqual(self.widget.search_entry.get(), term)

    def test_input_text_visibility_contrast_and_caret_properties(self):
        """
        Verifies foreground/background contrast, caret visibility, and font settings.
        """
        entry = self.widget.search_entry

        # Background should be bright (#ffffff) and text should be dark slate (#0f172a)
        self.assertEqual(entry.cget("bg"), "#ffffff")
        self.assertEqual(entry.cget("fg"), "#0f172a")

        # Caret must be vibrant blue and visible
        self.assertEqual(entry.cget("insertbackground"), "#2563eb")
        self.assertGreaterEqual(int(entry.cget("insertwidth")), 2)

        # High-contrast selection
        self.assertEqual(entry.cget("selectbackground"), "#bfdbfe")
        self.assertEqual(entry.cget("selectforeground"), "#1e3a8a")

    def test_typing_editing_backspace_selection_and_punctuation(self):
        """
        Verifies ordinary typing, backspace, selection, and punctuation handling.
        """
        self.widget.expand_search()
        entry = self.widget.search_entry

        # Typing alphanumeric with punctuation and spaces
        sample_query = "report (2026)_final.docx"
        self.widget.search_var.set(sample_query)
        self.assertEqual(entry.get(), sample_query)

        # Simulate backspace by trimming last character
        trimmed = sample_query[:-1]
        self.widget.search_var.set(trimmed)
        self.assertEqual(entry.get(), trimmed)

        # Verify search results stay synchronized with entry text
        self.widget.search_var.set("Budget")
        self.widget._execute_search()
        self.assertEqual(len(self.widget.results), 1)
        self.assertEqual(self.widget.results[0]["filename"], "Budget_2026.xlsx")

    def test_desktop_idle_widget_layering_and_non_topmost(self):
        """
        Verifies idle widget behavior:
        - Small desktop widget in configurable corner.
        - Not always-on-top (attributes('-topmost') is False).
        - Stays at desktop layer.
        """
        idle_widget = self.widget.idle_widget
        self.assertIsNotNone(idle_widget)
        self.assertIsInstance(idle_widget, DesktopIdleWidget)

        # Idle widget must NOT be set to topmost (does not cover normal windows)
        self.assertFalse(bool(idle_widget.attributes("-topmost")))

        # Check default corner positioning (bottom-right)
        sw = idle_widget.winfo_screenwidth()
        sh = idle_widget.winfo_screenheight()
        self.assertEqual(idle_widget.corner, "bottom-right")
        self.assertGreater(idle_widget.pos_x, sw // 2)
        self.assertGreater(idle_widget.pos_y, sh // 2)

        # Test repositioning to top-right corner
        idle_widget.set_corner("top-right")
        self.assertEqual(idle_widget.corner, "top-right")
        self.assertGreater(idle_widget.pos_x, sw // 2)
        self.assertLess(idle_widget.pos_y, sh // 2)

        # Test repositioning to bottom-left corner
        idle_widget.set_corner("bottom-left")
        self.assertEqual(idle_widget.corner, "bottom-left")
        self.assertLess(idle_widget.pos_x, sw // 2)
        self.assertGreater(idle_widget.pos_y, sh // 2)

    def test_search_window_centered_positioning(self):
        """
        Verifies that when activated, the search window appears near the center of the screen.
        """
        sw = self.widget.winfo_screenwidth()
        expected_center_x = (sw - self.widget.WIDGET_WIDTH) // 2
        self.assertEqual(self.widget.pos_x, expected_center_x)

    def test_empty_state_and_clear_button(self):
        """
        Verifies empty state card when no matching files exist and clear button behavior.
        """
        self.widget.expand_search()
        self.widget.search_var.set("nonexistent_filename_xyz_999")
        self.widget._execute_search()

        self.assertEqual(len(self.widget.results), 0)
        # Empty state items rendered on canvas
        empty_items = self.widget.canvas.find_withtag("empty_state")
        self.assertGreater(len(empty_items), 0)

        # Clear query
        self.widget.search_var.set("")
        self.widget._execute_search()
        self.assertEqual(len(self.widget.canvas.find_withtag("empty_state")), 0)
        self.assertEqual(len(self.widget.results), 0)


if __name__ == "__main__":
    unittest.main()

