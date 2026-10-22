import unittest
from unittest import mock
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
from storage import StorageManager


class TestStorageManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_fastretrival.db")
        self.storage = StorageManager(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_and_default_exclusions(self):
        exclusions = self.storage.get_exclusions()
        self.assertGreater(len(exclusions), 0)
        patterns = [e["pattern"] for e in exclusions]
        self.assertIn(r"$Recycle.Bin", patterns)
        self.assertIn(r"System Volume Information", patterns)

    def test_custom_exclusions(self):
        self.storage.add_exclusion(r"node_modules")
        self.assertTrue(self.storage.is_path_excluded(r"C:\Projects\my-app\node_modules\package.json"))
        self.assertFalse(self.storage.is_path_excluded(r"C:\Projects\my-app\src\index.js"))

        self.storage.remove_exclusion(r"node_modules")
        self.assertFalse(self.storage.is_path_excluded(r"C:\Projects\my-app\node_modules\package.json"))

    def test_upsert_and_retrieve_file(self):
        self.storage.upsert_file(
            full_path=r"C:\test\sample.txt",
            filename="sample.txt",
            size_bytes=1024,
            mtime=1234567.89,
            drive="C:\\"
        )

        meta = self.storage.get_file_metadata(r"C:\test\sample.txt")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["filename"], "sample.txt")
        self.assertEqual(meta["size_bytes"], 1024)
        self.assertEqual(meta["drive"], "C:\\")
        self.assertEqual(meta["extension"], ".txt")

    def test_batch_upsert_and_tree_loader(self):
        records = [
            {"drive": "C:\\", "full_path": f"C:\\dir\\file_{i}.txt", "filename": f"file_{i}.txt", "size_bytes": 100 * i, "mtime": 1000.0}
            for i in range(100)
        ]
        self.storage.upsert_files_batch(records)

        loaded = []
        for chunk in self.storage.load_all_records_for_tree(chunk_size=30):
            loaded.extend(chunk)

        self.assertEqual(len(loaded), 100)
        self.assertEqual(loaded[0], ("file_0.txt", "C:\\dir\\file_0.txt"))

    def test_delete_file(self):
        self.storage.upsert_file(r"C:\temp\delete_me.txt", "delete_me.txt", 50, 1000.0, "C:\\")
        self.assertIsNotNone(self.storage.get_file_metadata(r"C:\temp\delete_me.txt"))

        deleted = self.storage.delete_file(r"C:\temp\delete_me.txt")
        self.assertTrue(deleted)
        self.assertIsNone(self.storage.get_file_metadata(r"C:\temp\delete_me.txt"))

    def test_drive_status_update(self):
        self.storage.update_drive("C:\\", label="OS_Disk", fs_type="NTFS", total_bytes=1000000, free_bytes=500000, status="ready")
        drives = self.storage.get_drives()
        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]["drive_letter"], "C:\\")
        self.assertEqual(drives[0]["label"], "OS_Disk")
        self.assertEqual(drives[0]["status"], "ready")

    def test_metadata_key_value(self):
        self.storage.set_metadata("last_reconcile", "1729600000")
        val = self.storage.get_metadata("last_reconcile")
        self.assertEqual(val, "1729600000")
        self.assertIsNone(self.storage.get_metadata("non_existent"))

    def test_legacy_fastretrival_migration(self):
        # Setup simulated legacy FastRetrival directory and database
        simulated_localappdata = os.path.join(self.temp_dir.name, "LocalAppData")
        legacy_dir = os.path.join(simulated_localappdata, "FastRetrival")
        os.makedirs(legacy_dir, exist_ok=True)
        legacy_db = os.path.join(legacy_dir, "fastretrival.db")

        # Populate legacy db
        legacy_storage = StorageManager(db_path=legacy_db)
        legacy_storage.upsert_file(r"C:\Legacy\doc.txt", "doc.txt", 1234, 1000.0, "C:\\")

        # Now instantiate StorageManager without db_path, with patched LOCALAPPDATA
        with unittest.mock.patch.dict(os.environ, {"LOCALAPPDATA": simulated_localappdata}):
            new_storage = StorageManager(db_path=None)
            self.assertTrue(os.path.exists(new_storage.db_path))
            self.assertIn("Findora", new_storage.db_path)
            self.assertTrue(new_storage.db_path.endswith("findora.db"))

            # Verify migrated record exists in the new Findora database
            meta = new_storage.get_file_metadata(r"C:\Legacy\doc.txt")
            self.assertIsNotNone(meta)
            self.assertEqual(meta["size_bytes"], 1234)

            # Verify legacy database was NOT deleted
            self.assertTrue(os.path.exists(legacy_db))


if __name__ == "__main__":
    unittest.main()

