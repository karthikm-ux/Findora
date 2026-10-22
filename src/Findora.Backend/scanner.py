import os
import shutil
import time
import threading
from typing import List, Dict, Any, Optional, Callable, Set

try:
    import win32api
    import win32file
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

from queue_manager import IndexMutationQueue
from storage import StorageManager


class DriveInfo:
    def __init__(self, letter: str, label: str, fs_type: str, total_bytes: int, free_bytes: int, is_fixed: bool):
        self.letter = letter.upper()  # e.g. "C:\\"
        self.label = label
        self.fs_type = fs_type
        self.total_bytes = total_bytes
        self.free_bytes = free_bytes
        self.is_fixed = is_fixed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drive_letter": self.letter,
            "label": self.label,
            "fs_type": self.fs_type,
            "total_bytes": self.total_bytes,
            "free_bytes": self.free_bytes,
            "is_fixed": self.is_fixed,
        }


def discover_local_drives() -> List[DriveInfo]:
    """
    Discovers all local fixed drives automatically on the Windows system.
    Returns a list of DriveInfo objects.
    """
    results: List[DriveInfo] = []

    if WIN32_AVAILABLE:
        try:
            drive_strings = win32api.GetLogicalDriveStrings().split("\000")[:-1]
            for drive in drive_strings:
                drive_type = win32file.GetDriveType(drive)
                # DRIVE_FIXED is 3
                is_fixed = (drive_type == win32file.DRIVE_FIXED)
                label = ""
                fs_type = ""
                try:
                    vol_info = win32api.GetVolumeInformation(drive)
                    label = vol_info[0] or ""
                    fs_type = vol_info[4] or ""
                except Exception:
                    pass

                total = 0
                free = 0
                try:
                    usage = shutil.disk_usage(drive)
                    total = usage.total
                    free = usage.free
                except Exception:
                    pass

                if is_fixed:
                    results.append(DriveInfo(
                        letter=drive,
                        label=label,
                        fs_type=fs_type,
                        total_bytes=total,
                        free_bytes=free,
                        is_fixed=is_fixed
                    ))
            return results
        except Exception:
            pass

    # Fallback if win32api is unavailable
    for letter_code in range(ord('A'), ord('Z') + 1):
        drive = f"{chr(letter_code)}:\\"
        if os.path.exists(drive):
            try:
                usage = shutil.disk_usage(drive)
                results.append(DriveInfo(
                    letter=drive,
                    label="Local Disk",
                    fs_type="NTFS",
                    total_bytes=usage.total,
                    free_bytes=usage.free,
                    is_fixed=True
                ))
            except Exception:
                pass

    return results


class Scanner:
    """
    Resilient whole-computer directory scanner.
    Safely traverses directories, bypasses junctions/symlinks, skips access-denied
    folders without crashing, respects exclusion lists, and batches mutations to
    the IndexMutationQueue with real-time progress callbacks.
    """

    def __init__(
        self,
        queue_manager: IndexMutationQueue,
        storage: StorageManager,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        batch_size: int = 500,
    ):
        self.queue_manager = queue_manager
        self.storage = storage
        self.on_progress = on_progress
        self.batch_size = batch_size

        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._is_scanning = False
        self.inaccessible_paths: List[str] = []
        self.total_scanned_files = 0
        self.total_scanned_dirs = 0

    def cancel(self):
        """Cancels an ongoing scan."""
        self._cancel_event.set()
        self._pause_event.set()

    def pause(self):
        """Pauses the scan."""
        self._pause_event.clear()

    def resume(self):
        """Resumes a paused scan."""
        self._pause_event.set()

    def is_scanning(self) -> bool:
        return self._is_scanning

    def scan_all_drives(self) -> Dict[str, Any]:
        """
        Discovers all eligible local drives and scans them sequentially.
        """
        self._cancel_event.clear()
        self._pause_event.set()
        self._is_scanning = True
        self.inaccessible_paths.clear()
        self.total_scanned_files = 0
        self.total_scanned_dirs = 0

        drives = discover_local_drives()
        start_time = time.time()

        for drive in drives:
            if self._cancel_event.is_set():
                break

            self.storage.update_drive(
                drive.letter,
                label=drive.label,
                fs_type=drive.fs_type,
                total_bytes=drive.total_bytes,
                free_bytes=drive.free_bytes,
                status="scanning"
            )

            try:
                self.scan_folder(drive.letter, drive_letter=drive.letter)
                self.storage.update_drive(
                    drive.letter,
                    status="indexed",
                    last_scan_time=time.time(),
                    last_sync_time=time.time(),
                    file_count=self.total_scanned_files,
                    error_message=""
                )
            except Exception as e:
                self.storage.update_drive(
                    drive.letter,
                    status="error",
                    error_message=str(e)
                )

        self._is_scanning = False
        duration = time.time() - start_time

        return {
            "total_files": self.total_scanned_files,
            "total_dirs": self.total_scanned_dirs,
            "inaccessible_paths": self.inaccessible_paths,
            "duration_seconds": duration,
            "cancelled": self._cancel_event.is_set()
        }

    def scan_folder(self, folder_path: str, drive_letter: Optional[str] = None):
        """
        Scans a specific folder or drive root recursively.
        """
        if drive_letter is None:
            drive_letter = os.path.splitdrive(folder_path)[0].upper() + "\\"

        exclusions = [e["pattern"] for e in self.storage.get_exclusions()]
        batch: List[Dict[str, Any]] = []
        start_time = time.time()
        last_report_time = start_time

        # Iterative stack-based directory traversal to avoid recursion limits
        dir_stack = [folder_path]

        while dir_stack:
            if self._cancel_event.is_set():
                break

            self._pause_event.wait()

            current_dir = dir_stack.pop()
            self.total_scanned_dirs += 1

            try:
                with os.scandir(current_dir) as entries:
                    for entry in entries:
                        if self._cancel_event.is_set():
                            break

                        try:
                            # 1. Skip junctions and symlinks to prevent infinite loops
                            is_symlink = entry.is_symlink()
                            is_junction = False
                            if hasattr(os.path, "isjunction"):
                                is_junction = os.path.isjunction(entry.path)

                            if is_symlink or is_junction:
                                continue

                            # 2. Check exclusion list
                            if self.storage.is_path_excluded(entry.path, exclusions):
                                continue

                            if entry.is_dir(follow_symlinks=False):
                                dir_stack.append(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                stat = entry.stat(follow_symlinks=False)
                                record = {
                                    "drive": drive_letter,
                                    "full_path": entry.path,
                                    "filename": entry.name,
                                    "filename_lower": entry.name.lower(),
                                    "extension": os.path.splitext(entry.name)[1].lower(),
                                    "size_bytes": stat.st_size,
                                    "mtime": stat.st_mtime,
                                    "indexed_at": time.time(),
                                }
                                batch.append(record)
                                self.total_scanned_files += 1

                                if len(batch) >= self.batch_size:
                                    self.queue_manager.enqueue_batch_add(batch)
                                    batch = []

                        except (PermissionError, OSError):
                            self.inaccessible_paths.append(entry.path)
                            continue

            except (PermissionError, OSError):
                self.inaccessible_paths.append(current_dir)
                continue

            # Periodic progress reporting every 0.25 seconds
            now = time.time()
            if now - last_report_time >= 0.25:
                rate = self.total_scanned_files / max(0.001, now - start_time)
                if self.on_progress:
                    try:
                        self.on_progress({
                            "files_scanned": self.total_scanned_files,
                            "dirs_scanned": self.total_scanned_dirs,
                            "current_dir": current_dir,
                            "rate_files_per_sec": rate,
                            "inaccessible_count": len(self.inaccessible_paths),
                        })
                    except Exception:
                        pass
                last_report_time = now

        # Flush any remaining items in the batch
        if batch:
            self.queue_manager.enqueue_batch_add(batch)
            batch = []

        # Final progress notification
        if self.on_progress:
            try:
                self.on_progress({
                    "files_scanned": self.total_scanned_files,
                    "dirs_scanned": self.total_scanned_dirs,
                    "current_dir": folder_path,
                    "rate_files_per_sec": self.total_scanned_files / max(0.001, time.time() - start_time),
                    "inaccessible_count": len(self.inaccessible_paths),
                    "done": True,
                })
            except Exception:
                pass
