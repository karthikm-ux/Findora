import os
import threading
import time
from typing import Dict, Optional, List, Callable, Any

try:
    import win32file
    import win32con
    import win32event
    import pywintypes
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

from queue_manager import IndexMutationQueue
from storage import StorageManager


class DriveWatcher:
    """
    Watches a single drive or folder root for filesystem events in real-time
    using Windows ReadDirectoryChangesW with overlapped I/O and graceful cancellation.
    """

    BUFFER_SIZE = 64 * 1024  # 64 KB buffer

    def __init__(
        self,
        root_path: str,
        queue_manager: IndexMutationQueue,
        storage: StorageManager,
        on_event: Optional[Callable[[str, str], None]] = None,
    ):
        self.root_path = os.path.abspath(root_path)
        self.drive_letter = os.path.splitdrive(self.root_path)[0].upper() + "\\"
        self.queue_manager = queue_manager
        self.storage = storage
        self.on_event = on_event

        self._stop_event = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self._h_dir = None
        self._last_error = ""

    def start(self):
        if not WIN32_AVAILABLE:
            self._last_error = "pywin32 not available on this system."
            return

        if self._is_running:
            return

        self._is_running = True
        self._stop_event = win32event.CreateEvent(None, True, False, None)
        self._thread = threading.Thread(
            target=self._watch_loop,
            name=f"FastRetrival-Watcher-{self.drive_letter[0]}",
            daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0):
        if not self._is_running:
            return

        self._is_running = False
        if self._stop_event:
            win32event.SetEvent(self._stop_event)

        if self._h_dir:
            try:
                win32file.CancelIo(self._h_dir)
            except Exception:
                pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        if self._h_dir:
            try:
                win32file.CloseHandle(self._h_dir)
            except Exception:
                pass
            self._h_dir = None

    def is_running(self) -> bool:
        return self._is_running

    def get_last_error(self) -> str:
        return self._last_error

    def _watch_loop(self):
        try:
            self._h_dir = win32file.CreateFileW(
                self.root_path,
                win32con.GENERIC_READ,
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
                None,
                win32con.OPEN_EXISTING,
                win32con.FILE_FLAG_BACKUP_SEMANTICS | win32con.FILE_FLAG_OVERLAPPED,
                None
            )
        except Exception as e:
            self._last_error = f"Failed to open drive handle: {e}"
            self._is_running = False
            return

        overlapped = pywintypes.OVERLAPPED()
        overlapped.hEvent = win32event.CreateEvent(None, True, False, None)
        buffer = win32file.AllocateReadBuffer(self.BUFFER_SIZE)

        old_rename_path: Optional[str] = None
        old_rename_name: Optional[str] = None

        while self._is_running:
            try:
                win32file.ReadDirectoryChangesW(
                    self._h_dir,
                    buffer,
                    True,  # recursive watch subtree
                    win32con.FILE_NOTIFY_CHANGE_FILE_NAME |
                    win32con.FILE_NOTIFY_CHANGE_DIR_NAME |
                    win32con.FILE_NOTIFY_CHANGE_LAST_WRITE |
                    win32con.FILE_NOTIFY_CHANGE_SIZE,
                    overlapped
                )

                # Wait for change event or stop event
                rc = win32event.WaitForMultipleObjects(
                    [overlapped.hEvent, self._stop_event],
                    False,  # Wait for any
                    win32event.INFINITE
                )

                if rc == 1 or not self._is_running:
                    # Stop event signaled
                    win32file.CancelIo(self._h_dir)
                    break

                # Changes occurred
                n_bytes = win32file.GetOverlappedResult(self._h_dir, overlapped, True)
                if n_bytes > 0:
                    results = win32file.FILE_NOTIFY_INFORMATION(buffer, n_bytes)
                    exclusions = [e["pattern"] for e in self.storage.get_exclusions()]

                    for action, rel_path in results:
                        full_path = os.path.normpath(os.path.join(self.root_path, rel_path))

                        if self.storage.is_path_excluded(full_path, exclusions):
                            continue

                        filename = os.path.basename(full_path)

                        if action in (1, 3):  # ADDED (1) or MODIFIED (3)
                            if os.path.isfile(full_path):
                                try:
                                    stat = os.stat(full_path)
                                    self.queue_manager.enqueue_add(
                                        full_path=full_path,
                                        filename=filename,
                                        size_bytes=stat.st_size,
                                        mtime=stat.st_mtime,
                                        drive=self.drive_letter
                                    )
                                    if self.on_event:
                                        self.on_event("ADD", full_path)
                                except (PermissionError, OSError):
                                    pass
                            elif os.path.isdir(full_path):
                                # Newly added directory - scan items inside
                                self._scan_new_directory(full_path, exclusions)

                        elif action == 2:  # REMOVED (2)
                            self.queue_manager.enqueue_remove(full_path, filename)
                            if self.on_event:
                                self.on_event("REMOVE", full_path)

                        elif action == 4:  # RENAMED_OLD_NAME (4)
                            old_rename_path = full_path
                            old_rename_name = filename

                        elif action == 5:  # RENAMED_NEW_NAME (5)
                            if old_rename_path and old_rename_name:
                                if os.path.isfile(full_path):
                                    try:
                                        stat = os.stat(full_path)
                                        self.queue_manager.enqueue_rename(
                                            old_path=old_rename_path,
                                            old_name=old_rename_name,
                                            new_path=full_path,
                                            new_name=filename,
                                            size_bytes=stat.st_size,
                                            mtime=stat.st_mtime,
                                            drive=self.drive_letter
                                        )
                                        if self.on_event:
                                            self.on_event("RENAME", f"{old_rename_path} -> {full_path}")
                                    except (PermissionError, OSError):
                                        pass
                                old_rename_path = None
                                old_rename_name = None

                    # Update last sync time
                    self.storage.update_drive(self.drive_letter, last_sync_time=time.time())

            except Exception as e:
                if not self._is_running:
                    break
                self._last_error = str(e)
                time.sleep(0.5)

    def _scan_new_directory(self, dir_path: str, exclusions: List[str]):
        """Helper to index files when a new directory is pasted or extracted."""
        batch = []
        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    if entry.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(entry.path)):
                        continue
                    if self.storage.is_path_excluded(entry.path, exclusions):
                        continue
                    if entry.is_file():
                        try:
                            stat = entry.stat()
                            batch.append({
                                "drive": self.drive_letter,
                                "full_path": entry.path,
                                "filename": entry.name,
                                "filename_lower": entry.name.lower(),
                                "extension": os.path.splitext(entry.name)[1].lower(),
                                "size_bytes": stat.st_size,
                                "mtime": stat.st_mtime,
                                "indexed_at": time.time(),
                            })
                        except (PermissionError, OSError):
                            pass
                    elif entry.is_dir():
                        self._scan_new_directory(entry.path, exclusions)
            if batch:
                self.queue_manager.enqueue_batch_add(batch)
        except (PermissionError, OSError):
            pass


class WatcherManager:
    """
    Coordinates drive watchers across all active drives.
    """

    def __init__(
        self,
        queue_manager: IndexMutationQueue,
        storage: StorageManager,
        on_event: Optional[Callable[[str, str], None]] = None,
    ):
        self.queue_manager = queue_manager
        self.storage = storage
        self.on_event = on_event
        self.watchers: Dict[str, DriveWatcher] = {}
        self._lock = threading.Lock()

    def start_watching_drives(self, drive_letters: List[str]):
        with self._lock:
            for drive in drive_letters:
                drive_norm = drive.upper()
                if not drive_norm.endswith("\\"):
                    drive_norm += "\\"
                if drive_norm not in self.watchers:
                    watcher = DriveWatcher(
                        root_path=drive_norm,
                        queue_manager=self.queue_manager,
                        storage=self.storage,
                        on_event=self.on_event
                    )
                    watcher.start()
                    self.watchers[drive_norm] = watcher
                    self.storage.update_drive(drive_norm, is_monitored=1)

    def stop_all(self):
        with self._lock:
            for watcher in self.watchers.values():
                watcher.stop()
            self.watchers.clear()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                drive: {
                    "running": w.is_running(),
                    "last_error": w.get_last_error(),
                }
                for drive, w in self.watchers.items()
            }
