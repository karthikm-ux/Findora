using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;

namespace Findora.Wpf.Services
{
    public class FileActionResult
    {
        public bool Success { get; set; }
        public string? Message { get; set; }
        public string? ErrorMessage { get; set; }

        public static FileActionResult Ok(string? message = null) => new() { Success = true, Message = message };
        public static FileActionResult Fail(string errorMessage) => new() { Success = false, ErrorMessage = errorMessage };
    }

    public static class FileActionService
    {
        [DllImport("shell32.dll", ExactSpelling = true)]
        private static extern int SHParseDisplayName(
            [MarshalAs(UnmanagedType.LPWStr)] string pszName,
            IntPtr pbc,
            out IntPtr ppidl,
            uint sfgaoIn,
            out uint psfgaoOut);

        [DllImport("shell32.dll", ExactSpelling = true)]
        private static extern int SHOpenFolderAndSelectItems(
            IntPtr pidlFolder,
            uint cidl,
            [In, MarshalAs(UnmanagedType.LPArray)] IntPtr[]? apidl,
            uint dwFlags);

        [DllImport("ole32.dll", ExactSpelling = true)]
        private static extern void CoTaskMemFree(IntPtr pv);

        private const int S_OK = 0;
        private const int ERROR_ACCESS_DENIED = 5;
        private const int ERROR_NO_ASSOCIATION = 1155;

        /// <summary>
        /// Reveals and highlights the specified file or folder in Windows File Explorer.
        /// Uses SHOpenFolderAndSelectItems with fallback to explorer.exe /select.
        /// </summary>
        public static FileActionResult RevealInExplorer(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return FileActionResult.Fail("Path is empty or invalid.");
            }

            string fullPath;
            try
            {
                fullPath = Path.GetFullPath(path);
            }
            catch (Exception ex)
            {
                return FileActionResult.Fail($"Invalid path format: {ex.Message}");
            }

            bool isFile = File.Exists(fullPath);
            bool isDir = Directory.Exists(fullPath);

            if (!isFile && !isDir)
            {
                return FileActionResult.Fail($"File or directory does not exist: {fullPath}");
            }

            // 1. Try Windows native Shell API SHOpenFolderAndSelectItems
            try
            {
                int hr = SHParseDisplayName(fullPath, IntPtr.Zero, out IntPtr pidl, 0, out _);
                if (hr == S_OK && pidl != IntPtr.Zero)
                {
                    try
                    {
                        IntPtr[] files = { pidl };
                        int openHr = SHOpenFolderAndSelectItems(pidl, 0, null, 0);
                        if (openHr == S_OK)
                        {
                            return FileActionResult.Ok();
                        }
                    }
                    finally
                    {
                        CoTaskMemFree(pidl);
                    }
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[FileActionService] SHOpenFolderAndSelectItems error: {ex.Message}");
            }

            // 2. Fallback: launch explorer.exe with /select,"{fullPath}"
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "explorer.exe",
                    Arguments = $"/select,\"{fullPath}\"",
                    UseShellExecute = true
                };
                Process.Start(psi);
                return FileActionResult.Ok();
            }
            catch (Exception ex)
            {
                return FileActionResult.Fail($"Failed to launch Explorer: {ex.Message}");
            }
        }

        /// <summary>
        /// Opens the specified file using its default associated application, or opens directory in Explorer.
        /// </summary>
        public static FileActionResult OpenItem(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return FileActionResult.Fail("Path is empty or invalid.");
            }

            string fullPath;
            try
            {
                fullPath = Path.GetFullPath(path);
            }
            catch (Exception ex)
            {
                return FileActionResult.Fail($"Invalid path format: {ex.Message}");
            }

            bool isFile = File.Exists(fullPath);
            bool isDir = Directory.Exists(fullPath);

            if (!isFile && !isDir)
            {
                return FileActionResult.Fail($"File or directory does not exist: {fullPath}");
            }

            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = fullPath,
                    UseShellExecute = true,
                    WorkingDirectory = Path.GetDirectoryName(fullPath) ?? string.Empty
                };
                Process.Start(psi);
                return FileActionResult.Ok();
            }
            catch (Win32Exception w32Ex)
            {
                if (w32Ex.NativeErrorCode == ERROR_NO_ASSOCIATION)
                {
                    // No default association -> show Windows Open With dialog
                    try
                    {
                        Process.Start(new ProcessStartInfo
                        {
                            FileName = "rundll32.exe",
                            Arguments = $"shell32.dll,OpenAs_RunDLL \"{fullPath}\"",
                            UseShellExecute = true
                        });
                        return FileActionResult.Ok("Choose an app to open this file.");
                    }
                    catch
                    {
                        return FileActionResult.Fail("No application associated with this file type.");
                    }
                }
                else if (w32Ex.NativeErrorCode == ERROR_ACCESS_DENIED)
                {
                    return FileActionResult.Fail("Access denied. Administrator privileges may be required.");
                }
                return FileActionResult.Fail($"Cannot open file: {w32Ex.Message}");
            }
            catch (Exception ex)
            {
                return FileActionResult.Fail($"Error opening file: {ex.Message}");
            }
        }
    }
}
