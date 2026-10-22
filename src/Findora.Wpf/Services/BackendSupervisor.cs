using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Findora.Wpf.Models;

namespace Findora.Wpf.Services
{
    public class BackendSupervisor : IDisposable
    {
        private Process? _process;
        private StreamWriter? _stdin;
        private int _requestIdCounter = 0;
        private readonly ConcurrentDictionary<int, TaskCompletionSource<JsonElement>> _pendingRequests = new();
        private readonly CancellationTokenSource _cts = new();
        private bool _isDisposed = false;
        private string? _configuredDbPath;
        private readonly string _logFilePath;

        public event Action<string, JsonElement>? EventReceived;
        public event Action? BackendReady;
        public event Action? BackendExited;

        public bool IsRunning => _process != null && !_process.HasExited;
        public int? ProcessId => _process != null && !_process.HasExited ? _process.Id : null;
        public TaskCompletionSource<bool> ReadyTask { get; private set; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public long TotalIndexedFiles { get; private set; } = 0;

        public BackendSupervisor()
        {
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string logDir = Path.Combine(localAppData, "Findora", "logs");
            try
            {
                Directory.CreateDirectory(logDir);
            }
            catch { }
            _logFilePath = Path.Combine(logDir, "backend.log");
        }

        public void KillUnderlyingProcessForTest()
        {
            if (_process != null && !_process.HasExited)
            {
                _process.Kill(true);
                _process.WaitForExit(1000);
            }
        }

        public async Task<bool> WaitForReadyAsync(int timeoutMs = 25000)
        {
            if (IsReady) return true;
            using var timeoutCts = new CancellationTokenSource(timeoutMs);
            using (timeoutCts.Token.Register(() => ReadyTask.TrySetCanceled()))
            {
                try
                {
                    return await ReadyTask.Task;
                }
                catch
                {
                    return IsReady;
                }
            }
        }

        public void Start(string? customDbPath = null)
        {
            if (customDbPath != null) _configuredDbPath = customDbPath;
            if (IsRunning) return;

            string? dbPathToUse = customDbPath ?? _configuredDbPath;
            ProcessStartInfo startInfo;

            // 1. Check for bundled / packaged backend executable (Release / Distributable mode)
            string[] packagedCandidates = {
                Path.Combine(AppContext.BaseDirectory, "backend", "FindoraBackend.exe"),
                Path.Combine(AppContext.BaseDirectory, "backend", "findora_backend.exe"),
                Path.Combine(AppContext.BaseDirectory, "FindoraBackend.exe")
            };

            string? foundPackagedExe = null;
            foreach (var cand in packagedCandidates)
            {
                if (File.Exists(cand))
                {
                    foundPackagedExe = cand;
                    break;
                }
            }

            if (foundPackagedExe != null)
            {
                string args = string.IsNullOrEmpty(dbPathToUse)
                    ? "--ipc"
                    : $"--ipc --db \"{dbPathToUse}\"";

                startInfo = new ProcessStartInfo
                {
                    FileName = foundPackagedExe,
                    Arguments = args,
                    WorkingDirectory = Path.GetDirectoryName(foundPackagedExe)!,
                    RedirectStandardInput = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
            }
            else
            {
                // 2. Development mode: locate main.py and launch via Python
                string pythonExe = FindPythonExecutable();
                string? mainPyPath = FindBackendMainScript();

                if (mainPyPath == null || !File.Exists(mainPyPath))
                {
                    LogMessage($"[BackendSupervisor] main.py not found. Running in offline mock mode.");
                    return;
                }

                string args = string.IsNullOrEmpty(dbPathToUse)
                    ? $"\"{mainPyPath}\" --ipc"
                    : $"\"{mainPyPath}\" --ipc --db \"{dbPathToUse}\"";

                startInfo = new ProcessStartInfo
                {
                    FileName = pythonExe,
                    Arguments = args,
                    WorkingDirectory = Path.GetDirectoryName(mainPyPath)!,
                    RedirectStandardInput = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
            }

            try
            {
                _process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
                _process.Exited += (s, e) =>
                {
                    IsReady = false;
                    LogMessage($"[BackendSupervisor] Backend process exited with code {_process?.ExitCode}.");
                    BackendExited?.Invoke();
                };

                _process.Start();
                _stdin = new StreamWriter(_process.StandardInput.BaseStream, new System.Text.UTF8Encoding(false))
                {
                    AutoFlush = true
                };

                Task.Run(() => ReadStdoutLoopAsync(_process.StandardOutput, _cts.Token));
                Task.Run(() => ReadStderrLoopAsync(_process.StandardError, _cts.Token));

                LogMessage($"[BackendSupervisor] Started backend process PID {_process.Id} ({startInfo.FileName})");
            }
            catch (Exception ex)
            {
                LogMessage($"[BackendSupervisor] Failed to start backend: {ex.Message}");
            }
        }

        private async Task ReadStdoutLoopAsync(StreamReader reader, CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                string? line = await reader.ReadLineAsync(ct);
                if (line == null) break; // EOF
                line = line.Trim();
                if (string.IsNullOrEmpty(line)) continue;

                try
                {
                    using var doc = JsonDocument.Parse(line);
                    var root = doc.RootElement;

                    if (root.TryGetProperty("id", out var idProp) && idProp.ValueKind == JsonValueKind.Number)
                    {
                        int id = idProp.GetInt32();
                        if (_pendingRequests.TryRemove(id, out var tcs))
                        {
                            if (root.TryGetProperty("error", out var errProp) && errProp.ValueKind == JsonValueKind.String)
                            {
                                tcs.SetException(new Exception(errProp.GetString()));
                            }
                            else if (root.TryGetProperty("result", out var resProp))
                            {
                                tcs.SetResult(resProp.Clone());
                            }
                            else
                            {
                                tcs.SetResult(default);
                            }
                        }
                    }
                    else if (root.TryGetProperty("event", out var evProp))
                    {
                        string evName = evProp.GetString() ?? "";
                        JsonElement data = root.TryGetProperty("data", out var d) ? d.Clone() : default;

                        if (evName == "ready")
                        {
                            IsReady = true;
                            ReadyTask.TrySetResult(true);
                            BackendReady?.Invoke();
                        }
                        else if (evName == "scan_progress" && data.ValueKind == JsonValueKind.Object && data.TryGetProperty("files_scanned", out var fs))
                        {
                            TotalIndexedFiles = fs.GetInt64();
                        }

                        EventReceived?.Invoke(evName, data);
                    }
                }
                catch (Exception ex)
                {
                    LogMessage($"[BackendSupervisor] JSON Parse Error: {ex.Message}");
                }
            }
        }

        private async Task ReadStderrLoopAsync(StreamReader reader, CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                string? line = await reader.ReadLineAsync(ct);
                if (line == null) break;
                LogMessage($"[Backend Stderr] {line}");
            }
        }

        public bool IsReady { get; private set; } = false;

        public async Task<JsonElement> SendRequestAsync(string method, Dictionary<string, object>? parameters = null, int timeoutMs = 8000, CancellationToken ct = default)
        {
            if (!IsRunning || _stdin == null)
            {
                // Auto-recover backend if terminated
                Start();
                if (!IsRunning || _stdin == null)
                {
                    throw new InvalidOperationException("Backend process is not running.");
                }
            }

            int reqId = Interlocked.Increment(ref _requestIdCounter);
            var tcs = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
            _pendingRequests[reqId] = tcs;

            var req = new
            {
                id = reqId,
                method = method,
                @params = parameters ?? new Dictionary<string, object>()
            };

            string json = JsonSerializer.Serialize(req);
            await _stdin.WriteLineAsync(json);

            using var timeoutCts = new CancellationTokenSource(timeoutMs);
            using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(ct, timeoutCts.Token);
            using (linkedCts.Token.Register(() => tcs.TrySetCanceled()))
            {
                try
                {
                    return await tcs.Task;
                }
                finally
                {
                    _pendingRequests.TryRemove(reqId, out _);
                }
            }
        }

        public async Task<SearchQueryResult> SearchWithMetricsAsync(string query, int limit = 8, CancellationToken ct = default)
        {
            var sw = Stopwatch.StartNew();
            if (!IsRunning)
            {
                Start();
            }

            if (!IsRunning)
            {
                var mockItems = GetMockResults(query, limit);
                sw.Stop();
                return new SearchQueryResult
                {
                    Items = mockItems,
                    TotalMatches = mockItems.Count,
                    IndexMs = 0.05,
                    MetaMs = 0.05,
                    TotalMs = 0.1,
                    ClientElapsedMs = sw.Elapsed.TotalMilliseconds
                };
            }

            try
            {
                var res = await SendRequestAsync("search", new Dictionary<string, object>
                {
                    { "query", query },
                    { "limit", limit }
                }, timeoutMs: 8000, ct: ct);

                sw.Stop();
                var queryResult = new SearchQueryResult
                {
                    ClientElapsedMs = sw.Elapsed.TotalMilliseconds
                };

                if (res.TryGetProperty("index_ms", out var idxProp)) queryResult.IndexMs = idxProp.GetDouble();
                if (res.TryGetProperty("meta_ms", out var metaProp)) queryResult.MetaMs = metaProp.GetDouble();
                if (res.TryGetProperty("total_ms", out var totProp)) queryResult.TotalMs = totProp.GetDouble();
                else if (res.TryGetProperty("search_ms", out var sProp)) queryResult.TotalMs = sProp.GetDouble();

                if (res.TryGetProperty("items", out var itemsProp) && itemsProp.ValueKind == JsonValueKind.Array)
                {
                    foreach (var elem in itemsProp.EnumerateArray())
                    {
                        string fname = elem.GetProperty("filename").GetString() ?? "";
                        string fpath = elem.GetProperty("full_path").GetString() ?? "";
                        long size = elem.GetProperty("size_bytes").GetInt64();
                        double mtime = elem.GetProperty("mtime").GetDouble();
                        string ext = elem.GetProperty("extension").GetString() ?? Path.GetExtension(fname);

                        queryResult.Items.Add(new SearchResultItem
                        {
                            Filename = fname,
                            FullPath = fpath,
                            SizeBytes = size,
                            MTime = mtime,
                            Extension = ext,
                            Icon = FileIconService.GetIcon(ext)
                        });
                    }
                }
                queryResult.TotalMatches = queryResult.Items.Count;
                return queryResult;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                sw.Stop();
                LogMessage($"[BackendSupervisor] Search failed: {ex.Message}");
                var mock = GetMockResults(query, limit);
                return new SearchQueryResult
                {
                    Items = mock,
                    TotalMatches = mock.Count,
                    ClientElapsedMs = sw.Elapsed.TotalMilliseconds
                };
            }
        }

        public async Task<List<SearchResultItem>> SearchAsync(string query, int limit = 8, CancellationToken ct = default)
        {
            var res = await SearchWithMetricsAsync(query, limit, ct);
            return res.Items;
        }

        public async Task<FileActionResult> RevealAsync(string path)
        {
            // 1. Native Windows Shell API executes directly in-process without argument parsing bugs
            var result = FileActionService.RevealInExplorer(path);

            // 2. Also notify backend if running for IPC parity / logging
            if (IsRunning && result.Success)
            {
                try
                {
                    await SendRequestAsync("reveal", new Dictionary<string, object> { { "path", path } });
                }
                catch { }
            }

            return result;
        }

        public async Task<FileActionResult> OpenAsync(string path)
        {
            // 1. Native Windows ShellExecute executes directly with registered default handler
            var result = FileActionService.OpenItem(path);

            // 2. Also notify backend if running
            if (IsRunning && result.Success)
            {
                try
                {
                    await SendRequestAsync("open", new Dictionary<string, object> { { "path", path } });
                }
                catch { }
            }

            return result;
        }

        public async Task<bool> RescanAsync()
        {
            if (!IsRunning) return false;
            try
            {
                await SendRequestAsync("rescan");
                return true;
            }
            catch
            {
                return false;
            }
        }

        public async Task<long> GetTotalFilesCountAsync()
        {
            if (!IsRunning) return TotalIndexedFiles;
            try
            {
                var res = await SendRequestAsync("status", timeoutMs: 2000);
                if (res.TryGetProperty("stats", out var st) && st.TryGetProperty("total_files", out var tf))
                {
                    TotalIndexedFiles = tf.GetInt64();
                }
            }
            catch { }
            return TotalIndexedFiles;
        }

        private List<SearchResultItem> GetMockResults(string query, int limit)
        {
            var allMocks = new List<SearchResultItem>
            {
                new() { Filename = "Project_Report_Final.docx", FullPath = @"D:\College\Final Year\Project_Report_Final.docx", SizeBytes = 45000, MTime = 1729000000, Extension = ".docx", Icon = FileIconService.GetIcon(".docx") },
                new() { Filename = "Q3_Financial_Analysis.xlsx", FullPath = @"C:\Users\Student\Documents\Q3_Financial_Analysis.xlsx", SizeBytes = 125000, MTime = 1729100000, Extension = ".xlsx", Icon = FileIconService.GetIcon(".xlsx") },
                new() { Filename = "Findora_Architecture.pdf", FullPath = @"D:\Projects\Findora\Findora_Architecture.pdf", SizeBytes = 85000, MTime = 1729200000, Extension = ".pdf", Icon = FileIconService.GetIcon(".pdf") },
                new() { Filename = "app_core_main.py", FullPath = @"D:\Projects\Findora\src\Findora.Backend\main.py", SizeBytes = 8200, MTime = 1729250000, Extension = ".py", Icon = FileIconService.GetIcon(".py") },
                new() { Filename = "System_Backup_2026.zip", FullPath = @"D:\Backups\System_Backup_2026.zip", SizeBytes = 145000000, MTime = 1729150000, Extension = ".zip", Icon = FileIconService.GetIcon(".zip") }
            };

            if (string.IsNullOrWhiteSpace(query)) return new List<SearchResultItem>();

            var filtered = allMocks.FindAll(m => m.Filename.IndexOf(query, StringComparison.OrdinalIgnoreCase) >= 0);
            return filtered.Count > limit ? filtered.GetRange(0, limit) : filtered;
        }

        private string FindPythonExecutable()
        {
            string[] commands = { "python.exe", "py.exe" };
            foreach (var cmd in commands)
            {
                try
                {
                    var psi = new ProcessStartInfo
                    {
                        FileName = cmd,
                        Arguments = "--version",
                        CreateNoWindow = true,
                        UseShellExecute = false,
                        RedirectStandardOutput = true
                    };
                    using var p = Process.Start(psi);
                    if (p != null)
                    {
                        p.WaitForExit(1000);
                        if (p.ExitCode == 0) return cmd;
                    }
                }
                catch { }
            }

            return "python.exe";
        }

        private string? FindBackendMainScript()
        {
            string dir = AppContext.BaseDirectory;
            while (!string.IsNullOrEmpty(dir))
            {
                // Target structure
                string path1 = Path.Combine(dir, "src", "Findora.Backend", "main.py");
                if (File.Exists(path1)) return path1;

                // Legacy structure fallback
                string path2 = Path.Combine(dir, "src", "main.py");
                if (File.Exists(path2)) return path2;

                dir = Path.GetDirectoryName(dir)!;
            }
            return null;
        }

        private void LogMessage(string message)
        {
            string timestamped = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}] {message}";
            Debug.WriteLine(timestamped);
            try
            {
                File.AppendAllText(_logFilePath, timestamped + Environment.NewLine);
            }
            catch { }
        }

        public void Dispose()
        {
            if (_isDisposed) return;
            _isDisposed = true;

            _cts.Cancel();
            if (IsRunning)
            {
                try
                {
                    _stdin?.WriteLine("{\"method\": \"shutdown\"}");
                    _process?.WaitForExit(1000);
                }
                catch { }

                try
                {
                    if (!_process!.HasExited)
                    {
                        _process.Kill(true);
                    }
                }
                catch { }
            }

            _process?.Dispose();
            _cts.Dispose();
        }
    }
}
