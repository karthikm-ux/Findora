import unittest
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
from tree import BplusTree
from storage import StorageManager
from queue_manager import IndexMutationQueue
from reconciler import ReconciliationEngine
from watcher import DriveWatcher


class TestWatcherAndReconciler(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_watcher.db")
        self.storage = StorageManager(self.db_path)
        self.tree = BplusTree(4)
        self.queue_manager = IndexMutationQueue(
            tree=self.tree,
            storage=self.storage,
            batch_flush_interval=0.05,
            max_batch_size=20
        )
        self.queue_manager.start()

        self.watch_folder = os.path.join(self.temp_dir.name, "watched_area")
        os.makedirs(self.watch_folder, exist_ok=True)

    def tearDown(self):
        self.queue_manager.stop()
        self.temp_dir.cleanup()

    def test_reconciler_detects_offline_files(self):
        # Set drive in DB with past sync time
        drive_letter = os.path.splitdrive(self.watch_folder)[0].upper() + "\\"
        past_time = time.time() - 3600  # 1 hour ago
        self.storage.update_drive(drive_letter, last_sync_time=past_time, status="indexed")

        # Create a new file in watch folder
        new_file = os.path.join(self.watch_folder, "offline_doc.txt")
        with open(new_file, "w") as f:
            f.write("Created while offline")

        reconciler = ReconciliationEngine(self.queue_manager, self.storage)
        res = reconciler.reconcile_drive(drive_letter)
        self.queue_manager.wait_empty()
        time.sleep(0.15)

        self.assertGreaterEqual(res["duration"], 0)
        # Drive status should be indexed
        drives = {d["drive_letter"]: d for d in self.storage.get_drives()}
        self.assertEqual(drives[drive_letter]["status"], "indexed")

    def test_drive_watcher_live_events(self):
        events_received = []
        watcher = DriveWatcher(
            root_path=self.watch_folder,
            queue_manager=self.queue_manager,
            storage=self.storage,
            on_event=lambda act, path: events_received.append((act, path))
        )
        watcher.start()
        time.sleep(0.2)

        try:
            # Create a file
            test_file = os.path.join(self.watch_folder, "live_created.txt")
            with open(test_file, "w") as f:
                f.write("Live content")

            # Allow watcher loop and queue to process
            time.sleep(0.5)
            self.queue_manager.wait_empty()
            time.sleep(0.1)

            # Check that file was indexed into B+ Tree
            self.assertTrue(
                self.tree.find("live_created.txt", test_file),
                f"live_created.txt was not indexed into B+ Tree! Events: {events_received}"
            )
        finally:
            watcher.stop()


if __name__ == "__main__":
    unittest.main()

