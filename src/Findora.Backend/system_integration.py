import os
import sys
import threading
import ctypes
from ctypes import wintypes
import winreg
from typing import Optional, Callable
from PIL import Image, ImageDraw

try:
    import pystray
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

try:
    import win32event
    import win32api
    import winerror
    import win32gui
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


def create_app_icon(size: int = 64) -> Image.Image:
    """Creates a clean modern search icon for the tray and window."""
    img = Image.new("RGBA", (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = int(size * 0.05)
    radius = int(size * 0.2)
    draw.rounded_rectangle([margin, margin, size - margin, size - margin], radius=radius, fill=(0, 120, 215))
    cx1 = int(size * 0.22)
    cy1 = int(size * 0.22)
    cx2 = int(size * 0.60)
    cy2 = int(size * 0.60)
    draw.ellipse([cx1, cy1, cx2, cy2], outline="white", width=max(2, int(size * 0.07)))
    hx1 = int(size * 0.52)
    hy1 = int(size * 0.52)
    hx2 = int(size * 0.78)
    hy2 = int(size * 0.78)
    draw.line([hx1, hy1, hx2, hy2], fill="white", width=max(2, int(size * 0.08)))
    return img


def create_floating_icon_image(size: int = 48) -> Image.Image:
    """
    Creates a translucent circular floating desktop widget icon with a subtle drop shadow
    and a crisp magnifying glass.
    """
    img = Image.new("RGBA", (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Translucent rounded circle with restrained blue accent outline
    draw.ellipse([2, 2, size - 3, size - 3], fill=(24, 28, 36, 220), outline=(0, 120, 215, 235), width=2)

    # Magnifying glass circle
    cx = size * 0.44
    cy = size * 0.44
    r = size * 0.17
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 240), width=2)

    # Magnifying glass handle
    hx1 = cx + r * 0.68
    hy1 = cy + r * 0.68
    hx2 = cx + r * 1.75
    hy2 = cy + r * 1.75
    draw.line([hx1, hy1, hx2, hy2], fill=(51, 153, 255, 255), width=3)
    return img


class SingleInstanceChecker:
    """
    Enforces a single application instance to avoid duplicate hotkey registrations,
    conflicting background workers, and focus-stealing behavior.
    """

    def __init__(self, mutex_name: str = "Findora_SingleInstance_Mutex_2026"):
        self.mutex_name = mutex_name
        self.mutex = None
        self._is_already_running = False

        if WIN32_AVAILABLE:
            try:
                self.mutex = win32event.CreateMutex(None, False, self.mutex_name)
                if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                    self._is_already_running = True
            except Exception:
                self._is_already_running = False

    def is_already_running(self) -> bool:
        return self._is_already_running

    def notify_existing_instance(self):
        """Attempts to bring the existing instance's search widget to the front."""
        if WIN32_AVAILABLE:
            try:
                hwnd = win32gui.FindWindow(None, "Findora Search")
                if not hwnd:
                    hwnd = win32gui.FindWindow(None, "Findora - Floating Search")
                if not hwnd:
                    hwnd = win32gui.FindWindow(None, "FastRetrival - Floating Search")
                if hwnd:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass

    def cleanup(self):
        if self.mutex and WIN32_AVAILABLE:
            try:
                win32api.CloseHandle(self.mutex)
            except Exception:
                pass
            self.mutex = None


class AutostartManager:
    """
    Manages Windows autostart at user login via HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
    """

    RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "Findora"
    LEGACY_APP_NAME = "FastRetrival"

    @classmethod
    def is_enabled(cls) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, cls.APP_NAME)
                    if val:
                        return True
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, cls.LEGACY_APP_NAME)
                    return bool(val)
                except OSError:
                    return False
        except OSError:
            return False

    @classmethod
    def enable(cls, target_script: Optional[str] = None) -> bool:
        try:
            if not target_script:
                target_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))

            python_exe = sys.executable
            pythonw = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
            if os.path.exists(pythonw):
                cmd = f'"{pythonw}" "{target_script}" --background'
            else:
                cmd = f'"{python_exe}" "{target_script}" --background'

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.RUN_KEY_PATH, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, cls.APP_NAME, 0, winreg.REG_SZ, cmd)
                # Clean up legacy startup entry if present
                try:
                    winreg.DeleteValue(key, cls.LEGACY_APP_NAME)
                except OSError:
                    pass
            return True
        except OSError:
            return False

    @classmethod
    def disable(cls) -> bool:
        success = False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.RUN_KEY_PATH, 0, winreg.KEY_WRITE) as key:
                try:
                    winreg.DeleteValue(key, cls.APP_NAME)
                    success = True
                except OSError:
                    pass
                try:
                    winreg.DeleteValue(key, cls.LEGACY_APP_NAME)
                    success = True
                except OSError:
                    pass
        except OSError:
            pass
        return success


class HotkeyListener:
    """
    Registers a global Windows hotkey (Ctrl+Alt+F) to summon the floating search bar
    from anywhere in Windows. Runs a dedicated message pump in a daemon thread.
    """

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    HOTKEY_ID_CTRL_ALT_F = 8899
    HOTKEY_ID_ALT_SPACE = 8898

    def __init__(
        self,
        callback: Callable[[], None],
    ):
        self.callback = callback
        self._thread: Optional[threading.Thread] = None
        self._thread_id = None
        self._is_running = False
        self._is_registered = False

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._run, name="FastRetrival-Hotkey", daemon=True)
        self._thread.start()

    def stop(self):
        if not self._is_running:
            return
        self._is_running = False
        if self._thread_id:
            user32 = ctypes.windll.user32
            user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def is_registered(self) -> bool:
        return self._is_registered

    def _run(self):
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        self._thread_id = kernel32.GetCurrentThreadId()

        # Register both Ctrl+Alt+F and Alt+Space
        s1 = user32.RegisterHotKey(None, self.HOTKEY_ID_CTRL_ALT_F, self.MOD_CONTROL | self.MOD_ALT, 0x46) # 'F'
        s2 = user32.RegisterHotKey(None, self.HOTKEY_ID_ALT_SPACE, self.MOD_ALT, 0x20) # Space
        self._is_registered = bool(s1 or s2)

        msg = wintypes.MSG()
        try:
            while self._is_running:
                b_ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if b_ret == 0 or b_ret == -1:
                    break
                if msg.message == self.WM_HOTKEY and msg.wParam in (self.HOTKEY_ID_CTRL_ALT_F, self.HOTKEY_ID_ALT_SPACE):
                    try:
                        self.callback()
                    except Exception:
                        pass
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if s1:
                user32.UnregisterHotKey(None, self.HOTKEY_ID_CTRL_ALT_F)
            if s2:
                user32.UnregisterHotKey(None, self.HOTKEY_ID_ALT_SPACE)
            self._is_registered = False


class TrayIconManager:
    """
    Manages the system-tray icon via pystray.
    Provides options to toggle search widget, toggle floating desktop icon, view drive status,
    rescan drives, open settings, or exit.
    """

    def __init__(
        self,
        on_open_search: Callable[[], None],
        on_toggle_floating_icon: Callable[[], None],
        on_rescan: Callable[[], None],
        on_status: Callable[[], None],
        on_settings: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        self.on_open_search = on_open_search
        self.on_toggle_floating_icon = on_toggle_floating_icon
        self.on_rescan = on_rescan
        self.on_status = on_status
        self.on_settings = on_settings
        self.on_exit = on_exit

        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if not PYSTRAY_AVAILABLE:
            return

        image = create_app_icon(64)
        menu = pystray.Menu(
            pystray.MenuItem("Open Search (Ctrl+Alt+F)", lambda icon, item: self.on_open_search(), default=True),
            pystray.MenuItem("Toggle Floating Desktop Icon", lambda icon, item: self.on_toggle_floating_icon()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Indexing Status...", lambda icon, item: self.on_status()),
            pystray.MenuItem("Rescan Computer", lambda icon, item: self.on_rescan()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings & Exclusions...", lambda icon, item: self.on_settings()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: self.on_exit())
        )

        self._icon = pystray.Icon("FastRetrival", image, "FastRetrival - File Search (Ctrl+Alt+F)", menu)
        self._thread = threading.Thread(target=self._icon.run, name="FastRetrival-TrayIcon", daemon=True)
        self._thread.start()

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
