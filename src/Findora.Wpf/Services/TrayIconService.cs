using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;

namespace Findora.Wpf.Services
{
    public class TrayIconService : IDisposable
    {
        private const int WM_USER = 0x0400;
        private const int WM_TRAYICON = WM_USER + 1024;
        private const int WM_LBUTTONUP = 0x0202;
        private const int WM_LBUTTONDBLCLK = 0x0203;
        private const int WM_RBUTTONUP = 0x0205;

        private const uint NIM_ADD = 0x00000000;
        private const uint NIM_MODIFY = 0x00000001;
        private const uint NIM_DELETE = 0x00000002;
        private const uint NIF_MESSAGE = 0x00000001;
        private const uint NIF_ICON = 0x00000002;
        private const uint NIF_TIP = 0x00000004;

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct NOTIFYICONDATA
        {
            public int cbSize;
            public IntPtr hWnd;
            public int uID;
            public uint uFlags;
            public int uCallbackMessage;
            public IntPtr hIcon;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
            public string szTip;
            public int dwState;
            public int dwStateMask;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
            public string szInfo;
            public int uTimeoutOrVersion;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)]
            public string szInfoTitle;
            public int dwInfoFlags;
            public Guid guidItem;
            public IntPtr hBalloonIcon;
        }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern bool Shell_NotifyIcon(uint dwMessage, ref NOTIFYICONDATA lpData);

        [DllImport("user32.dll")]
        private static extern bool DestroyIcon(IntPtr hIcon);

        [DllImport("user32.dll")]
        private static extern bool SetForegroundWindow(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool GetCursorPos(out POINT lpPoint);

        [StructLayout(LayoutKind.Sequential)]
        private struct POINT
        {
            public int X;
            public int Y;
        }

        private IntPtr _hwnd = IntPtr.Zero;
        private HwndSource? _hwndSource;
        private IntPtr _hIcon = IntPtr.Zero;
        private bool _isAdded = false;
        private BackendSupervisor? _backend;

        public event Action? OpenSearchRequested;
        public event Action? RescanRequested;
        public event Action? SettingsRequested;
        public event Action? AboutRequested;
        public event Action? ExitRequested;

        public void Initialize(Window window, BackendSupervisor? backend = null)
        {
            _backend = backend;
            var helper = new WindowInteropHelper(window);
            _hwnd = helper.EnsureHandle();
            _hwndSource = HwndSource.FromHwnd(_hwnd);
            _hwndSource?.AddHook(WndProc);

            _hIcon = CreateFindoraTrayIconHandle();

            var nid = new NOTIFYICONDATA
            {
                cbSize = Marshal.SizeOf(typeof(NOTIFYICONDATA)),
                hWnd = _hwnd,
                uID = 1001,
                uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP,
                uCallbackMessage = WM_TRAYICON,
                hIcon = _hIcon,
                szTip = "Findora - Instant Filename Search"
            };

            _isAdded = Shell_NotifyIcon(NIM_ADD, ref nid);
        }

        public void UpdateTooltip(string tooltip)
        {
            if (!_isAdded || _hwnd == IntPtr.Zero) return;
            var nid = new NOTIFYICONDATA
            {
                cbSize = Marshal.SizeOf(typeof(NOTIFYICONDATA)),
                hWnd = _hwnd,
                uID = 1001,
                uFlags = NIF_TIP,
                szTip = tooltip.Length > 120 ? tooltip.Substring(0, 120) : tooltip
            };
            Shell_NotifyIcon(NIM_MODIFY, ref nid);
        }

        private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
        {
            if (msg == WM_TRAYICON)
            {
                int mouseMsg = lParam.ToInt32();
                if (mouseMsg == WM_LBUTTONUP || mouseMsg == WM_LBUTTONDBLCLK)
                {
                    OpenSearchRequested?.Invoke();
                    handled = true;
                }
                else if (mouseMsg == WM_RBUTTONUP)
                {
                    ShowTrayContextMenu();
                    handled = true;
                }
            }
            return IntPtr.Zero;
        }

        public ContextMenu CreateContextMenu()
        {
            var menu = new ContextMenu();
            if (Application.Current?.TryFindResource("DarkGlassContextMenu") is Style menuStyle)
            {
                menu.Style = menuStyle;
            }

            var itemStyle = Application.Current?.TryFindResource("GlassMenuItemStyle") as Style
                         ?? Application.Current?.TryFindResource("DarkGlassMenuItem") as Style;
            var sepStyle = Application.Current?.TryFindResource("GlassMenuSeparatorStyle") as Style
                        ?? Application.Current?.TryFindResource("DarkGlassSeparator") as Style;

            // 1. Header (Findora branding matching Storyboard Panel 6)
            var headerItem = new MenuItem
            {
                Header = "🔍  Findora",
                FontWeight = FontWeights.Bold,
                FontSize = 14,
                Foreground = new SolidColorBrush(System.Windows.Media.Color.FromRgb(54, 217, 255)),
                IsEnabled = false
            };
            if (itemStyle != null) headerItem.Style = itemStyle;
            menu.Items.Add(headerItem);

            var sep1 = new Separator();
            if (sepStyle != null) sep1.Style = sepStyle;
            menu.Items.Add(sep1);

            // 2. Open Search
            var openItem = new MenuItem
            {
                Header = "Open Search",
                InputGestureText = "Ctrl + Alt + F",
                FontWeight = FontWeights.SemiBold
            };
            if (itemStyle != null) openItem.Style = itemStyle;
            openItem.Click += (s, e) => OpenSearchRequested?.Invoke();
            menu.Items.Add(openItem);

            // 3. Indexing Status
            long fileCount = _backend?.TotalIndexedFiles ?? 0;
            string statusGesture = fileCount > 0 ? $"{fileCount:N0} files" : "Active";
            var statusItem = new MenuItem
            {
                Header = "Indexing Status",
                InputGestureText = statusGesture
            };
            if (itemStyle != null) statusItem.Style = itemStyle;
            statusItem.Click += (s, e) => RescanRequested?.Invoke();
            menu.Items.Add(statusItem);

            // 4. Settings
            var settingsItem = new MenuItem
            {
                Header = "Settings"
            };
            if (itemStyle != null) settingsItem.Style = itemStyle;
            settingsItem.Click += (s, e) => SettingsRequested?.Invoke();
            menu.Items.Add(settingsItem);

            // 5. Open Data Folder
            var dataFolderItem = new MenuItem
            {
                Header = "Open Data Folder"
            };
            if (itemStyle != null) dataFolderItem.Style = itemStyle;
            dataFolderItem.Click += (s, e) =>
            {
                string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string findoraDir = Path.Combine(localAppData, "Findora");
                try
                {
                    Directory.CreateDirectory(findoraDir);
                    Process.Start(new ProcessStartInfo { FileName = findoraDir, UseShellExecute = true });
                }
                catch { }
            };
            menu.Items.Add(dataFolderItem);

            // 6. About Findora
            var aboutItem = new MenuItem
            {
                Header = "About Findora"
            };
            if (itemStyle != null) aboutItem.Style = itemStyle;
            aboutItem.Click += (s, e) => AboutRequested?.Invoke();
            menu.Items.Add(aboutItem);

            var sep2 = new Separator();
            if (sepStyle != null) sep2.Style = sepStyle;
            menu.Items.Add(sep2);

            // 7. Exit Findora
            var exitItem = new MenuItem
            {
                Header = "Exit Findora",
                Foreground = new SolidColorBrush(System.Windows.Media.Color.FromRgb(248, 113, 113))
            };
            if (itemStyle != null) exitItem.Style = itemStyle;
            exitItem.Click += (s, e) => ExitRequested?.Invoke();
            menu.Items.Add(exitItem);

            return menu;
        }

        private void ShowTrayContextMenu()
        {
            SetForegroundWindow(_hwnd);
            GetCursorPos(out POINT pt);

            var menu = CreateContextMenu();
            menu.IsOpen = true;
        }

        private static IntPtr CreateFindoraTrayIconHandle()
        {
            using var bmp = new Bitmap(32, 32);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(System.Drawing.Color.Transparent);

                // Deep Midnight background disc with subtle cyan border
                using var bgBrush = new SolidBrush(System.Drawing.Color.FromArgb(7, 19, 43));
                g.FillEllipse(bgBrush, 2, 2, 28, 28);

                using var borderPen = new System.Drawing.Pen(System.Drawing.Color.FromArgb(54, 217, 255), 1.5f);
                g.DrawEllipse(borderPen, 2, 2, 28, 28);

                // Luminous Cyan Magnifying Glass Lens
                using var cyanPen = new System.Drawing.Pen(System.Drawing.Color.FromArgb(54, 217, 255), 2.6f);
                g.DrawEllipse(cyanPen, 8, 8, 10, 10);

                // Crisp White Handle
                using var whitePen = new System.Drawing.Pen(System.Drawing.Color.White, 3.0f);
                g.DrawLine(whitePen, 16, 16, 23, 23);
            }
            return bmp.GetHicon();
        }

        public void Dispose()
        {
            if (_isAdded && _hwnd != IntPtr.Zero)
            {
                var nid = new NOTIFYICONDATA
                {
                    cbSize = Marshal.SizeOf(typeof(NOTIFYICONDATA)),
                    hWnd = _hwnd,
                    uID = 1001
                };
                Shell_NotifyIcon(NIM_DELETE, ref nid);
                _isAdded = false;
            }

            if (_hIcon != IntPtr.Zero)
            {
                DestroyIcon(_hIcon);
                _hIcon = IntPtr.Zero;
            }

            if (_hwndSource != null)
            {
                _hwndSource.RemoveHook(WndProc);
                _hwndSource = null;
            }
        }
    }
}
