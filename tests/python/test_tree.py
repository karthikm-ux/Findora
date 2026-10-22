import unittest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
import tree


class TestBPlusTree(unittest.TestCase):

    def test_basic_insert_and_find(self):
        t = tree.BplusTree(3)
        t.insert("apple.txt", "C:\\docs\\apple.txt")
        t.insert("banana.py", "C:\\scripts\\banana.py")
        t.insert("cherry.md", "C:\\notes\\cherry.md")

        self.assertTrue(t.find("apple.txt", "C:\\docs\\apple.txt"))
        self.assertFalse(t.find("apple.txt", "C:\\wrong\\path.txt"))
        self.assertFalse(t.find("notfound.txt", "path"))

        node, idx = t.findWithoutKeys("banana.py")
        self.assertIsNotNone(node)
        self.assertEqual(node.values[idx], "banana.py")
        self.assertIn("C:\\scripts\\banana.py", node.keys[idx])

    def test_duplicate_filenames_multiple_paths(self):
        t = tree.BplusTree(3)
        t.insert("README.md", "C:\\proj1\\README.md")
        t.insert("README.md", "D:\\proj2\\README.md")
        t.insert("README.md", "E:\\proj3\\README.md")

        node, idx = t.findWithoutKeys("README.md")
        self.assertIsNotNone(node)
        self.assertEqual(node.values[idx], "README.md")
        self.assertEqual(len(node.keys[idx]), 3)
        self.assertIn("C:\\proj1\\README.md", node.keys[idx])
        self.assertIn("D:\\proj2\\README.md", node.keys[idx])
        self.assertIn("E:\\proj3\\README.md", node.keys[idx])

    def test_no_duplicate_identical_paths(self):
        t = tree.BplusTree(3)
        t.insert("test.log", "C:\\logs\\test.log")
        t.insert("test.log", "C:\\logs\\test.log")  # Duplicate insertion

        node, idx = t.findWithoutKeys("test.log")
        self.assertIsNotNone(node)
        self.assertEqual(len(node.keys[idx]), 1)

    def test_remove_specific_path(self):
        t = tree.BplusTree(4)
        t.insert("config.json", "C:\\app\\config.json")
        t.insert("config.json", "D:\\backup\\config.json")

        # Remove one path
        removed = t.remove("config.json", "C:\\app\\config.json")
        self.assertTrue(removed)

        # Still exists with the remaining path
        node, idx = t.findWithoutKeys("config.json")
        self.assertIsNotNone(node)
        self.assertNotIn("C:\\app\\config.json", node.keys[idx])
        self.assertIn("D:\\backup\\config.json", node.keys[idx])

        # Remove the remaining path
        removed2 = t.remove("config.json", "D:\\backup\\config.json")
        self.assertTrue(removed2)

        # Now config.json should be completely absent
        node2, idx2 = t.findWithoutKeys("config.json")
        self.assertFalse(node2)

    def test_prefix_search(self):
        t = tree.BplusTree(4)
        files = [
            ("apple.txt", "C:\\apple.txt"),
            ("application.exe", "C:\\application.exe"),
            ("apply.doc", "C:\\apply.doc"),
            ("apricot.png", "C:\\apricot.png"),
            ("banana.jpg", "C:\\banana.jpg"),
            ("cat.gif", "C:\\cat.gif"),
        ]
        for name, path in files:
            t.insert(name, path)

        results = t.prefix_search("appl")
        res_names = [name for name, _ in results]
        self.assertEqual(sorted(res_names), ["apple.txt", "application.exe", "apply.doc"])

    def test_substring_search(self):
        t = tree.BplusTree(4)
        files = [
            ("report_2026_q1.pdf", "C:\\finance\\report_2026_q1.pdf"),
            ("annual_report_final.docx", "C:\\docs\\annual_report_final.docx"),
            ("notes.txt", "C:\\notes.txt"),
            ("tele_report.py", "C:\\code\\tele_report.py"),
        ]
        for name, path in files:
            t.insert(name, path)

        results = t.substring_search("report")
        res_names = [name for name, _ in results]
        self.assertIn("report_2026_q1.pdf", res_names)
        self.assertIn("annual_report_final.docx", res_names)
        self.assertIn("tele_report.py", res_names)
        self.assertNotIn("notes.txt", res_names)

    def test_search_query_case_insensitive(self):
        t = tree.BplusTree(4)
        t.insert("README.MD", "C:\\README.MD")
        t.insert("readme_old.txt", "C:\\readme_old.txt")
        t.insert("project_readme.markdown", "C:\\project_readme.markdown")
        t.insert("other.py", "C:\\other.py")

        results = t.search_query("readme")
        names = [r[0] for r in results]
        self.assertIn("README.MD", names)
        self.assertIn("readme_old.txt", names)
        self.assertIn("project_readme.markdown", names)
        self.assertNotIn("other.py", names)
        # Exact match should come first
        self.assertEqual(names[0], "README.MD")

    def test_large_random_dataset(self):
        import random
        random.seed(123)
        t = tree.BplusTree(16)
        n = 2000
        items = [(f"file_{i:04d}.dat", f"C:\\data\\file_{i:04d}.dat") for i in range(n)]
        random.shuffle(items)

        for name, path in items:
            t.insert(name, path)

        # Check all present
        for name, path in items:
            self.assertTrue(t.find(name, path), f"Failed to find {name}")

        # Check remove half
        for name, path in items[:500]:
            self.assertTrue(t.remove(name, path), f"Failed to remove {name}")

        for name, path in items[:500]:
            self.assertFalse(t.find(name, path), f"Should not find {name}")

        for name, path in items[500:]:
            self.assertTrue(t.find(name, path), f"Should still find {name}")


if __name__ == "__main__":
    unittest.main()

