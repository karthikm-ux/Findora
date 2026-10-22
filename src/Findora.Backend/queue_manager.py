import queue
import threading
import time
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Tuple

from tree import BplusTree
from storage import StorageManager


class MutationType(Enum):
    ADD = "ADD"
    BATCH_ADD = "BATCH_ADD"
    REMOVE = "REMOVE"
    BATCH_REMOVE = "BATCH_REMOVE"
    RENAME = "RENAME"
    CLEAR = "CLEAR"
    FLUSH = "FLUSH"


class IndexMutationQueue:
    """
    Serializes all mutations to the in-memory B+ Tree and persistent SQLite storage
    through a single-threaded update worker. This guarantees absolute thread-safety
    and eliminates race conditions during filesystem scans and live monitoring.
    """

    def __init__(
        self,
        tree: BplusTree,
        storage: StorageManager,
        on_mutation_applied: Optional[Callable[[str, int], None]] = None,
        batch_flush_interval: float = 0.25,
        max_batch_size: int = 1000,
    ):
        self.tree = tree
        self.storage = storage
        self.on_mutation_applied = on_mutation_applied
        self.batch_flush_interval = batch_flush_interval
        self.max_batch_size = max_batch_size

        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._pending_adds: List[Dict[str, Any]] = []
        self._pending_removes: List[Tuple[str, str]] = []  # (full_path, filename)
        self._lock = threading.Lock()
        self._processed_count = 0

    def start(self):
        with self._lock:
            if not self._running:
                self._running = True
                self._worker_thread = threading.Thread(
                    target=self._worker_loop, name="FastRetrival-MutationWorker", daemon=True
                )
                self._worker_thread.start()

    def stop(self, timeout: float = 5.0):
        with self._lock:
            if self._running:
                self._running = False
                self._queue.put(None)  # Sentinel
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    def enqueue_add(self, full_path: str, filename: str, size_bytes: int = 0, mtime: float = 0.0, drive: str = ""):
        self._queue.put((MutationType.ADD, {
            "full_path": full_path,
            "filename": filename,
            "size_bytes": size_bytes,
            "mtime": mtime,
            "drive": drive
        }))

    def enqueue_batch_add(self, records: List[Dict[str, Any]]):
        if records:
            self._queue.put((MutationType.BATCH_ADD, records))

    def enqueue_remove(self, full_path: str, filename: str):
        self._queue.put((MutationType.REMOVE, {
            "full_path": full_path,
            "filename": filename
        }))

    def enqueue_batch_remove(self, items: List[Tuple[str, str]]):
        if items:
            self._queue.put((MutationType.BATCH_REMOVE, items))

    def enqueue_rename(
        self,
        old_path: str,
        old_name: str,
        new_path: str,
        new_name: str,
        size_bytes: int = 0,
        mtime: float = 0.0,
        drive: str = ""
    ):
        self._queue.put((MutationType.RENAME, {
            "old_path": old_path,
            "old_name": old_name,
            "new_path": new_path,
            "new_name": new_name,
            "size_bytes": size_bytes,
            "mtime": mtime,
            "drive": drive
        }))

    def flush(self, timeout: Optional[float] = 10.0) -> bool:
        """
        Blocks until all queued mutations and pending batches are committed to storage and tree.
        """
        done_event = threading.Event()
        self._queue.put((MutationType.FLUSH, done_event))
        return done_event.wait(timeout=timeout)

    def wait_empty(self, timeout: Optional[float] = 10.0) -> bool:
        """Blocks until all queued mutations and batches have been fully committed."""
        return self.flush(timeout=timeout)

    def get_processed_count(self) -> int:
        return self._processed_count

    def _flush_pending(self):
        if self._pending_adds:
            adds = self._pending_adds
            self._pending_adds = []
            # 1. Update SQLite
            self.storage.upsert_files_batch(adds)
            # 2. Update B+ Tree
            for item in adds:
                self.tree.insert(item["filename"], item["full_path"])
            self._processed_count += len(adds)

        if self._pending_removes:
            removes = self._pending_removes
            self._pending_removes = []
            paths_to_delete = [p for p, _ in removes]
            self.storage.delete_files_batch(paths_to_delete)
            for path, name in removes:
                self.tree.remove(name, path)
            self._processed_count += len(removes)

        if self.on_mutation_applied:
            try:
                self.on_mutation_applied("MUTATION_FLUSH", self._processed_count)
            except Exception:
                pass

    def _worker_loop(self):
        last_flush_time = time.time()

        while self._running:
            try:
                # Wait for up to batch_flush_interval
                timeout = max(0.01, self.batch_flush_interval - (time.time() - last_flush_time))
                item = self._queue.get(timeout=timeout)

                if item is None:
                    # Sentinel received
                    self._queue.task_done()
                    break

                mutation_type, payload = item

                if mutation_type == MutationType.ADD:
                    self._pending_adds.append(payload)
                elif mutation_type == MutationType.BATCH_ADD:
                    self._pending_adds.extend(payload)
                elif mutation_type == MutationType.REMOVE:
                    self._pending_removes.append((payload["full_path"], payload["filename"]))
                elif mutation_type == MutationType.BATCH_REMOVE:
                    self._pending_removes.extend(payload)
                elif mutation_type == MutationType.FLUSH:
                    self._flush_pending()
                    last_flush_time = time.time()
                    if payload and hasattr(payload, "set"):
                        payload.set()
                elif mutation_type == MutationType.RENAME:
                    # Flush pending first to keep ordering consistent
                    self._flush_pending()
                    # Apply remove old
                    self.tree.remove(payload["old_name"], payload["old_path"])
                    self.storage.delete_file(payload["old_path"])
                    # Apply add new
                    self.tree.insert(payload["new_name"], payload["new_path"])
                    self.storage.upsert_file(
                        full_path=payload["new_path"],
                        filename=payload["new_name"],
                        size_bytes=payload.get("size_bytes", 0),
                        mtime=payload.get("mtime", 0.0),
                        drive=payload.get("drive", "")
                    )
                    self._processed_count += 2
                elif mutation_type == MutationType.CLEAR:
                    self._flush_pending()
                    self.tree = BplusTree(self.tree.root.order)
                    # Note: does not wipe DB unless requested

                self._queue.task_done()

                # Flush if max batch size reached
                if len(self._pending_adds) >= self.max_batch_size or len(self._pending_removes) >= self.max_batch_size:
                    self._flush_pending()
                    last_flush_time = time.time()

            except queue.Empty:
                # Timed out, flush any pending items
                if self._pending_adds or self._pending_removes:
                    self._flush_pending()
                    last_flush_time = time.time()

        # On exit, flush remaining
        self._flush_pending()
