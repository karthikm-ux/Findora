using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using Findora.Wpf.Services;

namespace Findora.Wpf.Views
{
    public partial class SettingsDialog : Window
    {
        private readonly BackendSupervisor _backend;
        private bool _isUpdatingUi = false;

        public SettingsDialog(BackendSupervisor backend)
        {
            InitializeComponent();
            _backend = backend;
        }

        private async void Window_Loaded(object sender, RoutedEventArgs e)
        {
            WindowBackdropHelper.TryEnableBlur(this);
            ThemeManager.ThemeChanged += isDark => WindowBackdropHelper.TryEnableBlur(this);

            _isUpdatingUi = true;
            AutostartCheckBox.IsChecked = AutostartHelper.IsEnabled();

            // Set current theme radio button
            ThemeSystemRadio.IsChecked = ThemeManager.CurrentMode == AppThemeMode.System;
            ThemeDarkRadio.IsChecked = ThemeManager.CurrentMode == AppThemeMode.Dark;
            ThemeLightRadio.IsChecked = ThemeManager.CurrentMode == AppThemeMode.Light;

            _isUpdatingUi = false;

            if (_backend != null)
            {
                await LoadExclusionsAsync();
            }
        }

        private void ThemeRadio_Checked(object sender, RoutedEventArgs e)
        {
            if (_isUpdatingUi) return;

            if (ThemeDarkRadio.IsChecked == true)
            {
                ThemeManager.SetThemeMode(AppThemeMode.Dark);
            }
            else if (ThemeLightRadio.IsChecked == true)
            {
                ThemeManager.SetThemeMode(AppThemeMode.Light);
            }
            else
            {
                ThemeManager.SetThemeMode(AppThemeMode.System);
            }
        }

        private void AutostartCheckBox_Changed(object sender, RoutedEventArgs e)
        {
            if (_isUpdatingUi) return;
            AutostartHelper.SetEnabled(AutostartCheckBox.IsChecked == true);
        }

        private async Task LoadExclusionsAsync()
        {
            if (_backend == null) return;
            try
            {
                var res = await _backend.SendRequestAsync("exclusions_get");
                if (res.TryGetProperty("exclusions", out var exclList) && exclList.ValueKind == JsonValueKind.Array)
                {
                    ExclusionsListBox.Items.Clear();
                    foreach (var item in exclList.EnumerateArray())
                    {
                        if (item.TryGetProperty("pattern", out var p))
                        {
                            ExclusionsListBox.Items.Add(p.GetString());
                        }
                    }
                }
            }
            catch { }
        }

        private async void AddExclusionButton_Click(object sender, RoutedEventArgs e)
        {
            if (_backend == null) return;
            string pattern = NewExclusionTextBox.Text.Trim();
            if (string.IsNullOrEmpty(pattern)) return;

            try
            {
                await _backend.SendRequestAsync("exclusions_add", new Dictionary<string, object> { { "pattern", pattern } });
                NewExclusionTextBox.Text = string.Empty;
                await LoadExclusionsAsync();
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Failed to add exclusion: {ex.Message}", "Findora Settings", MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        }

        private async void RemoveExclusionButton_Click(object sender, RoutedEventArgs e)
        {
            if (_backend == null) return;
            if (ExclusionsListBox.SelectedItem is string pattern)
            {
                try
                {
                    await _backend.SendRequestAsync("exclusions_remove", new Dictionary<string, object> { { "pattern", pattern } });
                    await LoadExclusionsAsync();
                }
                catch (Exception ex)
                {
                    MessageBox.Show($"Failed to remove exclusion: {ex.Message}", "Findora Settings", MessageBoxButton.OK, MessageBoxImage.Warning);
                }
            }
        }

        private async void RescanButton_Click(object sender, RoutedEventArgs e)
        {
            if (_backend == null) return;
            RescanButton.IsEnabled = false;
            RescanStatusText.Text = "Initiating scan...";
            try
            {
                var res = await _backend.SendRequestAsync("rescan");
                if (res.TryGetProperty("message", out var msg))
                {
                    RescanStatusText.Text = msg.GetString();
                }
                else
                {
                    RescanStatusText.Text = "Scan in progress...";
                }
            }
            catch (Exception ex)
            {
                RescanStatusText.Text = $"Error: {ex.Message}";
            }
            finally
            {
                await Task.Delay(2000);
                RescanButton.IsEnabled = true;
            }
        }

        private void DoneButton_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }
    }
}
