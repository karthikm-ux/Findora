using System.Windows;
using Findora.Wpf.Services;

namespace Findora.Wpf.Views
{
    public partial class AboutDialog : Window
    {
        public AboutDialog()
        {
            InitializeComponent();
        }

        private void Window_Loaded(object sender, RoutedEventArgs e)
        {
            WindowBackdropHelper.TryEnableBlur(this);
            ThemeManager.ThemeChanged += isDark => WindowBackdropHelper.TryEnableBlur(this);
        }

        private void CloseButton_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }
    }
}
