# Findora IPC Protocol Specification

## 1. Overview
Findora uses a high-performance, asynchronous JSON-Lines (NDJSON) IPC channel over standard pipes (`stdin`/`stdout`).
The C# WPF frontend acts as the supervisor process and spawns the backend worker (`FindoraBackend.exe` or `python main.py --ipc`) with standard input, output, and error redirected.

## 2. Message Formats

### Request Format (WPF -> Backend)
Requests are single JSON objects serialized onto a single line ending in `\n`:
```json
{
  "id": 101,
  "method": "search",
  "params": {
    "query": "report",
    "limit": 8
  }
}
```

### Response Format (Backend -> WPF)
Responses correlate directly with the request `id`:
```json
{
  "id": 101,
  "result": {
    "query": "report",
    "items": [
      {
        "filename": "annual_report_2026.docx",
        "full_path": "C:\\Users\\User\\Documents\\annual_report_2026.docx",
        "size_bytes": 1048576,
        "mtime": 1729600000.0,
        "extension": ".docx"
      }
    ],
    "total_matches": 1,
    "search_ms": 0.45
  },
  "error": null
}
```

### Async Notification / Event Format (Backend -> WPF)
Events are unprompted messages emitted by the backend:
```json
{
  "event": "ready",
  "data": {
    "hydrated_records": 845039
  }
}
```

Other supported events:
- `"started"`: Emitted immediately when the stdin loop begins listening.
- `"scan_progress"`: Periodic stats during drive scanning (`files_scanned`, `current_path`).
- `"reconcile_progress"`: Periodic status during startup reconciliation.

## 3. Supported Methods
- `ping`: Health-check and protocol handshake.
- `search`: Queries in-memory B+ Tree with limits and fetches SQLite metadata.
- `status`: Returns indexed file count, total size, drive statuses, and worker state.
- `rescan`: Starts background full scan of all eligible drives.
- `reveal`: Selects and highlights a file in Windows File Explorer (`explorer.exe /select,...`).
- `open`: Launches file in default associated Windows application.
- `exclusions_get`: Returns current active exclusions.
- `exclusions_add`: Adds directory/pattern exclusion.
- `exclusions_remove`: Removes exclusion.
- `shutdown`: Instructs backend to stop watchers, flush queues, and exit cleanly.
