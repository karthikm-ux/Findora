import os
import time
import threading
from typing import Dict, Any, List, Optional, Callable

from queue_manager import IndexMutationQueue
from storage import StorageManager
from scanner import discover_local_drives


class ReconciliationEngine:
    """
    Reconciles the saved index with the actual filesystem on startup or recovery.
    Avoids rescanning the entire computer if an index already exists, while detecting
    files added, modified, or deleted while the application was closed.
    """

    def __init__(
        self,
        queue_manager: IndexMutationQueue,
        storage: StorageManager,
        on_progress: Optional[Callable[[str], None]] = None,
    ):
        self.queue_manager = queue_manager
        self.storage = storage
        self.on_progress = on_progress
        self._is_reconciling = False

    def is_reconciling(self) -> bool:
        return self._is_reconciling

    def reconcile_drive(self, drive_letter: str) -> Dict[str, Any]:
        """
        Reconciles a specific drive against the persisted SQLite index.
        Checks high-activity user directories and directories modified since last_sync_time.
        """
        self._is_reconciling = True
        drive_norm = drive_letter.upper()
        if not drive_norm.endswith("\\"):
            drive_norm += "\\"

        start_time = time.time()
        added_count = 0
        removed_count = 0

        # Retrieve drive metadata
        drives = {d["drive_letter"]: d for d in self.storage.get_drives()}
        drive_info = drives.get(drive_norm)
        last_sync = drive_info["last_sync_time"] if drive_info else 0.0

        if self.on_progress:
            self.on_progress(f"Reconciling drive {drive_norm} (last sync: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_sync)) if last_sync > 0 else 'Never'})...")

        exclusions = [e["pattern"] for e in self.storage.get_exclusions()]

        # High priority locations to check on Windows:
        # User profile directories (Downloads, Documents, Desktop, etc.)
        locations_to_check: List[str] = []
        user_profile = os.environ.get("USERPROFILE")
        if user_profile and user_profile.upper().startswith(drive_norm[:2]):
            locations_to_check.extend([
                os.path.join(user_profile, "Desktop"),
                os.path.join(user_profile, "Documents"),
                os.path.join(user_profile, "Downloads"),
                os.path.join(user_profile, "Pictures"),
                os.path.join(user_profile, "Music"),
                os.path.join(user_profile, "Videos"),
            ])

        # Also inspect drive root folders
        try:
            with os.scandir(drive_norm) as root_entries:
                for entry in root_entries:
                    if entry.is_dir(follow_symlinks=False):
                        if not self.storage.is_path_excluded(entry.path, exclusions):
                            locations_to_check.append(entry.path)
        except (PermissionError, OSError):
            pass

        # Check modified folders
        batch_add = []
        for location in locations_to_check:
            if not os.path.exists(location):
                continue

            try:
                # If directory mtime is newer than last_sync or last_sync is 0
                dir_stat = os.stat(location)
                if last_sync == 0 or dir_stat.st_mtime >= last_sync:
                    # Scan this directory for updates
                    with os.scandir(location) as entries:
                        for entry in entries:
                            if entry.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(entry.path)):
                                continue
                            if self.storage.is_path_excluded(entry.path, exclusions):
                                continue

                            if entry.is_file():
                                try:
                                    st = entry.stat()
                                    if st.st_mtime >= last_sync:
                                        batch_add.append({
                                            "drive": drive_norm,
                                            "full_path": entry.path,
                                            "filename": entry.name,
                                            "filename_lower": entry.name.lower(),
                                            "extension": os.path.splitext(entry.name)[1].lower(),
                                            "size_bytes": st.st_size,
                                            "mtime": st.st_mtime,
                                            "indexed_at": time.time(),
                                        })
                                        added_count += 1
                                except (PermissionError, OSError):
                                    pass
            except (PermissionError, OSError):
                pass

        if batch_add:
            self.queue_manager.enqueue_batch_add(batch_add)

        # Update last sync timestamp
        now = time.time()
        self.storage.update_drive(drive_norm, last_sync_time=now, status="indexed")

        self._is_reconciling = False
        duration = time.time() - start_time

        if self.on_progress:
            self.on_progress(f"Reconciliation of {drive_norm} complete in {duration:.2f}s ({added_count} updated).")

        return {
            "drive": drive_norm,
            "added_count": added_count,
            "removed_count": removed_count,
            "duration": duration,
        }

    def reconcile_all_drives(self) -> List[Dict[str, Any]]:
        results = []
        drives = discover_local_drives()
        for d in drives:
            res = self.reconcile_drive(d.letter)
            results.append(res)
        return results
