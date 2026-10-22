import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "Findora.Backend")))
from system_integration import AutostartManager, create_app_icon, HotkeyListener


class TestSystemIntegration(unittest.TestCase):

    def test_create_app_icon(self):
        icon = create_app_icon(32)
        self.assertIsNotNone(icon)
        self.assertEqual(icon.size, (32, 32))

    def test_autostart_manager_query(self):
        # Test query does not crash
        status = AutostartManager.is_enabled()
        self.assertIsInstance(status, bool)

    def test_hotkey_listener_start_stop(self):
        triggered = []
        listener = HotkeyListener(callback=lambda: triggered.append(1))
        listener.start()
        listener.stop()
        self.assertEqual(len(triggered), 0)

    def test_create_floating_icon_image(self):
        from system_integration import create_floating_icon_image
        img = create_floating_icon_image(48)
        self.assertIsNotNone(img)
        self.assertEqual(img.size, (48, 48))

    def test_single_instance_checker(self):
        from system_integration import SingleInstanceChecker
        c1 = SingleInstanceChecker(mutex_name="FastRetrival_Test_Mutex_SI")
        self.assertFalse(c1.is_already_running())
        c2 = SingleInstanceChecker(mutex_name="FastRetrival_Test_Mutex_SI")
        self.assertTrue(c2.is_already_running())
        c1.cleanup()
        c2.cleanup()


if __name__ == "__main__":
    unittest.main()

