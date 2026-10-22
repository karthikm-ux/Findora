using System;
using Microsoft.Win32;

namespace Findora.Wpf.Services
{
    public static class AutostartHelper
    {
        private const string RunKeyPath = @"Software\Microsoft\Windows\CurrentVersion\Run";
        private const string AppName = "Findora";
        private const string LegacyAppName = "FastRetrival";

        public static bool IsEnabled()
        {
            try
            {
                using var key = Registry.CurrentUser.OpenSubKey(RunKeyPath, false);
                if (key == null) return false;
                var val = key.GetValue(AppName);
                if (val != null) return true;
                return key.GetValue(LegacyAppName) != null;
            }
            catch
            {
                return false;
            }
        }

        public static bool SetEnabled(bool enable)
        {
            try
            {
                using var key = Registry.CurrentUser.OpenSubKey(RunKeyPath, true);
                if (key == null) return false;

                if (enable)
                {
                    string? exePath = Environment.ProcessPath;
                    if (!string.IsNullOrEmpty(exePath))
                    {
                        key.SetValue(AppName, $"\"{exePath}\" --autostart");
                    }
                }
                else
                {
                    try { key.DeleteValue(AppName, false); } catch { }
                }

                // Clean legacy key if present
                try { key.DeleteValue(LegacyAppName, false); } catch { }

                return true;
            }
            catch
            {
                return false;
            }
        }
    }
}
