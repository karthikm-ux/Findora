using System;
using System.IO;
using System.Text.Json;
using System.Windows;
using Microsoft.Win32;

namespace Findora.Wpf.Services
{
    public enum AppThemeMode
    {
        System = 0,
        Dark = 1,
        Light = 2
    }

    public static class ThemeManager
    {
        private static AppThemeMode _currentMode = AppThemeMode.System;
        private static bool _isHooked = false;

        public static event Action<bool>? ThemeChanged;

        public static AppThemeMode CurrentMode => _currentMode;

        public static bool IsDark
        {
            get
            {
                if (_currentMode == AppThemeMode.Dark) return true;
                if (_currentMode == AppThemeMode.Light) return false;
                return GetWindowsSystemDarkPreference();
            }
        }

        public static void Initialize()
        {
            _currentMode = LoadSavedThemeMode();
            if (!_isHooked)
            {
                SystemEvents.UserPreferenceChanged += (s, e) =>
                {
                    if (e.Category == UserPreferenceCategory.General && _currentMode == AppThemeMode.System)
                    {
                        Application.Current?.Dispatcher?.Invoke(() => ApplyCurrentTheme());
                    }
                };
                _isHooked = true;
            }
            ApplyCurrentTheme();
        }

        public static void SetThemeMode(AppThemeMode mode)
        {
            _currentMode = mode;
            SaveThemeMode(mode);
            ApplyCurrentTheme();
        }

        public static void ApplyCurrentTheme()
        {
            bool isDark = IsDark;
            string themeFile = isDark ? "Themes/DarkTheme.xaml" : "Themes/LightTheme.xaml";

            try
            {
                var dict = new ResourceDictionary
                {
                    Source = new Uri($"pack://application:,,,/Findora;component/{themeFile}", UriKind.Absolute)
                };

                if (Application.Current != null)
                {
                    var merged = Application.Current.Resources.MergedDictionaries;
                    merged.Clear();
                    merged.Add(dict);
                }

                ThemeChanged?.Invoke(isDark);
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Failed to load theme {themeFile}: {ex.Message}");
            }
        }

        private static bool GetWindowsSystemDarkPreference()
        {
            try
            {
                using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
                if (key != null)
                {
                    object? val = key.GetValue("AppsUseLightTheme");
                    if (val is int intVal)
                    {
                        return intVal == 0; // 0 = Dark mode, 1 = Light mode
                    }
                }
            }
            catch { }
            return true; // Default to dark mode if detection fails
        }

        private static string GetConfigFilePath()
        {
            string appData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Findora");
            Directory.CreateDirectory(appData);
            return Path.Combine(appData, "theme.json");
        }

        private static AppThemeMode LoadSavedThemeMode()
        {
            try
            {
                string path = GetConfigFilePath();
                if (File.Exists(path))
                {
                    string json = File.ReadAllText(path);
                    using var doc = JsonDocument.Parse(json);
                    if (doc.RootElement.TryGetProperty("themeMode", out var elem))
                    {
                        if (Enum.TryParse<AppThemeMode>(elem.GetString(), out var mode))
                        {
                            return mode;
                        }
                    }
                }
            }
            catch { }
            return AppThemeMode.System;
        }

        private static void SaveThemeMode(AppThemeMode mode)
        {
            try
            {
                string path = GetConfigFilePath();
                var data = new { themeMode = mode.ToString() };
                File.WriteAllText(path, JsonSerializer.Serialize(data));
            }
            catch { }
        }
    }
}
