using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace Findora.Wpf.Services
{
    public static class WindowBackdropHelper
    {
        private const int WCA_ACCENT_POLICY = 19;

        [StructLayout(LayoutKind.Sequential)]
        private struct AccentPolicy
        {
            public AccentState AccentState;
            public int AccentFlags;
            public int GradientColor;
            public int AnimationId;
        }

        private enum AccentState
        {
            ACCENT_DISABLED = 0,
            ACCENT_ENABLE_GRADIENT = 1,
            ACCENT_ENABLE_TRANSPARENTGRADIENT = 2,
            ACCENT_ENABLE_BLURBEHIND = 3,
            ACCENT_ENABLE_ACRYLICBLURBEHIND = 4,
            ACCENT_ENABLE_HOSTBACKDROP = 5
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct WindowCompositionAttributeData
        {
            public int Attribute;
            public IntPtr Data;
            public int SizeOfData;
        }

        [DllImport("user32.dll")]
        private static extern int SetWindowCompositionAttribute(IntPtr hwnd, ref WindowCompositionAttributeData data);

        [DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);

        private const int DWMWA_SYSTEMBACKDROP_TYPE = 38;
        private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;

        /// <summary>
        /// Attempts to enable native DWM Acrylic or Blur-behind on the specified window.
        /// Falls back gracefully to pure WPF layered alpha compositing if unsupported.
        /// </summary>
        public static bool TryEnableBlur(Window window, uint? tintColorRgba = null)
        {
            try
            {
                var helper = new WindowInteropHelper(window);
                IntPtr hwnd = helper.EnsureHandle();
                if (hwnd == IntPtr.Zero) return false;

                bool isDark = ThemeManager.IsDark;

                // 1. Enable immersive dark mode caption hints if applicable
                try
                {
                    int darkMode = isDark ? 1 : 0;
                    DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ref darkMode, sizeof(int));
                }
                catch { }

                // Default tint: quiet, subtle translucent acrylic tint
                uint tint = tintColorRgba ?? (isDark ? 0x2507111Fu : 0x25F0F4F8u);

                // GradientColor is AABBGGRR in Windows AccentPolicy
                byte a = (byte)((tint >> 24) & 0xFF);
                byte r = (byte)((tint >> 16) & 0xFF);
                byte g = (byte)((tint >> 8) & 0xFF);
                byte b = (byte)(tint & 0xFF);
                int abgr = (a << 24) | (b << 16) | (g << 8) | r;

                var policy = new AccentPolicy
                {
                    AccentState = AccentState.ACCENT_ENABLE_ACRYLICBLURBEHIND,
                    AccentFlags = 2, // Draw all borders
                    GradientColor = abgr
                };

                int structSize = Marshal.SizeOf(policy);
                IntPtr policyPtr = Marshal.AllocHGlobal(structSize);
                try
                {
                    Marshal.StructureToPtr(policy, policyPtr, false);
                    var data = new WindowCompositionAttributeData
                    {
                        Attribute = WCA_ACCENT_POLICY,
                        Data = policyPtr,
                        SizeOfData = structSize
                    };

                    int result = SetWindowCompositionAttribute(hwnd, ref data);
                    if (result != 0) return true;

                    // Fallback to basic blurbehind if acrylic not accepted
                    policy.AccentState = AccentState.ACCENT_ENABLE_BLURBEHIND;
                    Marshal.StructureToPtr(policy, policyPtr, false);
                    SetWindowCompositionAttribute(hwnd, ref data);
                    return true;
                }
                finally
                {
                    Marshal.FreeHGlobal(policyPtr);
                }
            }
            catch
            {
                // Graceful fallback to pure WPF per-pixel layered alpha transparency
                return false;
            }
        }
    }
}
