"""
Findora - High-Performance Windows Filename Search
Central Entry Point
"""

import sys
import os
import argparse
import time

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import FindoraApp, FastRetrivalApp
from tree import printTree


def run_cli_mode(app: FindoraApp):
    """Fallback interactive CLI mode."""
    print("========================================")
    print("        Findora CLI Mode                ")
    print("========================================")

    stats = app.storage.get_stats()
    print(f"Total Indexed Files: {stats['total_files']:,}")
    print(f"Total Indexed Size: {stats['total_bytes'] / (1024**3):.2f} GB")
    print("Hydrating in-memory B+ Tree...")
    app._hydrate_tree_from_storage()
    print("B+ Tree Ready!\n")

    while True:
        print("0: Exit")
        print("1: Print B+ Tree structure sample")
        print("2: Search for a file")
        print("3: Rescan all drives")
        choice = input("Choice: ").strip()

        if choice == "0":
            break
        elif choice == "1":
            printTree(app.tree)
        elif choice == "2":
            query = input("Enter filename to search: ").strip()
            if not query:
                continue
            t0 = time.time()
            results = app.tree.search_query(query, limit=50)
            t_search = time.time() - t0
            print(f"\n--- Found {len(results)} matches in {t_search * 1000:.2f} ms ---")
            for filename, paths in results:
                print(f"\nFile: {filename}")
                for p in paths:
                    print(f"   -> {p}")
            print()
        elif choice == "3":
            print("Scanning all local drives...")
            res = app.scanner.scan_all_drives()
            app.queue_manager.wait_empty()
            print(f"Scan complete: {res['total_files']} files indexed in {res['duration_seconds']:.2f}s.")


def main():
    parser = argparse.ArgumentParser(description="Findora - Windows Filename Search")
    parser.add_argument("--background", action="store_true", help="Launch minimized to system tray (for Windows autostart)")
    parser.add_argument("--rescan", action="store_true", help="Trigger a full re-index of all local drives")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode without GUI")
    parser.add_argument("--ipc", action="store_true", help="Run in local IPC server mode for C# WPF frontend")
    parser.add_argument("--db", type=str, default=None, help="Custom database file path")

    args = parser.parse_args()

    if args.ipc:
        from ipc_server import FindoraIpcServer
        server = FindoraIpcServer(db_path=args.db)
        server.run_loop()
    elif args.cli:
        app = FindoraApp(db_path=args.db)
        run_cli_mode(app)
    else:
        app = FindoraApp(db_path=args.db)
        app.start(background=args.background)


if __name__ == "__main__":
    main()
