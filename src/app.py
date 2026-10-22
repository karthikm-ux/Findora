import os
import sys
import time
import threading
from typing import Optional, List, Dict, Any
import tkinter as tk

from tree import BplusTree
from storage import StorageManager
from queue_manager import IndexMutationQueue
from scanner import Scanner, discover_local_drives
from watcher import WatcherManager
from reconciler import ReconciliationEngine
from system_integration import HotkeyListener, TrayIconManager, SingleInstanceChecker
from gui import GlassmorphismSearchWidget, DriveStatusDialog, SettingsDialog


class FindoraApp:
    """
    Main application controller that wires together:
    - Custom in-memory B+ Tree index
    - SQLite persistent storage
    - Serialized mutation queue
    - Automatic drive discovery and resilient scanner
    - Real-time ReadDirectoryChangesW filesystem watchers
    - Offline startup reconciler
    - Windows 11 Glassmorphism Search Widget (Idle glowing bubble + Expanded search bar & results)
    - System Tray icon and Global Hotkey listener (Alt+Space and Ctrl+Alt+F)
    """

    def __init__(self, db_path: Optional[str] = None):
        self.single_instance = SingleInstanceChecker()

        self.tree = BplusTree(order=32)
        self.storage = StorageManager(db_path)
        self.queue_manager = IndexMutationQueue(
            tree=self.tree,
            storage=self.storage,
            on_mutation_applied=self._on_mutation_applied,
            batch_flush_interval=0.2,
            max_batch_size=1000
        )
        self.scanner = Scanner(
            queue_manager=self.queue_manager,
            storage=self.storage,
            on_progress=self._on_scanner_progress
        )
        self.watcher_manager = WatcherManager(
            queue_manager=self.queue_manager,
            storage=self.storage,
            on_event=self._on_watcher_event
        )
        self.reconciler = ReconciliationEngine(
            queue_manager=self.queue_manager,
            storage=self.storage,
            on_progress=self._on_reconciler_progress
        )

        self.root: Optional[tk.Tk] = None
        self.search_widget: Optional[GlassmorphismSearchWidget] = None
        self.hotkey_listener: Optional[HotkeyListener] = None
        self.tray_manager: Optional[TrayIconManager] = None

        self._is_shutting_down = False
        self._initial_load_done = False

    def start(self, background: bool = False):
        """
        Starts the application.
        If an instance is already running, brings it to front and exits.
        If background is True, keeps the search bar idle on launch.
        """
        # 1. Enforce single instance
        if self.single_instance.is_already_running():
            print("Findora is already running. Revealing search widget...")
            self.single_instance.notify_existing_instance()
            sys.exit(0)

        # 2. Start mutation queue worker
        self.queue_manager.start()

        # 3. Hydrate in-memory B+ Tree from persistent database
        self._hydrate_tree_from_storage()

        # 4. Create root Tkinter window (hidden)
        self.root = tk.Tk()
        self.root.withdraw()

        # 5. Initialize Windows 11 Glassmorphism Search Widget
        self.search_widget = GlassmorphismSearchWidget(
            parent=self.root,
            app_core=self,
            on_open_settings=self.open_settings,
            on_status=self.open_status,
            on_rescan=self.trigger_rescan,
            on_exit=self.shutdown
        )

        # 6. Initialize global hotkeys (Alt+Space and Ctrl+Alt+F) and system tray icon
        self.hotkey_listener = HotkeyListener(callback=self._on_hotkey_triggered)
        self.hotkey_listener.start()

        self.tray_manager = TrayIconManager(
            on_open_search=self.show_search,
            on_toggle_floating_icon=self.toggle_search,
            on_rescan=self.trigger_rescan,
            on_status=self.open_status,
            on_settings=self.open_settings,
            on_exit=self.shutdown
        )
        self.tray_manager.start()

        # 7. Check if initial scan or reconciliation is needed
        drives = self.storage.get_drives()
        stats = self.storage.get_stats()
        if not drives or stats["total_files"] == 0:
            # First launch: automatically scan eligible drives in background
            threading.Thread(target=self._initial_scan_worker, daemon=True).start()
        else:
            # Subsequent launches: start watchers immediately and reconcile offline changes
            self._start_watchers_for_indexed_drives()
            threading.Thread(target=self._startup_reconcile_worker, daemon=True).start()

        # 8. Widget presentation
        if not background:
            self.show_search()

        # 9. Run Tkinter event loop
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.shutdown()

    def show_search(self):
        if self.search_widget and self.root:
            self.root.after(0, self.search_widget.expand_search)

    def hide_search(self):
        if self.search_widget and self.root:
            self.root.after(0, self.search_widget.collapse_to_idle)

    def toggle_search(self):
        if self.search_widget and self.root:
            self.root.after(0, self.search_widget.toggle_widget)

    def open_settings(self):
        if self.root:
            SettingsDialog(
                parent=self.root,
                storage=self.storage,
                on_corner_changed=self._on_desktop_corner_changed
            )

    def _on_desktop_corner_changed(self, new_corner: str):
        if self.search_widget and hasattr(self.search_widget, "idle_widget"):
            self.search_widget.idle_widget.set_corner(new_corner)

    def open_status(self):
        if self.root:
            DriveStatusDialog(
                parent=self.root,
                storage=self.storage,
                scanner=self.scanner
            )

    def trigger_rescan(self):
        if self.scanner.is_scanning():
            return
        threading.Thread(target=self._rescan_worker, daemon=True).start()

    def trigger_reconcile(self):
        if self.reconciler.is_reconciling():
            return
        threading.Thread(target=self._startup_reconcile_worker, daemon=True).start()

    def shutdown(self):
        if self._is_shutting_down:
            return
        self._is_shutting_down = True

        if self.scanner.is_scanning():
            self.scanner.cancel()

        self.watcher_manager.stop_all()

        if self.hotkey_listener:
            self.hotkey_listener.stop()

        if self.tray_manager:
            self.tray_manager.stop()

        self.queue_manager.stop()

        self.single_instance.cleanup()

        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass

        sys.exit(0)

    def _hydrate_tree_from_storage(self):
        """Loads all existing persistent records into the B+ Tree."""
        for chunk in self.storage.load_all_records_for_tree(chunk_size=10000):
            for filename, full_path in chunk:
                self.tree.insert(filename, full_path)
        self._initial_load_done = True

    def _start_watchers_for_indexed_drives(self):
        drives = self.storage.get_drives()
        letters = [d["drive_letter"] for d in drives if d.get("status") in ("indexed", "ready")]
        if not letters:
            discovered = discover_local_drives()
            letters = [d.letter for d in discovered]
        self.watcher_manager.start_watching_drives(letters)

    def _initial_scan_worker(self):
        results = self.scanner.scan_all_drives()
        self.queue_manager.wait_empty()
        discovered = discover_local_drives()
        self.watcher_manager.start_watching_drives([d.letter for d in discovered])

    def _rescan_worker(self):
        self.scanner.scan_all_drives()
        self.queue_manager.wait_empty()

    def _startup_reconcile_worker(self):
        self.reconciler.reconcile_all_drives()
        self.queue_manager.wait_empty()

    def _on_scanner_progress(self, progress: Dict[str, Any]):
        pass

    def _on_reconciler_progress(self, message: str):
        pass

    def _on_watcher_event(self, action: str, path: str):
        pass

    def _on_mutation_applied(self, mutation_type: str, total_count: int):
        pass

    def _on_hotkey_triggered(self):
        if self.search_widget and self.root:
            self.root.after(0, self.search_widget.toggle_widget)


# Compatibility alias
FastRetrivalApp = FindoraApp
