using System;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;

namespace Findora.Wpf.Services
{
    /// <summary>
    /// Manages the real-time optical light model and interactive specular dynamics
    /// that reproduce the visual behavior of Apple's Liquid Glass material.
    /// </summary>
    public class LiquidGlassController
    {
        private readonly FrameworkElement _targetElement;
        private Point _targetPointer = new Point(0.5, 0.2);
        private Point _currentPointer = new Point(0.5, 0.2);
        private bool _isPointerInside = false;
        private bool _isPressed = false;
        private bool _isHooked = false;

        public bool IsPointerInside => _isPointerInside;
        public RadialGradientBrush SpecularBrush { get; private set; }
        public LinearGradientBrush EdgeHighlightBrush { get; private set; }
        public LinearGradientBrush CausticBevelBrush { get; private set; }

        public event Action? VisualsUpdated;

        public LiquidGlassController(FrameworkElement targetElement)
        {
            _targetElement = targetElement ?? throw new ArgumentNullException(nameof(targetElement));

            // Initialize dynamic brushes
            SpecularBrush = new RadialGradientBrush
            {
                Center = new Point(0.5, 0.2),
                GradientOrigin = new Point(0.5, 0.2),
                RadiusX = 0.55,
                RadiusY = 0.55
            };

            EdgeHighlightBrush = new LinearGradientBrush
            {
                StartPoint = new Point(0, 0),
                EndPoint = new Point(1, 0)
            };

            CausticBevelBrush = new LinearGradientBrush
            {
                StartPoint = new Point(0, 0),
                EndPoint = new Point(0, 1)
            };

            UpdateBrushesForTheme(ThemeManager.IsDark);
            ThemeManager.ThemeChanged += UpdateBrushesForTheme;
        }

        public void Attach()
        {
            if (_isHooked) return;

            _targetElement.MouseMove += OnMouseMove;
            _targetElement.MouseEnter += OnMouseEnter;
            _targetElement.MouseLeave += OnMouseLeave;
            _targetElement.PreviewMouseDown += OnMouseDown;
            _targetElement.PreviewMouseUp += OnMouseUp;

            CompositionTarget.Rendering += OnCompositionRendering;
            _isHooked = true;
        }

        public void Detach()
        {
            if (!_isHooked) return;

            _targetElement.MouseMove -= OnMouseMove;
            _targetElement.MouseEnter -= OnMouseEnter;
            _targetElement.MouseLeave -= OnMouseLeave;
            _targetElement.PreviewMouseDown -= OnMouseDown;
            _targetElement.PreviewMouseUp -= OnMouseUp;

            CompositionTarget.Rendering -= OnCompositionRendering;
            _isHooked = false;
        }

        private void OnMouseMove(object sender, MouseEventArgs e)
        {
            if (_targetElement.ActualWidth <= 0 || _targetElement.ActualHeight <= 0) return;

            Point pos = e.GetPosition(_targetElement);
            double nx = Math.Clamp(pos.X / _targetElement.ActualWidth, 0.0, 1.0);
            double ny = Math.Clamp(pos.Y / _targetElement.ActualHeight, 0.0, 1.0);

            _targetPointer = new Point(nx, ny);
            _isPointerInside = true;
        }

        private void OnMouseEnter(object sender, MouseEventArgs e)
        {
            _isPointerInside = true;
            SpecularBrush.Opacity = 0.95;
        }

        private void OnMouseLeave(object sender, MouseEventArgs e)
        {
            _isPointerInside = false;
            SpecularBrush.Opacity = 0.55;
            // Smoothly drift back to a natural resting top-center specular position
            _targetPointer = new Point(0.5, 0.15);
        }

        private void OnMouseDown(object sender, MouseButtonEventArgs e)
        {
            _isPressed = true;
            UpdateSpecularIntensity();
        }

        private void OnMouseUp(object sender, MouseButtonEventArgs e)
        {
            _isPressed = false;
            UpdateSpecularIntensity();
        }

        private void OnCompositionRendering(object? sender, EventArgs e)
        {
            // Smooth fluid lerp dampening (speed factor = 0.12)
            double lerp = 0.12;
            double dx = _targetPointer.X - _currentPointer.X;
            double dy = _targetPointer.Y - _currentPointer.Y;

            if (Math.Abs(dx) > 0.0005 || Math.Abs(dy) > 0.0005)
            {
                _currentPointer = new Point(
                    _currentPointer.X + dx * lerp,
                    _currentPointer.Y + dy * lerp
                );

                SpecularBrush.Center = _currentPointer;
                SpecularBrush.GradientOrigin = _currentPointer;

                // Subtle dynamic shifting of top edge reflection based on horizontal cursor pos
                double leftStop = Math.Clamp(_currentPointer.X - 0.35, 0.0, 0.6);
                double centerStop = _currentPointer.X;
                double rightStop = Math.Clamp(_currentPointer.X + 0.35, 0.4, 1.0);

                if (EdgeHighlightBrush.GradientStops.Count >= 5)
                {
                    EdgeHighlightBrush.GradientStops[1].Offset = leftStop;
                    EdgeHighlightBrush.GradientStops[2].Offset = centerStop;
                    EdgeHighlightBrush.GradientStops[3].Offset = rightStop;
                }

                VisualsUpdated?.Invoke();
            }
        }

        public void UpdateBrushesForTheme(bool isDark)
        {
            if (isDark)
            {
                // Dark Mode: Smoky Sapphire / Obsidian Liquid Glass
                // 1. Dynamic Specular Sheen (Soft, organic, non-neon light reflection)
                SpecularBrush.GradientStops.Clear();
                SpecularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(55, 255, 255, 255), 0.0));
                SpecularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(28, 56, 189, 248), 0.35));
                SpecularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(10, 14, 165, 233), 0.65));
                SpecularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, 0, 0, 0), 1.0));

                // 2. Edge Specular Highlight (Physical light catch on glass curved bevel)
                EdgeHighlightBrush.GradientStops.Clear();
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 0.0));
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(60, 255, 255, 255), 0.2));
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(110, 255, 255, 255), 0.5));
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(60, 255, 255, 255), 0.8));
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 1.0));

                // 3. Caustic Bevel & Inner Reflection
                CausticBevelBrush.GradientStops.Clear();
                CausticBevelBrush.GradientStops.Add(new GradientStop(Color.FromArgb(90, 255, 255, 255), 0.0));
                CausticBevelBrush.GradientStops.Add(new GradientStop(Color.FromArgb(35, 56, 189, 248), 0.3));
                CausticBevelBrush.GradientStops.Add(new GradientStop(Color.FromArgb(18, 14, 165, 233), 0.7));
                CausticBevelBrush.GradientStops.Add(new GradientStop(Color.FromArgb(30, 255, 255, 255), 1.0));
            }
            else
            {
                // Light Mode: Pure Optical Crystal / Frosted Quartz Glass
                SpecularBrush.GradientStops.Clear();
                SpecularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(110, 255, 255, 255), 0.0));
                SpecularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(60, 255, 255, 255), 0.3));
                SpecularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(25, 2, 132, 199), 0.6));
                SpecularBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 1.0));

                EdgeHighlightBrush.GradientStops.Clear();
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 0.0));
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(120, 255, 255, 255), 0.2));
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(200, 255, 255, 255), 0.5));
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(120, 255, 255, 255), 0.8));
                EdgeHighlightBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 1.0));

                CausticBevelBrush.GradientStops.Clear();
                CausticBevelBrush.GradientStops.Add(new GradientStop(Color.FromArgb(160, 255, 255, 255), 0.0));
                CausticBevelBrush.GradientStops.Add(new GradientStop(Color.FromArgb(50, 148, 163, 184), 0.4));
                CausticBevelBrush.GradientStops.Add(new GradientStop(Color.FromArgb(25, 2, 132, 199), 0.8));
                CausticBevelBrush.GradientStops.Add(new GradientStop(Color.FromArgb(90, 255, 255, 255), 1.0));
            }
        }

        private void UpdateSpecularIntensity()
        {
            // When pressed, gently compress specular radius to simulate physical tactile contact
            SpecularBrush.RadiusX = _isPressed ? 0.42 : 0.55;
            SpecularBrush.RadiusY = _isPressed ? 0.42 : 0.55;
        }
    }
}
