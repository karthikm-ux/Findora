using System;
using System.Collections.Concurrent;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace Findora.Wpf.Services
{
    public static class FileIconService
    {
        private const uint SHGFI_ICON = 0x000000100;
        private const uint SHGFI_LARGEICON = 0x000000000;
        private const uint SHGFI_USEFILEATTRIBUTES = 0x000000010;
        private const uint FILE_ATTRIBUTE_NORMAL = 0x00000080;

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct SHFILEINFO
        {
            public IntPtr hIcon;
            public int iIcon;
            public uint dwAttributes;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
            public string szDisplayName;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 80)]
            public string szTypeName;
        }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr SHGetFileInfoW(
            string pszPath,
            uint dwFileAttributes,
            ref SHFILEINFO psfi,
            uint cbFileInfo,
            uint uFlags
        );

        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool DestroyIcon(IntPtr hIcon);

        private static readonly ConcurrentDictionary<string, ImageSource> _cache = new(StringComparer.OrdinalIgnoreCase);

        static FileIconService()
        {
            Task.Run(() => PreloadCommonIcons());
        }

        public static string NormalizeExtension(string extOrPath)
        {
            if (string.IsNullOrWhiteSpace(extOrPath)) return ".default";
            string ext = Path.GetExtension(extOrPath);
            if (string.IsNullOrEmpty(ext))
            {
                ext = extOrPath.StartsWith(".") ? extOrPath : "." + extOrPath;
            }
            ext = ext.Trim().ToLowerInvariant();
            return ext == "." ? ".default" : ext;
        }

        public static ImageSource GetIcon(string extOrPath)
        {
            string ext = NormalizeExtension(extOrPath);
            if (_cache.TryGetValue(ext, out var cached))
            {
                return cached;
            }

            var icon = ExtractShellIcon(ext);
            if (icon != null)
            {
                _cache[ext] = icon;
                return icon;
            }

            // Fallback generic icon
            if (_cache.TryGetValue(".default", out var defaultIcon))
            {
                return defaultIcon;
            }

            var fallback = CreateFallbackIcon();
            _cache[ext] = fallback;
            return fallback;
        }

        private static ImageSource? ExtractShellIcon(string ext)
        {
            try
            {
                var sfi = new SHFILEINFO();
                string dummy = ext == ".default" ? "dummy" : $"dummy{ext}";
                uint flags = SHGFI_ICON | SHGFI_LARGEICON | SHGFI_USEFILEATTRIBUTES;

                IntPtr res = SHGetFileInfoW(dummy, FILE_ATTRIBUTE_NORMAL, ref sfi, (uint)Marshal.SizeOf(sfi), flags);
                if (res != IntPtr.Zero && sfi.hIcon != IntPtr.Zero)
                {
                    try
                    {
                        var bitmapSource = Imaging.CreateBitmapSourceFromHIcon(
                            sfi.hIcon,
                            Int32Rect.Empty,
                            BitmapSizeOptions.FromEmptyOptions()
                        );
                        bitmapSource.Freeze();
                        return bitmapSource;
                    }
                    finally
                    {
                        DestroyIcon(sfi.hIcon);
                    }
                }
            }
            catch
            {
                // Graceful fallback
            }
            return null;
        }

        private static ImageSource CreateFallbackIcon()
        {
            var drawingVisual = new DrawingVisual();
            using (var dc = drawingVisual.RenderOpen())
            {
                var brush = new SolidColorBrush(Color.FromArgb(255, 241, 245, 249));
                var pen = new Pen(new SolidColorBrush(Color.FromArgb(255, 203, 213, 225)), 1);
                dc.DrawRoundedRectangle(brush, pen, new Rect(2, 2, 28, 28), 4, 4);

                var lineBrush = new SolidColorBrush(Color.FromArgb(255, 148, 163, 184));
                dc.DrawRectangle(lineBrush, null, new Rect(6, 8, 20, 2));
                dc.DrawRectangle(lineBrush, null, new Rect(6, 14, 16, 2));
                dc.DrawRectangle(lineBrush, null, new Rect(6, 20, 12, 2));
            }

            var rtb = new RenderTargetBitmap(32, 32, 96, 96, PixelFormats.Pbgra32);
            rtb.Render(drawingVisual);
            rtb.Freeze();
            return rtb;
        }

        private static void PreloadCommonIcons()
        {
            string[] common = {
                ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
                ".pdf", ".txt", ".py", ".exe", ".png", ".jpg",
                ".zip", ".mp3", ".mp4", ".default"
            };

            foreach (var ext in common)
            {
                GetIcon(ext);
            }
        }
    }
}
