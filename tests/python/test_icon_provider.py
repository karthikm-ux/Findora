import unittest
import sys
import os
import ctypes
from unittest.mock import patch, MagicMock
import tkinter as tk
from PIL import Image, ImageTk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
from icon_provider import WindowsIconProvider


class TestWindowsIconProvider(unittest.TestCase):

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
        WindowsIconProvider.clear_cache()

    def tearDown(self):
        WindowsIconProvider.clear_cache()

    def test_normalize_extension(self):
        self.assertEqual(WindowsIconProvider.normalize_extension("docx"), ".docx")
        self.assertEqual(WindowsIconProvider.normalize_extension(".DOCX"), ".docx")
        self.assertEqual(WindowsIconProvider.normalize_extension("C:\\Users\\Test\\file.PDF"), ".pdf")
        self.assertEqual(WindowsIconProvider.normalize_extension(".tar.gz"), ".gz")
        self.assertEqual(WindowsIconProvider.normalize_extension(""), ".default")
        self.assertEqual(WindowsIconProvider.normalize_extension("."), ".default")
        self.assertEqual(WindowsIconProvider.normalize_extension("   .xlsx   "), ".xlsx")

    def test_cache_reuse_for_identical_and_case_insensitive_queries(self):
        # Query docx in lowercase
        icon1 = WindowsIconProvider.get_icon("docx", size=26)
        self.assertIsNotNone(icon1)

        # Query docx with leading dot and uppercase
        icon2 = WindowsIconProvider.get_icon(".DOCX", size=26)
        # Should return the exact same cached PhotoImage object
        self.assertIs(icon1, icon2)

        # Query via full file path
        icon3 = WindowsIconProvider.get_icon("D:\\Documents\\Proposal.docx", size=26)
        self.assertIs(icon1, icon3)

        # PIL cache reuse
        pil1 = WindowsIconProvider.get_pil_icon("xlsx", size=26)
        pil2 = WindowsIconProvider.get_pil_icon(".XLSX", size=26)
        self.assertIs(pil1, pil2)

    def test_arbitrary_and_unassociated_extensions(self):
        # Even totally unknown/made-up extensions must return a valid icon without errors
        unusual_exts = [".xyz999_fake", ".random_unknown_type", ".custom_ext_42", ".not_a_real_type"]
        for ext in unusual_exts:
            icon = WindowsIconProvider.get_icon(ext, size=26)
            self.assertIsNotNone(icon)
            pil_img = WindowsIconProvider.get_pil_icon(ext, size=26)
            self.assertEqual(pil_img.size, (26, 26))
            self.assertEqual(pil_img.mode, "RGBA")

    def test_common_windows_file_types(self):
        common_types = [
            "docx", "xlsx", "pptx", "pdf", "txt", "py", "exe",
            "png", "jpg", "zip", "mp3", "mp4"
        ]
        for ctype in common_types:
            icon = WindowsIconProvider.get_icon(ctype, size=26)
            self.assertIsNotNone(icon)
            pil_img = WindowsIconProvider.get_pil_icon(ctype, size=26)
            self.assertEqual(pil_img.size, (26, 26))

    def test_graceful_fallback_when_native_api_fails(self):
        # Mock _extract_windows_shell_icon to simulate failure or non-Windows system
        with patch.object(WindowsIconProvider, "_extract_windows_shell_icon", return_value=None):
            pil_fallback = WindowsIconProvider.get_pil_icon("custom_fallback", size=26)
            self.assertIsNotNone(pil_fallback)
            self.assertEqual(pil_fallback.size, (26, 26))
            self.assertEqual(pil_fallback.mode, "RGBA")

            # Check Tk PhotoImage can also be created from fallback
            photo = WindowsIconProvider.get_icon("custom_fallback", size=26)
            self.assertIsNotNone(photo)

    def test_destroy_icon_called_on_native_handle(self):
        """Verify that user32.DestroyIcon is called in the finally block for non-zero hIcon."""
        if sys.platform != "win32":
            return

        with patch("ctypes.windll.user32.DestroyIcon") as mock_destroy:
            # We call _extract_windows_shell_icon directly
            img = WindowsIconProvider._extract_windows_shell_icon(".txt", 32)
            if img is not None:
                mock_destroy.assert_called()

    def test_icon_scaling_dimensions(self):
        img_16 = WindowsIconProvider.get_pil_icon(".pdf", size=16)
        self.assertEqual(img_16.size, (16, 16))

        img_32 = WindowsIconProvider.get_pil_icon(".pdf", size=32)
        self.assertEqual(img_32.size, (32, 32))

        img_48 = WindowsIconProvider.get_pil_icon(".pdf", size=48)
        self.assertEqual(img_48.size, (48, 48))

    def test_preload_common_icons(self):
        WindowsIconProvider.clear_cache()
        self.assertEqual(len(WindowsIconProvider._pil_cache), 0)

        WindowsIconProvider.preload_common_icons(size=26)
        self.assertGreater(len(WindowsIconProvider._pil_cache), 5)
        # Querying an already-preloaded type should have PIL cached
        self.assertIn((".docx", 26), WindowsIconProvider._pil_cache)
        self.assertIn((".pdf", 26), WindowsIconProvider._pil_cache)


if __name__ == "__main__":
    unittest.main()

