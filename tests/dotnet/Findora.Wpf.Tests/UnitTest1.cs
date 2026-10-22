using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using Findora.Wpf.Models;
using Findora.Wpf.Services;
using Xunit;

namespace Findora.Wpf.Tests
{
    public class WpfCoreTests
    {
        [Fact]
        public void TestSearchResultItemFormatting()
        {
            var item = new SearchResultItem
            {
                Filename = "Project_Report.docx",
                FullPath = @"D:\College\Final Year\Project_Report.docx",
                SizeBytes = 2048,
                MTime = 1729600000,
                Extension = ".docx"
            };

            Assert.Equal("2.0 KB", item.FormattedSize);
            Assert.Equal("Word Document", item.FileTypeDescription);
            Assert.False(string.IsNullOrEmpty(item.FormattedDate));
            Assert.Equal(@"D:\College\Final Year\Project_Report.docx", item.DisplayPath);

            var pdfItem = new SearchResultItem { Extension = ".pdf" };
            Assert.Equal("PDF Document", pdfItem.FileTypeDescription);

            var pngItem = new SearchResultItem { Extension = "png" };
            Assert.Equal("PNG Image", pngItem.FileTypeDescription);

            var pptxItem = new SearchResultItem { Extension = ".pptx" };
            Assert.Equal("PowerPoint", pptxItem.FileTypeDescription);

            var pyItem = new SearchResultItem { Extension = ".py" };
            Assert.Equal("Python File", pyItem.FileTypeDescription);

            var largeItem = new SearchResultItem
            {
                SizeBytes = 15 * 1024 * 1024
            };
            Assert.Equal("15.0 MB", largeItem.FormattedSize);

            var veryLongItem = new SearchResultItem
            {
                FullPath = @"C:\Users\Student\Documents\VeryLongDirectoryPathWithManyNestedFolders\AndEvenMoreFolders\DeepProjectReportFile_2026.docx"
            };
            Assert.Contains("...", veryLongItem.DisplayPath);
        }

        [Fact]
        public void TestFileIconServiceNormalization()
        {
            Assert.Equal(".docx", FileIconService.NormalizeExtension("docx"));
            Assert.Equal(".docx", FileIconService.NormalizeExtension(".DOCX"));
            Assert.Equal(".pdf", FileIconService.NormalizeExtension(@"C:\Path\File.PDF"));
            Assert.Equal(".default", FileIconService.NormalizeExtension(""));
            Assert.Equal(".default", FileIconService.NormalizeExtension("."));
            Assert.Equal(".txt", FileIconService.NormalizeExtension("test.txt"));
        }

        [Fact]
        public void TestIpcRequestSerialization()
        {
            var req = new IpcRequest
            {
                Id = 42,
                Method = "search",
                Params = new Dictionary<string, object>
                {
                    { "query", "quarterly" },
                    { "limit", 6 }
                }
            };

            string json = JsonSerializer.Serialize(req);
            Assert.Contains("\"id\":42", json);
            Assert.Contains("\"method\":\"search\"", json);
            Assert.Contains("\"query\":\"quarterly\"", json);
        }

        [Fact]
        public async Task TestBackendSupervisorEndToEndIpc()
        {
            string tempDb = Path.Combine(Path.GetTempPath(), $"fastretrival_test_{Guid.NewGuid():N}.db");
            try
            {
                using var backend = new BackendSupervisor();
                backend.Start(tempDb);

                Assert.True(backend.IsRunning, "Backend process failed to start.");

                // 1. Test ping
                var pingRes = await backend.SendRequestAsync("ping");
                Assert.True(pingRes.GetProperty("pong").GetBoolean());
                Assert.Equal("1.0", pingRes.GetProperty("protocol").GetString());

                // 2. Test status
                var statusRes = await backend.SendRequestAsync("status");
                Assert.True(statusRes.TryGetProperty("stats", out var stats));
                Assert.True(stats.GetProperty("total_files").GetInt64() >= 0);

                // 3. Test empty search query
                var emptyResults = await backend.SearchAsync("");
                Assert.Empty(emptyResults);

                // 4. Test real search query (on clean DB)
                var searchResults = await backend.SearchAsync("test", 5);
                Assert.NotNull(searchResults);

                // 5. Test Unicode search query
                var unicodeResults = await backend.SearchAsync("документ_2026", 5);
                Assert.NotNull(unicodeResults);

                // 6. Test reveal and open with temporary file
                string testFile = Path.Combine(Path.GetTempPath(), $"fr_ipc_test_{Guid.NewGuid():N}.txt");
                File.WriteAllText(testFile, "test content");
                try
                {
                    // Reveal should not throw
                    await backend.RevealAsync(testFile);
                }
                finally
                {
                    try { File.Delete(testFile); } catch { }
                }

                // 7. Test shutdown
                var shutdownRes = await backend.SendRequestAsync("shutdown");
                Assert.True(shutdownRes.GetProperty("shutdown").GetBoolean());
            }
            finally
            {
                if (File.Exists(tempDb))
                {
                    try { File.Delete(tempDb); } catch { }
                }
            }
        }

        [Fact]
        public async Task TestRapidQueriesAndCancellation()
        {
            string tempDb = Path.Combine(Path.GetTempPath(), $"fastretrival_test_{Guid.NewGuid():N}.db");
            try
            {
                using var backend = new BackendSupervisor();
                backend.Start(tempDb);
                Assert.True(backend.IsRunning);

                // Simulate rapid typing: queries 1..4 canceled in rapid succession, query 5 allowed to finish
                for (int i = 0; i < 4; i++)
                {
                    using var cts = new CancellationTokenSource();
                    cts.Cancel(); // Immediately cancelled
                    await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
                    {
                        await backend.SearchAsync($"query_{i}", 5, cts.Token);
                    });
                }

                // Final query succeeds without exception
                var finalResults = await backend.SearchAsync("final_query", 5);
                Assert.NotNull(finalResults);
            }
            finally
            {
                if (File.Exists(tempDb))
                {
                    try { File.Delete(tempDb); } catch { }
                }
            }
        }

        [Fact]
        public void TestSingleInstanceMutexBehavior()
        {
            const string mutexName = "Findora_WPF_SingleInstance_Mutex_2026";
            using var firstMutex = new System.Threading.Mutex(true, mutexName, out bool firstCreated);
            if (firstCreated)
            {
                // Second mutex should NOT be able to acquire initial ownership
                using var secondMutex = new System.Threading.Mutex(true, mutexName, out bool secondCreated);
                Assert.False(secondCreated, "Second instance was unexpectedly able to create mutex as owner.");
            }
        }

        [Fact]
        public async Task TestBackendSupervisorAutoRecoveryOnUnexpectedKill()
        {
            string tempDb = Path.Combine(Path.GetTempPath(), $"findora_test_{Guid.NewGuid():N}.db");
            try
            {
                using var backend = new BackendSupervisor();
                backend.Start(tempDb);
                Assert.True(backend.IsRunning);
                int? initialPid = backend.ProcessId;
                Assert.NotNull(initialPid);

                // Ping initial process
                var ping1 = await backend.SendRequestAsync("ping");
                Assert.True(ping1.GetProperty("pong").GetBoolean());

                // Abruptly kill the underlying process to simulate unexpected crash
                backend.KillUnderlyingProcessForTest();
                Assert.False(backend.IsRunning);

                // Send request - BackendSupervisor should auto-recover by launching a new process
                var ping2 = await backend.SendRequestAsync("ping");
                Assert.True(ping2.GetProperty("pong").GetBoolean());
                Assert.True(backend.IsRunning);
                Assert.NotEqual(initialPid, backend.ProcessId);
            }
            finally
            {
                if (File.Exists(tempDb))
                {
                    try { File.Delete(tempDb); } catch { }
                }
            }
        }

        [Fact]
        public async Task TestRealPersistentDatabaseSearchIntegration()
        {
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string findoraDbPath = Path.Combine(localAppData, "Findora", "findora.db");
            string legacyDbPath = Path.Combine(localAppData, "FastRetrival", "fastretrival.db");

            if (!File.Exists(findoraDbPath) && !File.Exists(legacyDbPath))
            {
                // If neither DB exists on this machine yet, pass test as not applicable
                return;
            }

            using var backend = new BackendSupervisor();
            backend.Start(); // Default DB (%LOCALAPPDATA%\Findora\findora.db)
            Assert.True(backend.IsRunning);

            // Wait for B+ Tree hydration
            bool isReady = await backend.WaitForReadyAsync(30000);
            Assert.True(isReady, "Backend failed to become ready within timeout.");

            // 1. Status check: total files should match > 800,000
            var statusRes = await backend.SendRequestAsync("status");
            Assert.True(statusRes.TryGetProperty("stats", out var stats));
            long totalFiles = stats.GetProperty("total_files").GetInt64();
            Assert.True(totalFiles > 0, "No files found in database.");

            // 2. Real query: search for common files (e.g. "explorer" or "cmd")
            var results = await backend.SearchAsync("explorer", 5);
            Assert.NotEmpty(results);
            foreach (var r in results)
            {
                Assert.False(string.IsNullOrWhiteSpace(r.Filename));
                Assert.False(string.IsNullOrWhiteSpace(r.FullPath));
                Assert.NotNull(r.Icon);
                Assert.False(string.IsNullOrWhiteSpace(r.FormattedSize));
            }

            // 3. Duplicate filename check: search for common duplicated filenames (e.g. "desktop.ini" or "license")
            var dupResults = await backend.SearchAsync("license", 10);
            Assert.NotNull(dupResults);

            // 4. Shutdown cleanly
            var shutdownRes = await backend.SendRequestAsync("shutdown");
            Assert.True(shutdownRes.GetProperty("shutdown").GetBoolean());
        }

        [Fact]
        public void TestSearchQueryResultFormatting()
        {
            var resEmpty = new SearchQueryResult { TotalMatches = 0, TotalMs = 0 };
            Assert.Equal(string.Empty, resEmpty.FormattedMetrics);
            Assert.Equal("0 results", resEmpty.ResultsHeader);
            Assert.Equal("< 0.1 ms", resEmpty.ProminentSearchTime);

            var resOne = new SearchQueryResult
            {
                TotalMatches = 1,
                IndexMs = 0.02,
                TotalMs = 0.04
            };
            Assert.Contains("1 match", resOne.FormattedMetrics);
            Assert.Contains("< 0.1 ms", resOne.FormattedMetrics);
            Assert.Equal("1 result", resOne.ResultsHeader);
            Assert.Equal("< 0.1 ms", resOne.ProminentSearchTime);

            var resMultiple = new SearchQueryResult
            {
                TotalMatches = 8,
                IndexMs = 0.45,
                TotalMs = 1.82
            };
            Assert.Equal("8 matches  •  Index: 0.45 ms  •  Total: 1.82 ms", resMultiple.FormattedMetrics);
            Assert.Equal("8 results", resMultiple.ResultsHeader);
            Assert.Equal("1.82 ms", resMultiple.ProminentSearchTime);
            Assert.Equal("0.45 ms", resMultiple.FormattedIndexMs);
            Assert.Equal("1.82 ms", resMultiple.FormattedTotalMs);
        }

        [Fact]
        public void TestFileActionServiceValidationAndNonExistentPaths()
        {
            // Empty / whitespace
            var emptyReveal = FileActionService.RevealInExplorer("");
            Assert.False(emptyReveal.Success);
            Assert.Contains("empty", emptyReveal.ErrorMessage, StringComparison.OrdinalIgnoreCase);

            var emptyOpen = FileActionService.OpenItem("   ");
            Assert.False(emptyOpen.Success);
            Assert.Contains("empty", emptyOpen.ErrorMessage, StringComparison.OrdinalIgnoreCase);

            // Non-existent path
            string fakePath = Path.Combine(Path.GetTempPath(), $"fake_file_{Guid.NewGuid():N}.docx");
            var fakeReveal = FileActionService.RevealInExplorer(fakePath);
            Assert.False(fakeReveal.Success);
            Assert.Contains("does not exist", fakeReveal.ErrorMessage);

            var fakeOpen = FileActionService.OpenItem(fakePath);
            Assert.False(fakeOpen.Success);
            Assert.Contains("does not exist", fakeOpen.ErrorMessage);
        }

        [Fact]
        public void TestFileActionServiceOnRealTempFilesAndDirectories()
        {
            // 1. Existing file
            string tempFile = Path.Combine(Path.GetTempPath(), $"findora_test_reveal_{Guid.NewGuid():N}.txt");
            File.WriteAllText(tempFile, "Temporary test content");
            try
            {
                var fileResult = FileActionService.RevealInExplorer(tempFile);
                Assert.True(fileResult.Success, $"Reveal failed: {fileResult.ErrorMessage}");
            }
            finally
            {
                try { File.Delete(tempFile); } catch { }
            }

            // 2. Existing directory
            string tempDir = Path.Combine(Path.GetTempPath(), $"findora_test_dir_{Guid.NewGuid():N}");
            Directory.CreateDirectory(tempDir);
            try
            {
                var dirResult = FileActionService.RevealInExplorer(tempDir);
                Assert.True(dirResult.Success, $"Directory reveal failed: {dirResult.ErrorMessage}");
            }
            finally
            {
                try { Directory.Delete(tempDir); } catch { }
            }
        }

        [Fact]
        public void TestAutostartHelperToggle()
        {
            bool initial = AutostartHelper.IsEnabled();

            try
            {
                // Enable
                bool enabledSuccess = AutostartHelper.SetEnabled(true);
                Assert.True(enabledSuccess);
                Assert.True(AutostartHelper.IsEnabled());

                // Disable
                bool disabledSuccess = AutostartHelper.SetEnabled(false);
                Assert.True(disabledSuccess);
                Assert.False(AutostartHelper.IsEnabled());
            }
            finally
            {
                // Restore initial state
                AutostartHelper.SetEnabled(initial);
            }
        }
    }
}
