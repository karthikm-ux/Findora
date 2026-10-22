using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using Findora.Wpf.Services;

namespace Findora.Wpf.Views
{
    public partial class DesktopWidget : Window
    {
        private const int GWL_EXSTYLE = -20;
        private const int WS_EX_TOOLWINDOW = 0x00000080;
        private const int WS_EX_NOACTIVATE = 0x08000000;
        private static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2);
        private const uint SWP_NOMOVE = 0x0002;
        private const uint SWP_NOSIZE = 0x0001;
        private const uint SWP_NOACTIVATE = 0x0010;

        [DllImport("user32.dll", SetLastError = true)]
        private static extern int GetWindowLong(IntPtr hWnd, int nIndex);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);

        [DllImport("user32.dll")]
        private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

        private Point _dragStart;
        private bool _isDragging = false;
        private LiquidGlassController? _glassController;

        public event Action? WidgetClicked;
        public event Action? ContextMenuRequested;

        public DesktopWidget()
        {
            InitializeComponent();
            SetCornerPosition("bottom-right");
        }

        private void Window_Loaded(object sender, RoutedEventArgs e)
        {
            WindowBackdropHelper.TryEnableBlur(this);
            ThemeManager.ThemeChanged += isDark => WindowBackdropHelper.TryEnableBlur(this);

            _glassController = new LiquidGlassController(this);
            _glassController.Attach();
            WidgetSpecularOverlay.Background = _glassController.SpecularBrush;

            ApplyDesktopLayering();

            MouseEnter += (s, args) =>
            {
                var anim = new DoubleAnimation(1.06, TimeSpan.FromMilliseconds(120))
                {
                    EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut }
                };
                DiscScale.BeginAnimation(ScaleTransform.ScaleXProperty, anim);
                DiscScale.BeginAnimation(ScaleTransform.ScaleYProperty, anim);
            };

            MouseLeave += (s, args) =>
            {
                var anim = new DoubleAnimation(1.0, TimeSpan.FromMilliseconds(120))
                {
                    EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut }
                };
                DiscScale.BeginAnimation(ScaleTransform.ScaleXProperty, anim);
                DiscScale.BeginAnimation(ScaleTransform.ScaleYProperty, anim);
            };
        }

        public void ApplyDesktopLayering()
        {
            var helper = new WindowInteropHelper(this);
            IntPtr hwnd = helper.Handle;
            if (hwnd == IntPtr.Zero) return;

            int exStyle = GetWindowLong(hwnd, GWL_EXSTYLE);
            SetWindowLong(hwnd, GWL_EXSTYLE, exStyle | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE);

            SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        }

        public void SetCornerPosition(string corner)
        {
            double screenW = SystemParameters.PrimaryScreenWidth;
            double screenH = SystemParameters.PrimaryScreenHeight;
            double margin = 24;
            double taskbarPad = 54;

            switch (corner.ToLowerInvariant())
            {
                case "top-left":
                    Left = margin;
                    Top = margin;
                    break;
                case "top-right":
                    Left = screenW - Width - margin;
                    Top = margin;
                    break;
                case "bottom-left":
                    Left = margin;
                    Top = screenH - Height - taskbarPad;
                    break;
                case "hidden":
                    Hide();
                    return;
                default: // bottom-right
                    Left = screenW - Width - margin;
                    Top = screenH - Height - taskbarPad;
                    break;
            }
            Show();
            ApplyDesktopLayering();
        }

        private void Window_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            _dragStart = e.GetPosition(this);
            _isDragging = false;
            CaptureMouse();
        }

        private void Window_MouseMove(object sender, MouseEventArgs e)
        {
            if (e.LeftButton == MouseButtonState.Pressed && IsMouseCaptured)
            {
                Point current = e.GetPosition(this);
                double dx = current.X - _dragStart.X;
                double dy = current.Y - _dragStart.Y;

                if (Math.Abs(dx) > 3 || Math.Abs(dy) > 3)
                {
                    _isDragging = true;
                    Left += dx;
                    Top += dy;
                }
            }
        }

        private void Window_MouseLeftButtonUp(object sender, MouseButtonEventArgs e)
        {
            ReleaseMouseCapture();
            if (!_isDragging)
            {
                WidgetClicked?.Invoke();
            }
            _isDragging = false;
            ApplyDesktopLayering();
        }

        private void Window_MouseRightButtonUp(object sender, MouseButtonEventArgs e)
        {
            if (!_isDragging)
            {
                ContextMenuRequested?.Invoke();
                if (ContextMenu != null)
                {
                    ContextMenu.IsOpen = true;
                }
            }
            e.Handled = true;
        }

        protected override void OnMouseEnter(MouseEventArgs e)
        {
            base.OnMouseEnter(e);
            var anim = new DoubleAnimation(1.1, TimeSpan.FromMilliseconds(150))
            {
                EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut }
            };
            DiscScale.BeginAnimation(System.Windows.Media.ScaleTransform.ScaleXProperty, anim);
            DiscScale.BeginAnimation(System.Windows.Media.ScaleTransform.ScaleYProperty, anim);
        }

        protected override void OnMouseLeave(MouseEventArgs e)
        {
            base.OnMouseLeave(e);
            var anim = new DoubleAnimation(1.0, TimeSpan.FromMilliseconds(150))
            {
                EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut }
            };
            DiscScale.BeginAnimation(System.Windows.Media.ScaleTransform.ScaleXProperty, anim);
            DiscScale.BeginAnimation(System.Windows.Media.ScaleTransform.ScaleYProperty, anim);
        }
    }
}
