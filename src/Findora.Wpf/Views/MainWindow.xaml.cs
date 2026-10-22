using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;
using Findora.Wpf.Models;
using Findora.Wpf.Services;

namespace Findora.Wpf.Views
{
    public partial class MainWindow : Window
    {
        private readonly BackendSupervisor _backend;
        private readonly DesktopWidget _desktopWidget;
        private readonly HotkeyManager _hotkeyManager = new();
        private readonly TrayIconService _trayIconService = new();
        private readonly DispatcherTimer _debounceTimer;
        private DispatcherTimer? _toastTimer;
        private CancellationTokenSource? _searchCts;
        private int _searchSequence = 0;
        private bool _isClosing = false;
        private LiquidGlassController? _glassController;

        public MainWindow(BackendSupervisor? backend = null)
        {
            InitializeComponent();
            _backend = backend ?? new BackendSupervisor();

            _desktopWidget = new DesktopWidget();
            _desktopWidget.WidgetClicked += ToggleSearch;

            _debounceTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(70) };
            _debounceTimer.Tick += DebounceTimer_Tick;

            CenterOnScreen();
        }

        private void Window_Loaded(object sender, RoutedEventArgs e)
        {
            WindowBackdropHelper.TryEnableBlur(this);
            ThemeManager.ThemeChanged += isDark => WindowBackdropHelper.TryEnableBlur(this);

            _glassController = new LiquidGlassController(this);
            _glassController.Attach();
            InteractiveSpecularOverlay.Background = _glassController.SpecularBrush;
            TopFresnelCatch.Background = _glassController.EdgeHighlightBrush;

            _hotkeyManager.Register(this);
            _hotkeyManager.HotkeyPressed += ToggleSearch;

            _trayIconService.Initialize(this, _backend);
            _trayIconService.OpenSearchRequested += ToggleSearch;
            _trayIconService.RescanRequested += () => _ = _backend.RescanAsync();
            _trayIconService.SettingsRequested += OpenSettings;
            _trayIconService.AboutRequested += OpenAbout;
            _trayIconService.ExitRequested += ExitApplication;

            _desktopWidget.ContextMenu = _trayIconService.CreateContextMenu();
            _desktopWidget.ContextMenuRequested += () =>
            {
                _desktopWidget.ContextMenu = _trayIconService.CreateContextMenu();
            };

            _backend.Start();

            // Refresh file count in tray
            _ = _backend.GetTotalFilesCountAsync();

            // Start with search window hidden; desktop widget visible
            Hide();
            _desktopWidget.Show();
        }

        private void CenterOnScreen()
        {
            double screenW = SystemParameters.PrimaryScreenWidth;
            double screenH = SystemParameters.PrimaryScreenHeight;
            Left = (screenW - Width) / 2.0;
            Top = Math.Max(80, screenH * 0.20);
        }

        public void ToggleSearch()
        {
            if (Visibility == Visibility.Visible && !_isClosing)
            {
                DismissWithAnimation();
            }
            else
            {
                ShowWithAnimation();
            }
        }

        public void ShowWithAnimation()
        {
            _isClosing = false;
            FeedbackToast.Visibility = Visibility.Collapsed;
            CenterOnScreen();
            Show();
            Activate();
            Topmost = true;

            // Focus search input
            SearchTextBox.Focus();
            SearchTextBox.SelectAll();

            // Fluid Liquid Glass entrance: Opacity + Subtle Scale + Slide
            var fadeIn = new DoubleAnimation(0.0, 1.0, TimeSpan.FromMilliseconds(180))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut }
            };
            var scaleAnim = new DoubleAnimation(0.975, 1.0, TimeSpan.FromMilliseconds(180))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut }
            };
            var slideDown = new DoubleAnimation(-12.0, 0.0, TimeSpan.FromMilliseconds(180))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut }
            };

            MainCard.BeginAnimation(OpacityProperty, fadeIn);
            CardScale.BeginAnimation(ScaleTransform.ScaleXProperty, scaleAnim);
            CardScale.BeginAnimation(ScaleTransform.ScaleYProperty, scaleAnim);
            CardTranslate.BeginAnimation(TranslateTransform.YProperty, slideDown);
        }

        public void DismissWithAnimation()
        {
            if (_isClosing) return;
            _isClosing = true;

            // Fluid Liquid Glass exit
            var fadeOut = new DoubleAnimation(1.0, 0.0, TimeSpan.FromMilliseconds(130))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseIn }
            };
            var scaleDown = new DoubleAnimation(1.0, 0.985, TimeSpan.FromMilliseconds(130))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseIn }
            };
            var slideUp = new DoubleAnimation(0.0, -8.0, TimeSpan.FromMilliseconds(130))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseIn }
            };

            fadeOut.Completed += (s, e) =>
            {
                Hide();
                _isClosing = false;
                _desktopWidget.ApplyDesktopLayering();
            };

            MainCard.BeginAnimation(OpacityProperty, fadeOut);
            CardScale.BeginAnimation(ScaleTransform.ScaleXProperty, scaleDown);
            CardScale.BeginAnimation(ScaleTransform.ScaleYProperty, scaleDown);
            CardTranslate.BeginAnimation(TranslateTransform.YProperty, slideUp);
        }

        private void SearchTextBox_TextChanged(object sender, TextChangedEventArgs e)
        {
            string query = SearchTextBox.Text;
            PlaceholderTextBlock.Visibility = string.IsNullOrEmpty(query) ? Visibility.Visible : Visibility.Collapsed;
            ClearButton.Visibility = string.IsNullOrEmpty(query) ? Visibility.Collapsed : Visibility.Visible;

            _debounceTimer.Stop();
            _debounceTimer.Start();
        }

        private async void DebounceTimer_Tick(object? sender, EventArgs e)
        {
            _debounceTimer.Stop();
            await ExecuteSearchAsync(SearchTextBox.Text.Trim());
        }

        private async Task ExecuteSearchAsync(string query)
        {
            _searchCts?.Cancel();
            _searchCts = new CancellationTokenSource();
            var ct = _searchCts.Token;
            int sequence = Interlocked.Increment(ref _searchSequence);

            if (string.IsNullOrEmpty(query))
            {
                ResultsListBox.ItemsSource = null;
                EmptyStatePanel.Visibility = Visibility.Collapsed;
                LoadingStatePanel.Visibility = Visibility.Collapsed;
                FeedbackToast.Visibility = Visibility.Collapsed;
                ResultsHeaderTextBlock.Text = "0 results";
                ProminentSearchTimeText.Text = "0.00 ms";
                IndexSearchTimeText.Text = "0.00 ms";
                TotalSearchTimeText.Text = "0.00 ms";
                return;
            }

            LoadingStatePanel.Visibility = Visibility.Visible;
            EmptyStatePanel.Visibility = Visibility.Collapsed;
            FeedbackToast.Visibility = Visibility.Collapsed;

            try
            {
                var queryResult = await _backend.SearchWithMetricsAsync(query, 7, ct);
                if (ct.IsCancellationRequested || sequence != _searchSequence || !string.Equals(SearchTextBox.Text.Trim(), query, StringComparison.OrdinalIgnoreCase))
                {
                    return; // Stale query, discard immediately
                }

                LoadingStatePanel.Visibility = Visibility.Collapsed;
                ResultsHeaderTextBlock.Text = queryResult.ResultsHeader;
                ProminentSearchTimeText.Text = queryResult.ProminentSearchTime;
                IndexSearchTimeText.Text = queryResult.FormattedIndexMs;
                TotalSearchTimeText.Text = queryResult.FormattedTotalMs;

                if (queryResult.Items.Count > 0)
                {
                    ResultsListBox.ItemsSource = queryResult.Items;
                    EmptyStatePanel.Visibility = Visibility.Collapsed;
                    ResultsListBox.SelectedIndex = 0;
                }
                else
                {
                    ResultsListBox.ItemsSource = null;
                    EmptyStatePanel.Visibility = Visibility.Visible;
                }
            }
            catch (OperationCanceledException)
            {
                // Expected on rapid typing
            }
            catch (Exception ex)
            {
                LoadingStatePanel.Visibility = Visibility.Collapsed;
                EmptyStatePanel.Visibility = Visibility.Visible;
                System.Diagnostics.Debug.WriteLine($"[Search Error] {ex.Message}");
            }
        }

        private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
        {
            if (e.Key == Key.Escape)
            {
                DismissWithAnimation();
                e.Handled = true;
                return;
            }

            if (e.Key == Key.Down)
            {
                if (ResultsListBox.Items.Count > 0)
                {
                    int next = (ResultsListBox.SelectedIndex + 1) % ResultsListBox.Items.Count;
                    ResultsListBox.SelectedIndex = next;
                    ResultsListBox.ScrollIntoView(ResultsListBox.SelectedItem);
                }
                e.Handled = true;
                return;
            }

            if (e.Key == Key.Up)
            {
                if (ResultsListBox.Items.Count > 0)
                {
                    int prev = (ResultsListBox.SelectedIndex - 1 + ResultsListBox.Items.Count) % ResultsListBox.Items.Count;
                    ResultsListBox.SelectedIndex = prev;
                    ResultsListBox.ScrollIntoView(ResultsListBox.SelectedItem);
                }
                e.Handled = true;
                return;
            }

            if (e.Key == Key.Enter)
            {
                if (Keyboard.IsKeyDown(Key.LeftShift) || Keyboard.IsKeyDown(Key.RightShift))
                {
                    OpenSelected();
                }
                else
                {
                    RevealSelected();
                }
                e.Handled = true;
                return;
            }
        }

        private async void RevealSelected()
        {
            if (ResultsListBox.SelectedItem == null && ResultsListBox.Items.Count > 0)
            {
                ResultsListBox.SelectedIndex = 0;
            }

            if (ResultsListBox.SelectedItem is SearchResultItem item && !string.IsNullOrEmpty(item.FullPath))
            {
                var result = await _backend.RevealAsync(item.FullPath);
                if (result.Success)
                {
                    DismissWithAnimation();
                }
                else
                {
                    ShowToast(result.ErrorMessage ?? "Could not reveal file in Windows Explorer.");
                }
            }
        }

        private async void OpenSelected()
        {
            if (ResultsListBox.SelectedItem == null && ResultsListBox.Items.Count > 0)
            {
                ResultsListBox.SelectedIndex = 0;
            }

            if (ResultsListBox.SelectedItem is SearchResultItem item && !string.IsNullOrEmpty(item.FullPath))
            {
                var result = await _backend.OpenAsync(item.FullPath);
                if (result.Success)
                {
                    DismissWithAnimation();
                }
                else
                {
                    ShowToast(result.ErrorMessage ?? "Could not open file.");
                }
            }
        }

        public void ShowToast(string message)
        {
            FeedbackToastText.Text = message;
            FeedbackToast.Visibility = Visibility.Visible;

            _toastTimer?.Stop();
            _toastTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(4) };
            _toastTimer.Tick += (s, e) =>
            {
                _toastTimer.Stop();
                FeedbackToast.Visibility = Visibility.Collapsed;
            };
            _toastTimer.Start();
        }

        private void CloseToastButton_Click(object sender, RoutedEventArgs e)
        {
            _toastTimer?.Stop();
            FeedbackToast.Visibility = Visibility.Collapsed;
        }

        private void ClearButton_Click(object sender, RoutedEventArgs e)
        {
            SearchTextBox.Text = string.Empty;
            SearchTextBox.Focus();
        }

        private void SettingsButton_Click(object sender, RoutedEventArgs e)
        {
            OpenSettings();
        }

        private void ResultsListBox_MouseDoubleClick(object sender, MouseButtonEventArgs e)
        {
            RevealSelected();
        }

        private void Window_Deactivated(object sender, EventArgs e)
        {
            if (Visibility == Visibility.Visible && !_isClosing)
            {
                DismissWithAnimation();
            }
        }

        public void OpenSettings()
        {
            var settings = new SettingsDialog(_backend) { Owner = this };
            settings.ShowDialog();
        }

        public void OpenAbout()
        {
            var about = new AboutDialog { Owner = this };
            about.ShowDialog();
        }

        public void ExitApplication()
        {
            _trayIconService?.Dispose();
            _hotkeyManager?.Dispose();
            _backend?.Dispose();
            _desktopWidget?.Close();
            Application.Current.Shutdown();
        }

        protected override void OnClosed(EventArgs e)
        {
            _glassController?.Detach();
            _trayIconService?.Dispose();
            _hotkeyManager?.Dispose();
            _backend?.Dispose();
            _desktopWidget?.Close();
            base.OnClosed(e);
        }
    }
}
