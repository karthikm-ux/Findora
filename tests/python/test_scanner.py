import unittest
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
from tree import BplusTree
from storage import StorageManager
from queue_manager import IndexMutationQueue
from scanner import Scanner, discover_local_drives


class TestScanner(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_scanner.db")
        self.storage = StorageManager(self.db_path)
        self.tree = BplusTree(4)
        self.queue_manager = IndexMutationQueue(
            tree=self.tree,
            storage=self.storage,
            batch_flush_interval=0.05,
            max_batch_size=50
        )
        self.queue_manager.start()

        # Create a sample nested directory structure
        self.scan_root = os.path.join(self.temp_dir.name, "sample_scan_root")
        os.makedirs(os.path.join(self.scan_root, "subdir1", "subsubdir"), exist_ok=True)
        os.makedirs(os.path.join(self.scan_root, "subdir2"), exist_ok=True)
        os.makedirs(os.path.join(self.scan_root, "$Recycle.Bin"), exist_ok=True)  # Should be excluded

        # Create files
        with open(os.path.join(self.scan_root, "root_file.txt"), "w") as f:
            f.write("hello root")
        with open(os.path.join(self.scan_root, "subdir1", "file_sub1.py"), "w") as f:
            f.write("print('sub1')")
        with open(os.path.join(self.scan_root, "subdir1", "subsubdir", "deep_file.dat"), "w") as f:
            f.write("data deep")
        with open(os.path.join(self.scan_root, "subdir2", "image.png"), "w") as f:
            f.write("fake png")
        with open(os.path.join(self.scan_root, "$Recycle.Bin", "deleted.tmp"), "w") as f:
            f.write("should not be indexed")

    def tearDown(self):
        self.queue_manager.stop()
        self.temp_dir.cleanup()

    def test_discover_local_drives(self):
        drives = discover_local_drives()
        self.assertGreater(len(drives), 0)
        letters = [d.letter for d in drives]
        self.assertIn("C:\\", letters)

    def test_scan_folder_indexes_correct_files(self):
        progress_reports = []
        scanner = Scanner(
            queue_manager=self.queue_manager,
            storage=self.storage,
            on_progress=lambda p: progress_reports.append(p),
            batch_size=2
        )

        scanner.scan_folder(self.scan_root)
        self.queue_manager.wait_empty()
        time.sleep(0.15)

        # Total expected valid files: 4 (root_file.txt, file_sub1.py, deep_file.dat, image.png)
        # $Recycle.Bin/deleted.tmp should be excluded!
        self.assertEqual(scanner.total_scanned_files, 4)
        self.assertTrue(self.tree.find("root_file.txt", os.path.join(self.scan_root, "root_file.txt")))
        self.assertTrue(self.tree.find("file_sub1.py", os.path.join(self.scan_root, "subdir1", "file_sub1.py")))
        self.assertTrue(self.tree.find("deep_file.dat", os.path.join(self.scan_root, "subdir1", "subsubdir", "deep_file.dat")))
        self.assertTrue(self.tree.find("image.png", os.path.join(self.scan_root, "subdir2", "image.png")))
        self.assertFalse(self.tree.find("deleted.tmp", os.path.join(self.scan_root, "$Recycle.Bin", "deleted.tmp")))

        self.assertGreater(len(progress_reports), 0)

    def test_cancel_scan(self):
        scanner = Scanner(self.queue_manager, self.storage, batch_size=1)
        scanner.cancel()
        scanner.scan_folder(self.scan_root)
        # Scan should exit immediately
        self.assertEqual(scanner.total_scanned_files, 0)


if __name__ == "__main__":
    unittest.main()

