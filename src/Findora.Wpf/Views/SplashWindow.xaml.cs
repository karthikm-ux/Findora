using System;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media.Animation;
using Findora.Wpf.Services;

namespace Findora.Wpf.Views
{
    public partial class SplashWindow : Window
    {
        private readonly BackendSupervisor _backend;
        private bool _isDismissed = false;
        private int _currentStage = 1;

        public event Action? InitializationCompleted;

        public SplashWindow(BackendSupervisor backend)
        {
            InitializeComponent();
            _backend = backend;
        }

        private async void Window_Loaded(object sender, RoutedEventArgs e)
        {
            WindowBackdropHelper.TryEnableBlur(this);
            StartContinuousAnimations();
            SetStage(1, "Find anything. Instantly.");

            if (_backend != null)
            {
                _backend.EventReceived += OnBackendEvent;
                _backend.BackendReady += OnBackendReady;
                _backend.BackendExited += OnBackendExited;
                _backend.Start();

                // Wait for backend readiness with timeout
                bool ready = await _backend.WaitForReadyAsync(timeoutMs: 25000);
                if (ready)
                {
                    await SetStage4AndCompleteAsync();
                }
                else
                {
                    ShowError("Initialization timed out. You can retry or exit.");
                }
            }
        }

        private void StartContinuousAnimations()
        {
            // Continuous scanning track rotation
            var rotateAnim = new DoubleAnimation(0, 360, TimeSpan.FromSeconds(3.5))
            {
                RepeatBehavior = RepeatBehavior.Forever
            };
            TrackRotate.BeginAnimation(System.Windows.Media.RotateTransform.AngleProperty, rotateAnim);

            // Subtle breathing glow on central emblem
            var breatheAnim = new DoubleAnimation(0.96, 1.04, TimeSpan.FromSeconds(1.8))
            {
                AutoReverse = true,
                RepeatBehavior = RepeatBehavior.Forever,
                EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut }
            };
            EmblemScale.BeginAnimation(System.Windows.Media.ScaleTransform.ScaleXProperty, breatheAnim);
            EmblemScale.BeginAnimation(System.Windows.Media.ScaleTransform.ScaleYProperty, breatheAnim);
        }

        public void SetStage(int stage, string statusText, string subText = "")
        {
            if (_isDismissed) return;
            _currentStage = stage;

            StatusTextBlock.Text = statusText;

            if (!string.IsNullOrEmpty(subText))
            {
                SubStatusTextBlock.Text = subText;
                SubStatusTextBlock.Visibility = Visibility.Visible;
            }
            else
            {
                SubStatusTextBlock.Visibility = Visibility.Collapsed;
            }

            switch (stage)
            {
                case 1: // Launching Findora
                    AnimateProgressBar(70);
                    break;

                case 2: // Starting the engine
                    AnimateProgressBar(160);
                    AnimateFade(FileBadgePdf, 1.0, 300);
                    AnimateFade(FileBadgeImg, 1.0, 350);
                    AnimateFade(FileBadgeFolder, 1.0, 400);
                    AnimateFade(FileBadgeCode, 1.0, 450);
                    break;

                case 3: // Loading index
                    AnimateProgressBar(250);
                    AnimateFade(DatabaseIconPanel, 1.0, 300);
                    break;

                case 4: // Ready
                    AnimateProgressBar(380);
                    ShowCheckmark();
                    break;
            }
        }

        private void AnimateProgressBar(double targetWidth)
        {
            var anim = new DoubleAnimation(targetWidth, TimeSpan.FromMilliseconds(400))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut }
            };
            GlowProgressBar.BeginAnimation(FrameworkElement.WidthProperty, anim);
        }

        private void AnimateFade(UIElement element, double targetOpacity, int durationMs)
        {
            var anim = new DoubleAnimation(targetOpacity, TimeSpan.FromMilliseconds(durationMs))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut }
            };
            element.BeginAnimation(UIElement.OpacityProperty, anim);
        }

        private void ShowCheckmark()
        {
            SuccessCheckmarkBadge.Opacity = 1.0;
            var scaleAnim = new DoubleAnimation(0.0, 1.0, TimeSpan.FromMilliseconds(350))
            {
                EasingFunction = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.5 }
            };
            CheckmarkScale.BeginAnimation(System.Windows.Media.ScaleTransform.ScaleXProperty, scaleAnim);
            CheckmarkScale.BeginAnimation(System.Windows.Media.ScaleTransform.ScaleYProperty, scaleAnim);
        }

        private void OnBackendEvent(string evName, JsonElement data)
        {
            Dispatcher.Invoke(() =>
            {
                switch (evName)
                {
                    case "started":
                        SetStage(2, "Starting the search engine...");
                        break;
                    case "scan_progress":
                        long scanned = 0;
                        if (data.ValueKind == JsonValueKind.Object && data.TryGetProperty("files_scanned", out var fs))
                        {
                            scanned = fs.GetInt64();
                        }
                        SetStage(3, "Loading your saved index...", scanned > 0 ? $"{scanned:N0} files indexed" : "Indexing drives...");
                        break;
                    case "reconcile_progress":
                        SetStage(3, "Loading your saved index...", "Reconciling recent changes...");
                        break;
                }
            });
        }

        private async void OnBackendReady()
        {
            await Dispatcher.InvokeAsync(async () =>
            {
                await SetStage4AndCompleteAsync();
            });
        }

        private async Task SetStage4AndCompleteAsync()
        {
            if (_isDismissed) return;
            SetStage(4, "Ready to search!");

            // Hold briefly so user perceives the ready checkmark
            await Task.Delay(450);
            DismissAndComplete();
        }

        private void OnBackendExited()
        {
            Dispatcher.Invoke(() =>
            {
                if (!_isDismissed && !_backend.IsRunning)
                {
                    ShowError("The background engine terminated unexpectedly.");
                }
            });
        }

        private void ShowError(string message)
        {
            ErrorTextBlock.Text = message;
            NormalProgressPanel.Visibility = Visibility.Collapsed;
            ErrorPanel.Visibility = Visibility.Visible;
        }

        private async void RetryButton_Click(object sender, RoutedEventArgs e)
        {
            ErrorPanel.Visibility = Visibility.Collapsed;
            NormalProgressPanel.Visibility = Visibility.Visible;
            SetStage(1, "Retrying engine startup...");

            _backend.Start();
            bool ready = await _backend.WaitForReadyAsync(15000);
            if (ready)
            {
                await SetStage4AndCompleteAsync();
            }
            else
            {
                ShowError("Engine startup failed on retry.");
            }
        }

        private void ExitButton_Click(object sender, RoutedEventArgs e)
        {
            _backend.Dispose();
            Application.Current.Shutdown();
        }

        private void DismissAndComplete()
        {
            if (_isDismissed) return;
            _isDismissed = true;

            var fadeOut = new DoubleAnimation(1.0, 0.0, TimeSpan.FromMilliseconds(220));
            fadeOut.Completed += (s, e) =>
            {
                Hide();
                InitializationCompleted?.Invoke();
                Close();
            };
            SplashCard.BeginAnimation(OpacityProperty, fadeOut);
        }

        protected override void OnClosed(EventArgs e)
        {
            if (_backend != null)
            {
                _backend.EventReceived -= OnBackendEvent;
                _backend.BackendReady -= OnBackendReady;
                _backend.BackendExited -= OnBackendExited;
            }
            base.OnClosed(e);
        }
    }
}
