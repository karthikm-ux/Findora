using System;
using System.Collections.Generic;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Findora.Wpf.Models;
using Findora.Wpf.Services;
using Findora.Wpf.Views;

namespace VisualInspector
{
    class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Console.WriteLine("Starting VisualInspector for iPhone Liquid Glass verification...");
            string outputDir = @"D:\Project\FastRetrival-main\FastRetrival-main\assets\screenshots";
            if (!Directory.Exists(outputDir))
            {
                Directory.CreateDirectory(outputDir);
            }

            var app = new Application();

            // 1. Capture Dark Mode Liquid Glass (Smoky Obsidian)
            Console.WriteLine("\n--- Capturing Liquid Glass: Dark Mode ---");
            ThemeManager.SetThemeMode(AppThemeMode.Dark);

            CaptureMainWindow(outputDir, isDark: true, pointerPos: new Point(0.45, 0.25), "liquid_mainwindow_dark_desktop");
            CaptureMainWindow(outputDir, isDark: true, pointerPos: new Point(0.25, 0.45), "liquid_mainwindow_dark_rowhover_desktop");
            CaptureSplash(outputDir, isDark: true, "liquid_splash_dark_desktop");
            CaptureDesktopWidget(outputDir, isDark: true, "liquid_widget_dark_desktop");
            CaptureSettingsDialog(outputDir, isDark: true, "liquid_settings_dark_desktop");
            CaptureAboutDialog(outputDir, isDark: true, "liquid_about_dark_desktop");

            // 2. Capture Light Mode Liquid Glass (Crystal Quartz)
            Console.WriteLine("\n--- Capturing Liquid Glass: Light Mode ---");
            ThemeManager.SetThemeMode(AppThemeMode.Light);

            CaptureMainWindow(outputDir, isDark: false, pointerPos: new Point(0.5, 0.2), "liquid_mainwindow_light_desktop");
            CaptureSplash(outputDir, isDark: false, "liquid_splash_light_desktop");
            CaptureDesktopWidget(outputDir, isDark: false, "liquid_widget_light_desktop");

            Console.WriteLine("\nAll Liquid Glass visual snapshots saved to: " + outputDir);
        }

        private static DrawingBrush CreateDesktopWallpaperBrush(bool lightWallpaper = false)
        {
            var dg = new DrawingGroup();
            
            if (!lightWallpaper)
            {
                // Rich desktop with distinct elements (colorful light bands, organic geometry) to verify real-time refraction and shine-through
                var baseRect = new GeometryDrawing(
                    new LinearGradientBrush(
                        Color.FromRgb(15, 23, 42), // deep slate
                        Color.FromRgb(30, 41, 59), // slate 800
                        new Point(0, 0), new Point(1, 1)),
                    null,
                    new RectangleGeometry(new Rect(0, 0, 1920, 1080)));
                dg.Children.Add(baseRect);

                // Vivid chromatic light waves (simulating dynamic iPhone wallpaper)
                var wave1 = new GeometryDrawing(
                    new RadialGradientBrush(Color.FromArgb(160, 56, 189, 248), Colors.Transparent) // Electric cyan
                    {
                        Center = new Point(0.32, 0.38),
                        RadiusX = 0.45,
                        RadiusY = 0.45
                    },
                    null,
                    new RectangleGeometry(new Rect(0, 0, 1920, 1080)));
                dg.Children.Add(wave1);

                var wave2 = new GeometryDrawing(
                    new RadialGradientBrush(Color.FromArgb(130, 244, 63, 94), Colors.Transparent) // Vivid rose
                    {
                        Center = new Point(0.72, 0.62),
                        RadiusX = 0.5,
                        RadiusY = 0.5
                    },
                    null,
                    new RectangleGeometry(new Rect(0, 0, 1920, 1080)));
                dg.Children.Add(wave2);

                var wave3 = new GeometryDrawing(
                    new RadialGradientBrush(Color.FromArgb(100, 168, 85, 247), Colors.Transparent) // Violet ambient
                    {
                        Center = new Point(0.55, 0.5),
                        RadiusX = 0.4,
                        RadiusY = 0.4
                    },
                    null,
                    new RectangleGeometry(new Rect(0, 0, 1920, 1080)));
                dg.Children.Add(wave3);
            }
            else
            {
                // Light Mode Wallpaper: vibrant sunlit daylight with azure and warm gold ambient glows
                var baseRect = new GeometryDrawing(
                    new LinearGradientBrush(
                        Color.FromRgb(240, 249, 255), // sky 50
                        Color.FromRgb(224, 242, 254), // sky 100
                        new Point(0, 0), new Point(1, 1)),
                    null,
                    new RectangleGeometry(new Rect(0, 0, 1920, 1080)));
                dg.Children.Add(baseRect);

                var wave1 = new GeometryDrawing(
                    new RadialGradientBrush(Color.FromArgb(110, 14, 165, 233), Colors.Transparent) // Sky blue
                    {
                        Center = new Point(0.3, 0.35),
                        RadiusX = 0.5,
                        RadiusY = 0.5
                    },
                    null,
                    new RectangleGeometry(new Rect(0, 0, 1920, 1080)));
                dg.Children.Add(wave1);

                var wave2 = new GeometryDrawing(
                    new RadialGradientBrush(Color.FromArgb(80, 251, 146, 60), Colors.Transparent) // Warm sun glow
                    {
                        Center = new Point(0.75, 0.65),
                        RadiusX = 0.45,
                        RadiusY = 0.45
                    },
                    null,
                    new RectangleGeometry(new Rect(0, 0, 1920, 1080)));
                dg.Children.Add(wave2);
            }

            return new DrawingBrush(dg) { Stretch = Stretch.Fill };
        }

        private static void SaveVisualToPng(Visual visual, int width, int height, string filePath, bool placeOnDesktop = true, int contentWidth = 920, int contentHeight = 490, bool lightDesktop = false)
        {
            var rtb = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);

            if (placeOnDesktop)
            {
                var dv = new DrawingVisual();
                using (var dc = dv.RenderOpen())
                {
                    dc.DrawRectangle(CreateDesktopWallpaperBrush(lightDesktop), null, new Rect(0, 0, width, height));
                    dc.DrawRectangle(new VisualBrush(visual), null, new Rect((width - contentWidth) / 2, (height - contentHeight) / 2, contentWidth, contentHeight));
                }
                rtb.Render(dv);
            }
            else
            {
                rtb.Render(visual);
            }

            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(rtb));
            using (var fs = new FileStream(filePath, FileMode.Create, FileAccess.Write))
            {
                encoder.Save(fs);
            }
            Console.WriteLine($"Saved: {Path.GetFileName(filePath)} ({width}x{height})");
        }

        private static void CaptureMainWindow(string outputDir, bool isDark, Point pointerPos, string filePrefix)
        {
            try
            {
                var window = new MainWindow(null);

                var resultsListBox = window.FindName("ResultsListBox") as ListBox;
                var searchTextBox = window.FindName("SearchTextBox") as TextBox;
                var resultsHeader = window.FindName("ResultsHeaderTextBlock") as TextBlock;
                var prominentSearchTime = window.FindName("ProminentSearchTimeText") as TextBlock;
                var indexSearchTime = window.FindName("IndexSearchTimeText") as TextBlock;
                var totalSearchTime = window.FindName("TotalSearchTimeText") as TextBlock;
                var placeholder = window.FindName("PlaceholderTextBlock") as TextBlock;
                var mainCard = window.FindName("MainCard") as Border;
                var specularOverlay = window.FindName("InteractiveSpecularOverlay") as Border;

                // Configure specular sheen for the specified pointer position
                var specularBrush = new RadialGradientBrush
                {
                    Center = pointerPos,
                    GradientOrigin = pointerPos,
                    RadiusX = 0.55,
                    RadiusY = 0.55
                };

                if (isDark)
                {
                    specularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(60, 255, 255, 255), 0.0));
                    specularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(28, 56, 189, 248), 0.35));
                    specularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(10, 14, 165, 233), 0.65));
                    specularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, 0, 0, 0), 1.0));
                }
                else
                {
                    specularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(120, 255, 255, 255), 0.0));
                    specularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(60, 255, 255, 255), 0.3));
                    specularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(25, 2, 132, 199), 0.6));
                    specularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 1.0));
                }

                if (specularOverlay != null)
                {
                    specularOverlay.Background = specularBrush;
                }

                var results = new List<SearchResultItem>
                {
                    new SearchResultItem
                    {
                        Filename = "Quarterly_Financial_Report_2026.docx",
                        FullPath = @"C:\Users\Student\Documents\Finance\Quarterly_Financial_Report_2026.docx",
                        SizeBytes = 245760,
                        MTime = DateTimeOffset.Now.ToUnixTimeSeconds(),
                        Extension = ".docx",
                        Icon = FileIconService.GetIcon(".docx")
                    },
                    new SearchResultItem
                    {
                        Filename = "Design_System_Specification.pdf",
                        FullPath = @"D:\Projects\Findora\docs\Design_System_Specification.pdf",
                        SizeBytes = 4194304,
                        MTime = DateTimeOffset.Now.ToUnixTimeSeconds() - 3600,
                        Extension = ".pdf",
                        Icon = FileIconService.GetIcon(".pdf")
                    },
                    new SearchResultItem
                    {
                        Filename = "findora_core_indexer.py",
                        FullPath = @"D:\Projects\Findora\src\indexer\findora_core_indexer.py",
                        SizeBytes = 18432,
                        MTime = DateTimeOffset.Now.ToUnixTimeSeconds() - 7200,
                        Extension = ".py",
                        Icon = FileIconService.GetIcon(".py")
                    },
                    new SearchResultItem
                    {
                        Filename = "Executive_Summary_Deck.pptx",
                        FullPath = @"C:\Users\Student\OneDrive\Presentations\Executive_Summary_Deck.pptx",
                        SizeBytes = 12582912,
                        MTime = DateTimeOffset.Now.ToUnixTimeSeconds() - 86400,
                        Extension = ".pptx",
                        Icon = FileIconService.GetIcon(".pptx")
                    },
                    new SearchResultItem
                    {
                        Filename = "glass_reflection_specular.png",
                        FullPath = @"D:\Projects\Findora\assets\icons\glass_reflection_specular.png",
                        SizeBytes = 84520,
                        MTime = DateTimeOffset.Now.ToUnixTimeSeconds() - 172800,
                        Extension = ".png",
                        Icon = FileIconService.GetIcon(".png")
                    }
                };

                if (resultsListBox != null)
                {
                    resultsListBox.ItemsSource = results;
                    resultsListBox.SelectedIndex = 0;
                }
                if (searchTextBox != null) searchTextBox.Text = "report";
                if (resultsHeader != null) resultsHeader.Text = "5 results";
                if (prominentSearchTime != null) prominentSearchTime.Text = "0.42 ms";
                if (indexSearchTime != null) indexSearchTime.Text = "0.28 ms";
                if (totalSearchTime != null) totalSearchTime.Text = "0.42 ms";
                if (placeholder != null) placeholder.Visibility = Visibility.Collapsed;

                if (window.Content is UIElement content)
                {
                    content.Measure(new Size(920, 490));
                    content.Arrange(new Rect(0, 0, 920, 490));
                    content.UpdateLayout();
                }

                if (mainCard != null)
                {
                    string path = Path.Combine(outputDir, $"{filePrefix}.png");
                    SaveVisualToPng(mainCard, 1400, 800, path, placeOnDesktop: true, contentWidth: 892, contentHeight: 462, lightDesktop: !isDark);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error in CaptureMainWindow: " + ex);
            }
        }

        private static void CaptureSplash(string outputDir, bool isDark, string filePrefix)
        {
            try
            {
                var splash = new SplashWindow(null!);
                if (splash.Content is UIElement content)
                {
                    content.Measure(new Size(500, 410));
                    content.Arrange(new Rect(0, 0, 500, 410));
                    content.UpdateLayout();

                    string path = Path.Combine(outputDir, $"{filePrefix}.png");
                    SaveVisualToPng(content, 900, 600, path, placeOnDesktop: true, contentWidth: 468, contentHeight: 378, lightDesktop: !isDark);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error in CaptureSplash: " + ex);
            }
        }

        private static void CaptureDesktopWidget(string outputDir, bool isDark, string filePrefix)
        {
            try
            {
                var widget = new DesktopWidget();
                if (widget.Content is UIElement content)
                {
                    content.Measure(new Size(54, 54));
                    content.Arrange(new Rect(0, 0, 54, 54));
                    content.UpdateLayout();

                    string path = Path.Combine(outputDir, $"{filePrefix}.png");
                    SaveVisualToPng(content, 220, 220, path, placeOnDesktop: true, contentWidth: 44, contentHeight: 44, lightDesktop: !isDark);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error in CaptureDesktopWidget: " + ex);
            }
        }

        private static void CaptureSettingsDialog(string outputDir, bool isDark, string filePrefix)
        {
            try
            {
                var dlg = new SettingsDialog(null!);
                if (dlg.Content is UIElement content)
                {
                    content.Measure(new Size(550, 490));
                    content.Arrange(new Rect(0, 0, 550, 490));
                    content.UpdateLayout();

                    string path = Path.Combine(outputDir, $"{filePrefix}.png");
                    SaveVisualToPng(content, 1000, 700, path, placeOnDesktop: true, contentWidth: 522, contentHeight: 462, lightDesktop: !isDark);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error in CaptureSettingsDialog: " + ex);
            }
        }

        private static void CaptureAboutDialog(string outputDir, bool isDark, string filePrefix)
        {
            try
            {
                var dlg = new AboutDialog();
                if (dlg.Content is UIElement content)
                {
                    content.Measure(new Size(480, 360));
                    content.Arrange(new Rect(0, 0, 480, 360));
                    content.UpdateLayout();

                    string path = Path.Combine(outputDir, $"{filePrefix}.png");
                    SaveVisualToPng(content, 900, 600, path, placeOnDesktop: true, contentWidth: 452, contentHeight: 332, lightDesktop: !isDark);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error in CaptureAboutDialog: " + ex);
            }
        }
    }
}
