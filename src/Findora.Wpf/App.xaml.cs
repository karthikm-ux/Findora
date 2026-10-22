using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows;
using Findora.Wpf.Services;
using Findora.Wpf.Views;

namespace Findora.Wpf
{
    public partial class App : Application
    {
        private const string MutexName = "Findora_WPF_SingleInstance_Mutex_2026";
        private static Mutex? _mutex;
        private static bool _ownsMutex = false;
        private BackendSupervisor? _backend;
        private MainWindow? _mainWindow;

        [DllImport("user32.dll", SetLastError = true)]
        private static extern IntPtr FindWindow(string? lpClassName, string lpWindowName);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool SetForegroundWindow(IntPtr hWnd);

        protected override void OnStartup(StartupEventArgs e)
        {
            string appDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Findora");
            try { Directory.CreateDirectory(appDir); } catch { }
            string startupLog = Path.Combine(appDir, "startup.log");

            AppDomain.CurrentDomain.UnhandledException += (s, args) =>
            {
                try { File.AppendAllText(startupLog, $"[{DateTime.Now}] Unhandled: {args.ExceptionObject}\n"); } catch { }
            };
            DispatcherUnhandledException += (s, args) =>
            {
                try { File.AppendAllText(startupLog, $"[{DateTime.Now}] DispatcherUnhandled: {args.Exception}\n"); } catch { }
            };

            _mutex = new Mutex(true, MutexName, out bool createdNew);
            _ownsMutex = createdNew;
            try { File.AppendAllText(startupLog, $"[{DateTime.Now}] OnStartup. createdNew={createdNew}, args={string.Join(" ", e.Args)}\n"); } catch { }

            if (!createdNew)
            {
                // Another instance is already running! Bring existing window to front and exit immediately
                IntPtr existingHwnd = FindWindow(null, "Findora Search");
                if (existingHwnd == IntPtr.Zero)
                {
                    existingHwnd = FindWindow(null, "FastRetrival Search");
                }
                if (existingHwnd != IntPtr.Zero)
                {
                    SetForegroundWindow(existingHwnd);
                }
                _mutex?.Dispose();
                _mutex = null;
                Environment.Exit(0);
                return;
            }

            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            base.OnStartup(e);

            ThemeManager.Initialize();
            _backend = new BackendSupervisor();

            // Check if launched silently or via autostart
            bool isSilent = false;
            foreach (var arg in e.Args)
            {
                if (arg.Equals("--silent", StringComparison.OrdinalIgnoreCase) ||
                    arg.Equals("--autostart", StringComparison.OrdinalIgnoreCase) ||
                    arg.Equals("--minimized", StringComparison.OrdinalIgnoreCase))
                {
                    isSilent = true;
                    break;
                }
            }

            if (isSilent)
            {
                // Silent background startup
                _backend.Start();
                _mainWindow = new MainWindow(_backend);
                MainWindow = _mainWindow;
                _mainWindow.Show();
            }
            else
            {
                // Animated interactive startup
                var splash = new SplashWindow(_backend);
                splash.InitializationCompleted += () =>
                {
                    _mainWindow = new MainWindow(_backend);
                    MainWindow = _mainWindow;
                    _mainWindow.Show();
                };
                splash.Show();
            }
        }

        protected override void OnExit(ExitEventArgs e)
        {
            try
            {
                _mainWindow?.ExitApplication();
            }
            catch { }

            try
            {
                _backend?.Dispose();
            }
            catch { }

            if (_ownsMutex && _mutex != null)
            {
                try
                {
                    _mutex.ReleaseMutex();
                }
                catch { }
                _mutex.Dispose();
                _mutex = null;
            }
            base.OnExit(e);
        }
    }
}
