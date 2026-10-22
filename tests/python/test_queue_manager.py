import unittest
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
from tree import BplusTree
from storage import StorageManager
from queue_manager import IndexMutationQueue, MutationType


class TestQueueManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_queue.db")
        self.storage = StorageManager(self.db_path)
        self.tree = BplusTree(4)
        self.q_manager = IndexMutationQueue(
            tree=self.tree,
            storage=self.storage,
            batch_flush_interval=0.05,
            max_batch_size=50
        )
        self.q_manager.start()

    def tearDown(self):
        self.q_manager.stop()
        self.temp_dir.cleanup()

    def test_enqueue_add_and_flush(self):
        self.q_manager.enqueue_add(
            full_path=r"C:\test\hello.py",
            filename="hello.py",
            size_bytes=256,
            mtime=100.0,
            drive="C:\\"
        )
        self.q_manager.wait_empty()
        time.sleep(0.1)

        # Verify in B+ Tree
        self.assertTrue(self.tree.find("hello.py", r"C:\test\hello.py"))

        # Verify in SQLite
        meta = self.storage.get_file_metadata(r"C:\test\hello.py")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["filename"], "hello.py")

    def test_enqueue_remove(self):
        self.q_manager.enqueue_add(r"C:\test\temp.log", "temp.log", 10, 50.0, "C:\\")
        self.q_manager.wait_empty()
        time.sleep(0.1)
        self.assertTrue(self.tree.find("temp.log", r"C:\test\temp.log"))

        self.q_manager.enqueue_remove(r"C:\test\temp.log", "temp.log")
        self.q_manager.wait_empty()
        time.sleep(0.1)

        self.assertFalse(self.tree.find("temp.log", r"C:\test\temp.log"))
        self.assertIsNone(self.storage.get_file_metadata(r"C:\test\temp.log"))

    def test_enqueue_rename(self):
        self.q_manager.enqueue_add(r"C:\test\old_name.txt", "old_name.txt", 100, 1.0, "C:\\")
        self.q_manager.wait_empty()
        time.sleep(0.1)

        self.q_manager.enqueue_rename(
            old_path=r"C:\test\old_name.txt",
            old_name="old_name.txt",
            new_path=r"C:\test\new_name.txt",
            new_name="new_name.txt",
            size_bytes=100,
            mtime=2.0,
            drive="C:\\"
        )
        self.q_manager.wait_empty()
        time.sleep(0.1)

        self.assertFalse(self.tree.find("old_name.txt", r"C:\test\old_name.txt"))
        self.assertTrue(self.tree.find("new_name.txt", r"C:\test\new_name.txt"))
        self.assertIsNone(self.storage.get_file_metadata(r"C:\test\old_name.txt"))
        self.assertIsNotNone(self.storage.get_file_metadata(r"C:\test\new_name.txt"))

    def test_batch_add(self):
        batch = [
            {"drive": "C:\\", "full_path": f"C:\\dir\\item_{i}.dat", "filename": f"item_{i}.dat", "size_bytes": i, "mtime": float(i)}
            for i in range(150)
        ]
        self.q_manager.enqueue_batch_add(batch)
        self.q_manager.wait_empty()
        time.sleep(0.15)

        self.assertEqual(self.tree.count_total_files(), 150)
        stats = self.storage.get_stats()
        self.assertEqual(stats["total_files"], 150)


if __name__ == "__main__":
    unittest.main()

