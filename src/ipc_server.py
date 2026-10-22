"""
FastRetrival - Local IPC Server
Exposes the Python indexing and search engine over a private, authenticated
standard I/O (stdin/stdout) JSON protocol.
"""

import sys
import os
import json
import time
import threading
import subprocess
from typing import Dict, Any, Optional

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from tree import BplusTree
from storage import StorageManager
from queue_manager import IndexMutationQueue
from scanner import Scanner, discover_local_drives
from watcher import WatcherManager
from reconciler import ReconciliationEngine
from system_integration import SingleInstanceChecker


class FindoraIpcServer:
    """
    Supervises the B+ Tree, SQLite store, filesystem watchers, and background scanner,
    and serves bounded JSON-RPC-style requests over stdin/stdout.
    """

    PROTOCOL_VERSION = "1.0"

    def __init__(self, db_path: Optional[str] = None):
        self.single_instance = SingleInstanceChecker(mutex_name="Findora_Backend_Mutex_2026")
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

        self._is_running = False
        self._initial_load_done = False
        self._write_lock = threading.Lock()

    def start_engine(self):
        """Starts mutation queue and launches hydration & watchers asynchronously."""
        self.queue_manager.start()
        threading.Thread(target=self._background_start_engine, daemon=True).start()

    def _background_start_engine(self):
        self._hydrate_tree()
        self._send_event("ready", {
            "version": self.PROTOCOL_VERSION,
            "pid": os.getpid(),
            "total_files": self.tree.count_total_files()
        })

        # Start drive monitoring and reconciliation in background
        drives = self.storage.get_drives()
        stats = self.storage.get_stats()
        if not drives or stats["total_files"] == 0:
            threading.Thread(target=self._initial_scan_worker, daemon=True).start()
        else:
            self._start_watchers()
            threading.Thread(target=self._startup_reconcile_worker, daemon=True).start()

    def _hydrate_tree(self):
        for chunk in self.storage.load_all_records_for_tree(chunk_size=10000):
            for filename, full_path in chunk:
                self.tree.insert(filename, full_path)
        self._initial_load_done = True

    def _start_watchers(self):
        drives = self.storage.get_drives()
        letters = [d["drive_letter"] for d in drives if d.get("status") in ("indexed", "ready")]
        if not letters:
            discovered = discover_local_drives()
            letters = [d.letter for d in discovered]
        self.watcher_manager.start_watching_drives(letters)

    def _initial_scan_worker(self):
        self.scanner.scan_all_drives()
        self.queue_manager.wait_empty()
        discovered = discover_local_drives()
        self.watcher_manager.start_watching_drives([d.letter for d in discovered])

    def _startup_reconcile_worker(self):
        self.reconciler.reconcile_all_drives()
        self.queue_manager.wait_empty()

    def _on_scanner_progress(self, progress: Dict[str, Any]):
        self._send_event("scan_progress", progress)

    def _on_reconciler_progress(self, message: str):
        self._send_event("reconcile_progress", {"message": message})

    def _on_watcher_event(self, action: str, path: str):
        pass

    def _on_mutation_applied(self, mutation_type: str, total_count: int):
        pass

    def _send_response(self, req_id: Any, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        msg = {
            "id": req_id,
            "result": result,
            "error": error
        }
        raw = json.dumps(msg, ensure_ascii=True)
        with self._write_lock:
            sys.stdout.write(raw + "\n")
            sys.stdout.flush()

    def _send_event(self, event_name: str, data: Dict[str, Any]):
        msg = {
            "event": event_name,
            "data": data
        }
        raw = json.dumps(msg, ensure_ascii=True)
        with self._write_lock:
            sys.stdout.write(raw + "\n")
            sys.stdout.flush()

    def handle_request(self, raw_line: str):
        """Dispatches a single JSON line request."""
        line = raw_line.strip()
        if not line:
            return

        try:
            req = json.loads(line)
        except Exception as e:
            self._send_response(None, error=f"Invalid JSON request: {e}")
            return

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        try:
            if method == "ping":
                self._send_response(req_id, result={"pong": True, "server_time": time.time(), "protocol": self.PROTOCOL_VERSION})

            elif method == "search":
                query = str(params.get("query", "")).strip()
                limit = min(int(params.get("limit", 10)), 100)
                if not query:
                    self._send_response(req_id, result={
                        "query": "",
                        "items": [],
                        "total_matches": 0,
                        "index_ms": 0.0,
                        "meta_ms": 0.0,
                        "total_ms": 0.0,
                        "search_ms": 0.0
                    })
                    return

                t0 = time.perf_counter()
                matches = self.tree.search_query(query, limit=limit)
                index_ms = (time.perf_counter() - t0) * 1000

                t_meta = time.perf_counter()
                all_paths = [p for _, paths in matches for p in paths]
                meta_dict = self.storage.get_files_metadata_batch(all_paths)
                meta_ms = (time.perf_counter() - t_meta) * 1000

                items = []
                for fname, full_path in [(fn, p) for fn, paths in matches for p in paths][:limit]:
                    m = meta_dict.get(full_path, {})
                    items.append({
                        "filename": fname,
                        "full_path": full_path,
                        "size_bytes": m.get("size_bytes", 0),
                        "mtime": m.get("mtime", 0.0),
                        "extension": m.get("extension", os.path.splitext(fname)[1]).lower()
                    })
                total_ms = (time.perf_counter() - t0) * 1000

                self._send_response(req_id, result={
                    "query": query,
                    "items": items,
                    "total_matches": len(items),
                    "index_ms": round(index_ms, 2),
                    "meta_ms": round(meta_ms, 2),
                    "total_ms": round(total_ms, 2),
                    "search_ms": round(total_ms, 2)
                })

            elif method == "status":
                stats = self.storage.get_stats()
                drives = self.storage.get_drives()
                self._send_response(req_id, result={
                    "stats": stats,
                    "drives": drives,
                    "is_scanning": self.scanner.is_scanning(),
                    "is_reconciling": self.reconciler.is_reconciling(),
                    "tree_files_loaded": self.tree.count_total_files()
                })

            elif method == "rescan":
                if not self.scanner.is_scanning():
                    threading.Thread(target=self._initial_scan_worker, daemon=True).start()
                    self._send_response(req_id, result={"started": True, "message": "Rescan started"})
                else:
                    self._send_response(req_id, result={"started": False, "message": "Scan already in progress"})

            elif method == "reveal":
                path = params.get("path", "")
                if path and os.path.exists(path):
                    norm = os.path.normpath(path)
                    try:
                        subprocess.Popen(f'explorer.exe /select,"{norm}"')
                        self._send_response(req_id, result={"revealed": True, "path": path})
                    except Exception as e:
                        self._send_response(req_id, error=f"Failed to launch Explorer: {e}")
                elif path:
                    folder = os.path.dirname(path)
                    if os.path.exists(folder):
                        try:
                            os.startfile(folder)
                            self._send_response(req_id, result={"revealed": True, "path": folder})
                        except Exception as e:
                            self._send_response(req_id, error=f"Failed to open folder: {e}")
                    else:
                        self._send_response(req_id, error=f"Path not found: {path}")
                else:
                    self._send_response(req_id, error="Missing path parameter")

            elif method == "open":
                path = params.get("path", "")
                if path and os.path.exists(path):
                    try:
                        os.startfile(os.path.normpath(path))
                        self._send_response(req_id, result={"opened": True, "path": path})
                    except Exception as e:
                        self._send_response(req_id, error=f"Failed to open item: {e}")
                else:
                    self._send_response(req_id, error=f"File not found: {path}")

            elif method == "exclusions_get":
                exclusions = self.storage.get_exclusions()
                self._send_response(req_id, result={"exclusions": exclusions})

            elif method == "exclusions_add":
                pattern = params.get("pattern", "")
                if pattern:
                    self.storage.add_exclusion(pattern)
                    self._send_response(req_id, result={"added": True, "pattern": pattern})
                else:
                    self._send_response(req_id, error="Empty exclusion pattern")

            elif method == "exclusions_remove":
                pattern = params.get("pattern", "")
                if pattern:
                    self.storage.remove_exclusion(pattern)
                    self._send_response(req_id, result={"removed": True, "pattern": pattern})
                else:
                    self._send_response(req_id, error="Empty exclusion pattern")

            elif method == "shutdown":
                self._send_response(req_id, result={"shutdown": True})
                self.stop()
                sys.exit(0)

            else:
                self._send_response(req_id, error=f"Unknown method '{method}'")

        except Exception as e:
            self._send_response(req_id, error=f"Method execution error: {e}")

    def run_loop(self):
        """Runs the main stdin message pump until EOF or shutdown."""
        self._is_running = True
        self.start_engine()

        # Emit started event immediately so supervisor knows stdin is listening
        self._send_event("started", {
            "version": self.PROTOCOL_VERSION,
            "pid": os.getpid()
        })

        try:
            for line in sys.stdin:
                if not self._is_running:
                    break
                self.handle_request(line)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self.stop()

    def stop(self):
        self._is_running = False
        try:
            self.scanner.cancel()
        except Exception:
            pass
        try:
            self.watcher_manager.stop_all()
        except Exception:
            pass
        try:
            self.queue_manager.stop()
        except Exception:
            pass
        try:
            self.single_instance.cleanup()
        except Exception:
            pass


# Compatibility alias
FastRetrivalIpcServer = FindoraIpcServer


if __name__ == "__main__":
    server = FindoraIpcServer()
    server.run_loop()
