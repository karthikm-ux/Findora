# Findora

Findora is a high-performance Windows filename-search application featuring a **Windows 11 glassmorphism floating search widget** and **automatic whole-computer indexing with minimal user interaction**.

It combines a modern **C# .NET 8 WPF** desktop frontend with a custom in-memory **B+ Tree** indexing engine, persistent SQLite storage, kernel-level live filesystem monitoring (`ReadDirectoryChangesW`), and standalone distribution capability.

---

## Key Features

1. **Windows 11 Glassmorphism Floating Search Widget**
   - Sleek, modern floating search panel near the center of the screen with frosted acrylic translucency, rounded corners, soft drop shadows, and subtle blue accent glows.
   - Smooth opening, closing, and selection animations.
   - Summoned instantly via global hotkey (**Ctrl + Alt + F**) or by clicking the desktop widget.
   - Arrow keys ($\uparrow$/$\downarrow$) navigate results with wrap-around selection.
   - **Enter** reveals the selected file in Windows File Explorer with the item highlighted.
   - **Shift+Enter** opens the file immediately in its default associated application.
   - **Escape** or clicking outside smoothly dismisses the search interface.

2. **Idle Desktop Magnifying-Glass Widget**
   - A compact, translucent floating circular disc docked unobtrusively in a desktop corner.
   - Designed with proper desktop layering (`HWND_NOTOPMOST` / `WS_EX_NOACTIVATE`) so it never covers normal application windows or steals focus.
   - Draggable across the desktop with smooth hover transitions.

3. **Dynamic Windows Shell File Icons**
   - Uses native `SHGetFileInfoW` to extract real Windows-associated file-type icons (Word, PowerPoint, Excel, PDF, code, executables, media, and folders) without hardcoding extension tables.
   - Memory-safe icon caching with automatic native handle cleanup (`DestroyIcon`).

4. **Custom B+ Tree In-Memory Search Engine**
   - High-fanout B+ Tree (order 32) indexing filename keys to multi-path value arrays.
   - Sub-millisecond prefix searches and substring matching across hundreds of thousands of files.
   - Full support for duplicate filenames across different paths and drives.

5. **Persistent SQLite File Catalog (`findora.db`)**
   - WAL (Write-Ahead Logging) mode with 32 MB cache for instantaneous hydration on subsequent launches.
   - Stored in stable per-user application data: `%LOCALAPPDATA%\Findora\findora.db`.
   - **Automatic Legacy Migration**: If upgrading from FastRetrival, seamlessly imports existing indexes without re-scanning or losing data.

6. **Real-Time Filesystem Monitoring & Reconciliation**
   - Monitors drives in real-time using Windows `ReadDirectoryChangesW` with overlapped I/O.
   - Serialized mutation worker queue prevents race conditions.
   - Offline startup reconciler compares directory modification timestamps against the last synchronization checkpoint.

7. **Zero-Dependency Distributable Windows Release**
   - Distributed as a standalone package in `dist/Findora/Findora.exe`.
   - Bundles the Python indexing worker into `backend/FindoraBackend.exe` via PyInstaller.
   - Runs cleanly on any modern Windows 10/11 system without requiring Python to be installed.

8. **Single-Instance Enforcement & Zero Orphan Processes**
   - Protected by named Windows Mutex (`Findora_WPF_SingleInstance_Mutex_2026`).
   - Duplicate launches bring the existing search window to the front and exit in under 1 second.
   - Clean shutdown terminates all background threads and watcher processes with zero orphan processes.

---

## Repository Structure

```
Findora/
├── Findora.sln                  # Main Visual Studio / .NET Solution
├── README.md                    # Project documentation
├── .gitignore                   # Git ignore specifications
├── LICENSE                      # Project license
├── src/
│   ├── Findora.Wpf/             # Modern C# .NET 8 WPF Frontend
│   │   ├── Findora.Wpf.csproj   # Compiles to Findora.exe
│   │   ├── App.xaml / .cs       # Application bootstrap & single-instance mutex
│   │   ├── Views/               # MainWindow.xaml & DesktopWidget.xaml
│   │   ├── Models/              # IpcMessages.cs & SearchResultItem.cs
│   │   └── Services/            # BackendSupervisor, FileIconService, HotkeyManager
│   ├── Findora.Backend/         # Python Indexing & Search Engine
│   │   ├── main.py              # Backend entry point (--ipc, --cli)
│   │   ├── ipc_server.py        # NDJSON JSON-RPC IPC server
│   │   ├── tree.py              # Custom B+ Tree implementation
│   │   ├── storage.py           # Persistent SQLite database & migration
│   │   ├── scanner.py           # Whole-computer drive scanner
│   │   ├── watcher.py           # ReadDirectoryChangesW monitoring
│   │   ├── reconciler.py        # Offline startup reconciler
│   │   ├── queue_manager.py     # Thread-safe mutation queue
│   │   └── system_integration.py # Autostart, single-instance, tray
│   └── Findora.Ipc/             # IPC protocol specifications & schemas
├── tests/
│   ├── python/                  # Python unit & IPC test suite (65 tests)
│   └── dotnet/                  # C# WPF xUnit test suite (8 tests)
│       └── Findora.Wpf.Tests/
├── build/
│   └── build_release.ps1        # Automated release build script
├── dist/
│   └── Findora/                 # Packaged distributable release
│       ├── Findora.exe          # Main application executable
│       └── backend/             # Standalone Python backend runtime
└── docs/
    └── architecture.md          # Architectural diagrams & specifications
```

---

## Building and Running

### Prerequisites
- Windows 10 / 11 (x64)
- [.NET 8.0 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)
- Python 3.10+ (for backend development and PyInstaller packaging)

### Run in Development Mode
```powershell
# Run the WPF frontend with live Python backend supervision
dotnet run --project src\Findora.Wpf\Findora.Wpf.csproj
```

### Run Tests
```powershell
# Run Python backend test suite
python -m unittest discover -s tests\python

# Run .NET xUnit test suite
dotnet test Findora.sln
```

### Build Distributable Release Package
To compile both the WPF frontend and standalone backend into a clean, distributable package in `dist/Findora/`:
```powershell
powershell -ExecutionPolicy Bypass -File build\build_release.ps1
```
The output will be placed in:
- Main Executable: `dist\Findora\Findora.exe`
- Standalone Backend: `dist\Findora\backend\FindoraBackend.exe`
