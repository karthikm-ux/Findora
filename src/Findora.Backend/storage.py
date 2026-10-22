import os
import sqlite3
import threading
import time
from typing import List, Dict, Optional, Tuple, Any

DEFAULT_EXCLUSIONS = [
    r"$Recycle.Bin",
    r"System Volume Information",
    r"pagefile.sys",
    r"hiberfil.sys",
    r"swapfile.sys",
    r"DumpStack.log",
    r"Thumbs.db",
    r"desktop.ini",
    r"C:\Windows\WinSxS",
    r"C:\Windows\SoftwareDistribution",
    r"C:\Windows\System32\LogFiles",
]


class StorageManager:
    """
    Manages persistent SQLite storage for Findora file records,
    drive status, exclusions, and recovery metadata.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            data_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Findora")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "findora.db")
            if not os.path.exists(self.db_path):
                self._migrate_legacy_db()
        else:
            self.db_path = db_path
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

        self._lock = threading.Lock()
        self._init_db()

    def _migrate_legacy_db(self):
        """Safely imports existing index and settings from legacy FastRetrival database."""
        legacy_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FastRetrival")
        legacy_db = os.path.join(legacy_dir, "fastretrival.db")
        if os.path.exists(legacy_db):
            try:
                import shutil
                shutil.copy2(legacy_db, self.db_path)
                for ext in ["-wal", "-shm"]:
                    extra = legacy_db + ext
                    if os.path.exists(extra):
                        shutil.copy2(extra, self.db_path + ext)
            except Exception:
                pass

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -32000;")  # 32 MB cache
        return conn

    def _init_db(self):
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.executescript("""
                    CREATE TABLE IF NOT EXISTS files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        drive TEXT NOT NULL,
                        full_path TEXT UNIQUE NOT NULL,
                        filename TEXT NOT NULL,
                        filename_lower TEXT NOT NULL,
                        extension TEXT,
                        size_bytes INTEGER DEFAULT 0,
                        mtime REAL DEFAULT 0,
                        indexed_at REAL DEFAULT 0
                    );

                    CREATE INDEX IF NOT EXISTS idx_files_path ON files(full_path);
                    CREATE INDEX IF NOT EXISTS idx_files_drive ON files(drive);
                    CREATE INDEX IF NOT EXISTS idx_files_filename ON files(filename);
                    CREATE INDEX IF NOT EXISTS idx_files_filename_lower ON files(filename_lower);

                    CREATE TABLE IF NOT EXISTS drives (
                        drive_letter TEXT PRIMARY KEY,
                        label TEXT DEFAULT '',
                        fs_type TEXT DEFAULT '',
                        total_bytes INTEGER DEFAULT 0,
                        free_bytes INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'unindexed',
                        last_scan_time REAL DEFAULT 0,
                        last_sync_time REAL DEFAULT 0,
                        is_monitored INTEGER DEFAULT 1,
                        file_count INTEGER DEFAULT 0,
                        error_message TEXT DEFAULT ''
                    );

                    CREATE TABLE IF NOT EXISTS exclusions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pattern TEXT UNIQUE NOT NULL,
                        is_regex INTEGER DEFAULT 0,
                        is_active INTEGER DEFAULT 1
                    );

                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                """)
                conn.commit()

                # Seed default exclusions if table is empty
                cursor.execute("SELECT COUNT(*) FROM exclusions")
                if cursor.fetchone()[0] == 0:
                    cursor.executemany(
                        "INSERT OR IGNORE INTO exclusions (pattern, is_regex, is_active) VALUES (?, 0, 1)",
                        [(ex,) for ex in DEFAULT_EXCLUSIONS]
                    )
                    conn.commit()
            finally:
                conn.close()

    def upsert_files_batch(self, file_records: List[Dict[str, Any]]):
        """
        Batch upsert files into SQLite.
        file_records: list of dicts with keys:
          drive, full_path, filename, filename_lower, extension, size_bytes, mtime, indexed_at
        """
        if not file_records:
            return

        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                rows = [
                    (
                        r.get("drive", ""),
                        r["full_path"],
                        r["filename"],
                        r.get("filename_lower", r["filename"].lower()),
                        r.get("extension", os.path.splitext(r["filename"])[1].lower()),
                        r.get("size_bytes", 0),
                        r.get("mtime", 0.0),
                        r.get("indexed_at", time.time()),
                    )
                    for r in file_records
                ]
                cursor.executemany("""
                    INSERT INTO files (drive, full_path, filename, filename_lower, extension, size_bytes, mtime, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(full_path) DO UPDATE SET
                        filename=excluded.filename,
                        filename_lower=excluded.filename_lower,
                        extension=excluded.extension,
                        size_bytes=excluded.size_bytes,
                        mtime=excluded.mtime,
                        indexed_at=excluded.indexed_at
                """, rows)
                conn.commit()
            finally:
                conn.close()

    def upsert_file(self, full_path: str, filename: str, size_bytes: int = 0, mtime: float = 0.0, drive: str = ""):
        self.upsert_files_batch([{
            "drive": drive or (os.path.splitdrive(full_path)[0].upper() + "\\"),
            "full_path": full_path,
            "filename": filename,
            "filename_lower": filename.lower(),
            "extension": os.path.splitext(filename)[1].lower(),
            "size_bytes": size_bytes,
            "mtime": mtime,
            "indexed_at": time.time(),
        }])

    def delete_file(self, full_path: str) -> bool:
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM files WHERE full_path = ?", (full_path,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def delete_files_batch(self, full_paths: List[str]):
        if not full_paths:
            return
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.executemany("DELETE FROM files WHERE full_path = ?", [(p,) for p in full_paths])
                conn.commit()
            finally:
                conn.close()

    def get_file_metadata(self, full_path: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE full_path = ?", (full_path,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def get_files_metadata_batch(self, paths: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fast batch fetch of file metadata for a list of paths (used by search UI).
        """
        if not paths:
            return {}
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(paths))
            cursor.execute(
                f"SELECT full_path, filename, extension, size_bytes, mtime, drive FROM files WHERE full_path IN ({placeholders})",
                paths
            )
            results = {}
            for row in cursor.fetchall():
                results[row["full_path"]] = dict(row)
            return results
        finally:
            conn.close()

    def load_all_records_for_tree(self, chunk_size: int = 10000):
        """
        Yields chunks of file records (filename, full_path) for populating the B+ Tree.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT filename, full_path FROM files ORDER BY id ASC")
            while True:
                rows = cursor.fetchmany(chunk_size)
                if not rows:
                    break
                yield [(r["filename"], r["full_path"]) for r in rows]
        finally:
            conn.close()

    def update_drive(self, drive_letter: str, **kwargs):
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT drive_letter FROM drives WHERE drive_letter = ?", (drive_letter,))
                exists = cursor.fetchone()

                if not exists:
                    cursor.execute("""
                        INSERT INTO drives (drive_letter, label, fs_type, total_bytes, free_bytes, status, last_scan_time, last_sync_time, is_monitored, file_count, error_message)
                        VALUES (?, '', '', 0, 0, 'unindexed', 0, 0, 1, 0, '')
                    """, (drive_letter,))

                if kwargs:
                    sets = ", ".join([f"{k} = ?" for k in kwargs.keys()])
                    values = list(kwargs.values()) + [drive_letter]
                    cursor.execute(f"UPDATE drives SET {sets} WHERE drive_letter = ?", values)

                conn.commit()
            finally:
                conn.close()

    def get_drives(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM drives ORDER BY drive_letter ASC")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_exclusions(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM exclusions WHERE is_active = 1")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def add_exclusion(self, pattern: str, is_regex: bool = False):
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO exclusions (pattern, is_regex, is_active)
                    VALUES (?, ?, 1)
                    ON CONFLICT(pattern) DO UPDATE SET is_active = 1
                """, (pattern, 1 if is_regex else 0))
                conn.commit()
            finally:
                conn.close()

    def remove_exclusion(self, pattern: str):
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM exclusions WHERE pattern = ?", (pattern,))
                conn.commit()
            finally:
                conn.close()

    def is_path_excluded(self, path: str, cached_patterns: Optional[List[str]] = None) -> bool:
        """
        Checks if a given path matches any exclusion patterns.
        """
        if cached_patterns is None:
            cached_patterns = [e["pattern"] for e in self.get_exclusions()]

        path_norm = os.path.normpath(path).lower()
        for pat in cached_patterns:
            pat_norm = os.path.normpath(pat).lower()
            if pat_norm in path_norm:
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM files")
            count, total_bytes = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) FROM drives")
            drives_count = cursor.fetchone()[0]

            cursor.execute("SELECT MAX(last_sync_time) FROM drives")
            last_sync = cursor.fetchone()[0] or 0.0

            return {
                "total_files": count,
                "total_bytes": total_bytes,
                "drives_count": drives_count,
                "last_sync_time": last_sync,
            }
        finally:
            conn.close()

    def set_metadata(self, key: str, value: str):
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO metadata (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """, (key, value))
                conn.commit()
            finally:
                conn.close()

    def get_metadata(self, key: str, default: Optional[str] = None) -> Optional[str]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return default
        finally:
            conn.close()
