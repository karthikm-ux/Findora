import os
import sys
import time
import subprocess
import threading
import ctypes
from typing import Dict, Any, List, Optional, Callable
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageDraw, ImageTk

try:
    import win32gui
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

from system_integration import create_app_icon, AutostartManager
from icon_provider import WindowsIconProvider

FileIconRenderer = WindowsIconProvider


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_mtime(timestamp: float) -> str:
    if not timestamp or timestamp <= 0:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
    except Exception:
        return ""


def apply_window_styling(window: tk.Toplevel, alpha: float = 0.98, rounded: bool = True, toolwindow: bool = True):
    """Applies Windows native translucency, rounded corners (DWM), and toolwindow styles."""
    try:
        window.attributes("-alpha", alpha)
    except Exception:
        pass

    window.update_idletasks()
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()

        if rounded and hasattr(ctypes.windll, "dwmapi"):
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
            val = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(val), ctypes.sizeof(val))

            class MARGINS(ctypes.Structure):
                _fields_ = [
                    ("cxLeftWidth", ctypes.c_int),
                    ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int),
                    ("cyBottomHeight", ctypes.c_int),
                ]
            m = MARGINS(1, 1, 1, 1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))

        if toolwindow and WIN32_AVAILABLE:
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_TOOLWINDOW)
    except Exception:
        pass


class DesktopIdleWidget(tk.Toplevel):
    """
    Idle floating magnifying-glass widget pinned to a configurable corner of the desktop.
    Behaves as a true desktop widget, NOT an always-on-top application window:
    - Non-topmost Z-order (HWND_NOTOPMOST) so active application windows sit naturally above it.
    - WS_EX_TOOLWINDOW: hidden from taskbar and Alt-Tab.
    - WS_EX_NOACTIVATE: prevents focus-stealing on click.
    - Left-click summons the centered search interface.
    - Right-click displays context menu.
    - Draggable to any desktop position.
    """
    SIZE = 54
    CHROMA_KEY = "#010203"

    def __init__(
        self,
        parent: tk.Tk,
        on_click: Callable[[], None],
        on_right_click: Callable[[Any], None],
        corner: str = "bottom-right"
    ):
        super().__init__(parent)
        self.on_click = on_click
        self.on_right_click = on_right_click
        self.corner = corner

        self.title("Findora Desktop Widget")
        self.overrideredirect(True)
        self.attributes("-topmost", False)

        try:
            self.wm_attributes("-transparentcolor", self.CHROMA_KEY)
        except Exception:
            pass

        self.canvas = tk.Canvas(
            self,
            width=self.SIZE,
            height=self.SIZE,
            bg=self.CHROMA_KEY,
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.tk_bubble_normal = self._create_bubble_image(hover=False)
        self.tk_bubble_hover = self._create_bubble_image(hover=True)
        self.bubble_item = self.canvas.create_image(self.SIZE // 2, self.SIZE // 2, image=self.tk_bubble_normal)

        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False

        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Button-3>", lambda e: self.on_right_click(e))
        self.canvas.bind("<Enter>", lambda e: self.canvas.itemconfig(self.bubble_item, image=self.tk_bubble_hover))
        self.canvas.bind("<Leave>", lambda e: self.canvas.itemconfig(self.bubble_item, image=self.tk_bubble_normal))

        self.set_corner(self.corner)
        self._apply_desktop_layering()

    def _create_bubble_image(self, size: int = 46, hover: bool = False) -> ImageTk.PhotoImage:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Soft glowing halo
        halo_fill = (186, 230, 253, 170) if hover else (186, 230, 253, 110)
        halo_outline = (56, 189, 248, 220) if hover else (125, 211, 252, 160)
        d.ellipse([1, 1, size - 2, size - 2], fill=halo_fill, outline=halo_outline, width=1)
        # Frosted glass disc
        body_fill = (240, 249, 255, 245) if hover else (224, 242, 254, 230)
        d.ellipse([5, 5, size - 6, size - 6], fill=body_fill, outline=(255, 255, 255, 255), width=2)
        # Vibrant royal blue magnifying glass
        cx, cy = size // 2, size // 2
        r = 6
        d.ellipse([cx - r - 1, cy - r - 1, cx + r - 1, cy + r - 1], outline=(37, 99, 235, 255), width=2)
        d.line([cx + 3, cy + 3, cx + 8, cy + 8], fill=(37, 99, 235, 255), width=2)
        return ImageTk.PhotoImage(img)

    def set_corner(self, corner: str):
        self.corner = corner
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        margin = 20
        taskbar_pad = 54

        if corner == "top-left":
            x = margin
            y = margin
        elif corner == "top-right":
            x = sw - self.SIZE - margin
            y = margin
        elif corner == "bottom-left":
            x = margin
            y = sh - self.SIZE - taskbar_pad
        elif corner == "hidden":
            self.withdraw()
            return
        else:  # default "bottom-right"
            x = sw - self.SIZE - margin
            y = sh - self.SIZE - taskbar_pad

        self.pos_x = x
        self.pos_y = y
        self.geometry(f"{self.SIZE}x{self.SIZE}+{x}+{y}")
        self.deiconify()
        self._apply_desktop_layering()

    def _apply_desktop_layering(self):
        """
        Enforces desktop widget behavior:
        - HWND_NOTOPMOST so active applications (Explorer, browser) sit above it.
        - WS_EX_TOOLWINDOW: excluded from taskbar and Alt-Tab.
        - WS_EX_NOACTIVATE: prevents focus-stealing on click.
        """
        self.update_idletasks()
        if not WIN32_AVAILABLE:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            cur = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, GWL_EXSTYLE, cur | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_NOTOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
            )
        except Exception:
            pass

    def _on_mouse_down(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._is_dragging = False

    def _on_mouse_drag(self, event):
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y
        if abs(dx) > 3 or abs(dy) > 3:
            self._is_dragging = True
            self.pos_x += dx
            self.pos_y += dy
            self.geometry(f"+{self.pos_x}+{self.pos_y}")

    def _on_mouse_up(self, event):
        if not self._is_dragging:
            self.on_click()
        self._is_dragging = False
        self._apply_desktop_layering()


class GlassmorphismSearchWidget(tk.Toplevel):
    """
    Windows 11 Centered Search Interface with Companion Desktop Idle Widget:
    - Idle State: Compact glowing magnifying-glass widget in configurable desktop corner (not always-on-top).
    - Expanded State: Centered modern search interface (Ctrl+Alt+F or click on desktop widget).
    - Windows 11 frosted acrylic design: DWM rounded corners, subtle drop shadows, crisp typography.
    - Search input: 100% visible typing, high contrast, permanent input widget, never stolen or deleted on keystrokes.
    - Dynamic Windows Shell icons for every search result.
    - Arrow navigation, Enter to reveal in File Explorer (/select), Shift+Enter to open file, Escape to dismiss.
    """

    CHROMA_KEY = "#010203"
    WIDGET_WIDTH = 640
    IDLE_HEIGHT = 56
    EXPANDED_BAR_HEIGHT = 58
    ROW_HEIGHT = 52

    def __init__(
        self,
        parent: tk.Tk,
        app_core,
        on_open_settings: Callable[[], None],
        on_status: Callable[[], None],
        on_rescan: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        super().__init__(parent)
        self.app_core = app_core
        self.on_open_settings = on_open_settings
        self.on_status = on_status
        self.on_rescan = on_rescan
        self.on_exit = on_exit

        self.title("Findora - Filename Search")
        self.overrideredirect(True)
        self.attributes("-topmost", False)

        # Center horizontally and position in upper-center (22% from top of screen)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.pos_x = (sw - self.WIDGET_WIDTH) // 2
        self.pos_y = max(80, int(sh * 0.22))

        self.geometry(f"{self.WIDGET_WIDTH}x{self.IDLE_HEIGHT}+{self.pos_x}+{self.pos_y}")
        apply_window_styling(self, alpha=0.98, rounded=True, toolwindow=True)

        self.state = "IDLE"
        self.results: List[Dict[str, Any]] = []
        self.selected_index: int = 0
        self._search_timer = None
        self._is_searching = False

        # Load desktop corner preference from storage if available
        saved_corner = "bottom-right"
        if hasattr(self.app_core, "storage") and self.app_core.storage:
            try:
                saved_corner = self.app_core.storage.get_metadata("desktop_corner", "bottom-right") or "bottom-right"
            except Exception:
                saved_corner = "bottom-right"

        # Initialize Desktop Idle Widget (pinned to desktop corner)
        self.idle_widget = DesktopIdleWidget(
            parent=self,
            on_click=self.expand_search,
            on_right_click=self._on_bubble_right_click,
            corner=saved_corner
        )

        self._init_ui()
        self._init_bindings()

        # Asynchronously preload common file icons in background without blocking UI
        threading.Thread(target=WindowsIconProvider.preload_common_icons, args=(28,), daemon=True).start()

        # Start hidden in IDLE state; desktop widget remains visible
        self.withdraw()
        self.canvas.config(height=self.IDLE_HEIGHT)

    def _init_ui(self):
        # Surface canvas with rounded background
        self.canvas = tk.Canvas(
            self,
            width=self.WIDGET_WIDTH,
            height=self.IDLE_HEIGHT,
            bg="#ffffff",
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Permanent Search Entry field (NEVER destroyed or recreated on search updates)
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            self.canvas,
            textvariable=self.search_var,
            font=("Segoe UI", 13),
            bg="#ffffff",
            fg="#0f172a",
            insertbackground="#2563eb",
            insertwidth=2,
            selectbackground="#bfdbfe",
            selectforeground="#1e3a8a",
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0
        )

        # Result item right-click context menu
        self.result_context_menu = tk.Menu(self, tearoff=0)
        self.result_context_menu.add_command(label="Reveal in File Explorer (Enter)", command=self.reveal_selected)
        self.result_context_menu.add_command(label="Open File (Shift+Enter)", command=self.open_selected)
        self.result_context_menu.add_separator()
        self.result_context_menu.add_command(label="Copy Full Path", command=self.copy_selected_path)
        self.result_context_menu.add_command(label="Copy File Name", command=self.copy_selected_name)
        self.result_context_menu.add_command(label="Copy Containing Folder", command=self.copy_containing_folder)

        # Desktop bubble context menu
        self.bubble_context_menu = tk.Menu(self, tearoff=0)
        self.bubble_context_menu.add_command(label="Open Search (Ctrl+Alt+F)", command=self.expand_search)
        self.bubble_context_menu.add_separator()
        self.bubble_context_menu.add_command(label="Drive & Index Status...", command=self.on_status)
        self.bubble_context_menu.add_command(label="Settings & Exclusions...", command=self.on_open_settings)
        self.bubble_context_menu.add_command(label="Rescan Computer", command=self.on_rescan)
        self.bubble_context_menu.add_separator()
        self.bubble_context_menu.add_command(label="Exit Findora", command=self.on_exit)

        # Draw header elements once with tag "header"
        self._render_header()

    def _render_header(self):
        """Draws the fixed top search bar header. This is never deleted on search result updates."""
        # Clean subtle border on window edge
        self.canvas.create_rectangle(0, 0, self.WIDGET_WIDTH, 56, fill="#ffffff", outline="", tags="header")

        # Left magnifying glass search icon
        self.canvas.create_text(24, 28, text="🔍", font=("Segoe UI", 12), fill="#2563eb", tags="header")

        # Place Entry widget permanently inside canvas
        self.canvas.create_window(48, 28, window=self.search_entry, anchor=tk.W, width=510, tags="header")

        # Clear button (✕)
        self.clear_btn_id = self.canvas.create_text(
            580, 28, text="✕", font=("Segoe UI", 10, "bold"), fill="#94a3b8", tags=("header", "clear_btn")
        )

        # Esc badge pill
        self._draw_round_rect(self.canvas, 600, 16, 628, 40, r=6, fill="#f1f5f9", outline="#e2e8f0", width=1, tags="header")
        self.canvas.create_text(614, 28, text="Esc", font=("Segoe UI", 8, "bold"), fill="#64748b", tags="header")

    def _init_bindings(self):
        # Debounced search trace
        self.search_var.trace_add("write", self._on_text_changed)

        # Keyboard shortcuts inside entry
        self.search_entry.bind("<Down>", self._on_key_down)
        self.search_entry.bind("<Up>", self._on_key_up)
        self.search_entry.bind("<Return>", self._on_key_enter)
        self.search_entry.bind("<Shift-Return>", lambda e: self.open_selected())
        self.search_entry.bind("<Escape>", lambda e: self.collapse_to_idle())

        # Global Escape binding on window
        self.bind("<Escape>", lambda e: self.collapse_to_idle())

        # Canvas clicks and mouse interactions
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Double-1>", lambda e: self.reveal_selected())
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)
        self.canvas.bind("<Motion>", self._on_canvas_motion)

        # Dismiss when focus is lost to another application
        self.bind("<FocusOut>", self._on_focus_out)

    def _draw_round_rect(self, canvas, x1, y1, x2, y2, r=10, **kwargs):
        """Draws a smooth anti-aliased rounded rectangle."""
        points = (
            x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r,
            x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1
        )
        return canvas.create_polygon(points, **kwargs, smooth=True)

    def _render_results(self):
        """
        Renders search results, empty state, or loading state beneath the permanent search header.
        Crucial: Only removes results elements. Never destroys or resets the search entry widget.
        """
        # Delete only dynamic result items and status overlays
        self.canvas.delete("result_item")
        self.canvas.delete("empty_state")
        self.canvas.delete("loading_state")
        self.canvas.delete("divider")

        query = self.search_var.get().strip()

        # Update clear button visibility
        self.canvas.itemconfig(self.clear_btn_id, fill="#64748b" if query else "#ffffff")

        # 1. Empty query: Collapse to search bar only
        if not query:
            self._update_geometry(self.EXPANDED_BAR_HEIGHT)
            return

        # Thin 1px separator line below search bar
        self.canvas.create_line(16, 56, self.WIDGET_WIDTH - 16, 56, fill="#f1f5f9", width=1, tags="divider")

        # 2. Loading state
        if self._is_searching:
            desired_h = 56 + 1 + 60
            self._update_geometry(desired_h)
            self.canvas.create_text(
                self.WIDGET_WIDTH // 2, 88,
                text="Searching computer...", font=("Segoe UI", 9, "italic"), fill="#2563eb", tags="loading_state"
            )
            return

        # 3. No matches: Empty state card
        if not self.results:
            desired_h = 56 + 1 + 96
            self._update_geometry(desired_h)
            self.canvas.create_text(
                self.WIDGET_WIDTH // 2, 86,
                text=f'No matching files found for "{query}"',
                font=("Segoe UI", 11, "bold"), fill="#334155", tags="empty_state"
            )
            self.canvas.create_text(
                self.WIDGET_WIDTH // 2, 114,
                text="Check file spelling or verify excluded directories in Settings.",
                font=("Segoe UI", 9), fill="#64748b", tags="empty_state"
            )
            return

        # 4. Results List
        count = min(len(self.results), 6)
        desired_h = 56 + 1 + count * self.ROW_HEIGHT + 8
        self._update_geometry(desired_h)

        for i, item in enumerate(self.results[:count]):
            ry1 = 60 + i * self.ROW_HEIGHT
            ry2 = ry1 + 48
            is_selected = (i == self.selected_index)

            # Selected row pill
            if is_selected:
                self._draw_round_rect(
                    self.canvas, 10, ry1, self.WIDGET_WIDTH - 10, ry2,
                    r=10, fill="#dbeafe", outline="#bfdbfe", width=1, tags="result_item"
                )
                # Left accent indicator
                self.canvas.create_rectangle(
                    10, ry1 + 10, 14, ry2 - 10, fill="#2563eb", outline="", tags="result_item"
                )
                # Enter shortcut badge
                self.canvas.create_text(
                    self.WIDGET_WIDTH - 24, ry1 + 24,
                    text="↵", font=("Segoe UI", 12, "bold"), fill="#2563eb", tags="result_item"
                )
                self.canvas.create_text(
                    self.WIDGET_WIDTH - 54, ry1 + 24,
                    text="Reveal", font=("Segoe UI", 8, "bold"), fill="#2563eb", tags="result_item"
                )

            # Native Windows Shell file icon (28x28)
            icon_img = FileIconRenderer.get_icon(item.get("full_path") or item.get("extension", ""), size=28)
            self.canvas.create_image(32, ry1 + 24, image=icon_img, tags="result_item")

            # Filename (bold Segoe UI 10.5)
            fname = item["filename"]
            if len(fname) > 42:
                fname = fname[:22] + "..." + fname[-17:]
            self.canvas.create_text(
                54, ry1 + 15,
                anchor=tk.W, text=fname, font=("Segoe UI", 11, "bold"),
                fill="#0f172a" if is_selected else "#1e293b", tags="result_item"
            )

            # Full path breadcrumb (muted Segoe UI 9)
            fpath = item["full_path"]
            if len(fpath) > 54:
                fpath = fpath[:24] + "..." + fpath[-27:]
            self.canvas.create_text(
                54, ry1 + 33,
                anchor=tk.W, text=fpath, font=("Segoe UI", 9), fill="#64748b", tags="result_item"
            )

            # File size badge
            size_str = format_size(item.get("size_bytes", 0))
            self.canvas.create_text(
                self.WIDGET_WIDTH - 128, ry1 + 24,
                anchor=tk.E, text=size_str, font=("Segoe UI", 9), fill="#475569", tags="result_item"
            )

            # Modified date
            mtime_str = format_mtime(item.get("mtime", 0))
            if mtime_str:
                date_part = mtime_str.split()[0]
                self.canvas.create_text(
                    self.WIDGET_WIDTH - 82, ry1 + 24,
                    anchor=tk.W, text=date_part, font=("Segoe UI", 8), fill="#94a3b8", tags="result_item"
                )

    def _update_geometry(self, height: int):
        self.geometry(f"{self.WIDGET_WIDTH}x{height}+{self.pos_x}+{self.pos_y}")
        self.canvas.config(height=height)

    def expand_search(self):
        """Reveals the centered modern search interface and provides immediate keyboard focus."""
        self.state = "EXPANDED"
        self.deiconify()
        self.attributes("-topmost", True)
        self.lift()

        # Bring window to foreground in Windows OS
        if WIN32_AVAILABLE:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass

        # Give immediate focus and select text in entry
        self.search_entry.focus_force()
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

        self._render_results()

    def collapse_to_idle(self):
        """Collapses search window and returns to idle desktop widget."""
        self.state = "IDLE"
        if self._search_timer:
            self.after_cancel(self._search_timer)
            self._search_timer = None
        self.withdraw()
        self.attributes("-topmost", False)
        self.canvas.config(height=self.IDLE_HEIGHT)
        self.idle_widget.set_corner(self.idle_widget.corner)

    def toggle_widget(self):
        """Toggles between IDLE and EXPANDED state."""
        if self.state == "IDLE":
            self.expand_search()
        else:
            self.collapse_to_idle()

    def show_widget(self):
        self.expand_search()

    def hide_widget(self):
        self.collapse_to_idle()

    def _on_text_changed(self, *args):
        if self.state != "EXPANDED":
            return
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(60, self._execute_search)

    def _execute_search(self):
        query = self.search_var.get().strip()
        if not query:
            self.results = []
            self.selected_index = 0
            self._is_searching = False
            self._render_results()
            return

        self._is_searching = False

        # Query custom B+ Tree
        search_matches = self.app_core.tree.search_query(query, limit=6)

        # Unpack duplicate paths
        all_paths = []
        unpacked_items = []
        for filename, paths in search_matches:
            for p in paths:
                all_paths.append(p)
                unpacked_items.append((filename, p))

        # Batch fetch metadata from SQLite (< 1ms)
        meta_dict = {}
        if hasattr(self.app_core, "storage") and self.app_core.storage:
            meta_dict = self.app_core.storage.get_files_metadata_batch(all_paths)

        self.results = []
        for filename, full_path in unpacked_items[:6]:
            m = meta_dict.get(full_path, {})
            self.results.append({
                "filename": filename,
                "full_path": full_path,
                "size_bytes": m.get("size_bytes", 0),
                "mtime": m.get("mtime", 0.0),
                "extension": m.get("extension", os.path.splitext(filename)[1]).lower()
            })

        self.selected_index = 0
        self._render_results()

    def _on_key_down(self, event):
        if self.results:
            self.selected_index = (self.selected_index + 1) % len(self.results)
            self._render_results()
        return "break"

    def _on_key_up(self, event):
        if self.results:
            self.selected_index = (self.selected_index - 1) % len(self.results)
            self._render_results()
        return "break"

    def _on_key_enter(self, event):
        self.reveal_selected()
        return "break"

    def _on_canvas_click(self, event):
        # Clicked clear button (✕)
        if event.y <= 56 and 570 <= event.x <= 595:
            self.search_var.set("")
            self.search_entry.focus_set()
            return

        # Clicked result row
        if self.results and event.y >= 60:
            idx = int((event.y - 60) // self.ROW_HEIGHT)
            if 0 <= idx < len(self.results):
                self.selected_index = idx
                self._render_results()

    def _on_canvas_motion(self, event):
        if self.results and event.y >= 60:
            idx = int((event.y - 60) // self.ROW_HEIGHT)
            if 0 <= idx < len(self.results) and idx != self.selected_index:
                self.selected_index = idx
                self._render_results()

    def _on_canvas_right_click(self, event):
        if self.results and event.y >= 60:
            idx = int((event.y - 60) // self.ROW_HEIGHT)
            if 0 <= idx < len(self.results):
                self.selected_index = idx
                self._render_results()
                self.result_context_menu.post(event.x_root, event.y_root)

    def _on_bubble_right_click(self, event):
        self.bubble_context_menu.post(event.x_root, event.y_root)

    def _on_focus_out(self, event):
        self.after(150, self._check_focus_loss)

    def _check_focus_loss(self):
        if self.state == "EXPANDED" and WIN32_AVAILABLE:
            try:
                fg = win32gui.GetForegroundWindow()
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
                if fg and fg != hwnd and fg != self.winfo_id():
                    self.collapse_to_idle()
            except Exception:
                pass

    def get_selected_path(self) -> Optional[str]:
        if self.results and 0 <= self.selected_index < len(self.results):
            return self.results[self.selected_index]["full_path"]
        return None

    def get_selected_name(self) -> Optional[str]:
        if self.results and 0 <= self.selected_index < len(self.results):
            return self.results[self.selected_index]["filename"]
        return None

    def reveal_selected(self):
        """Reveals selected file in Windows File Explorer with file highlighted."""
        path = self.get_selected_path()
        if path and os.path.exists(path):
            try:
                subprocess.Popen(["explorer.exe", f"/select,{os.path.normpath(path)}"])
            except Exception as e:
                messagebox.showerror("Error", f"Failed to reveal in Explorer:\n{e}")
        elif path:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                os.startfile(folder)
            else:
                messagebox.showwarning("File Missing", f"File does not exist on disk:\n{path}")
        self.collapse_to_idle()

    def open_selected(self):
        """Opens selected file directly."""
        path = self.get_selected_path()
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file:\n{e}")
        elif path:
            messagebox.showwarning("File Missing", f"File does not exist:\n{path}")
        self.collapse_to_idle()

    def copy_selected_path(self):
        path = self.get_selected_path()
        if path:
            self.clipboard_clear()
            self.clipboard_append(path)

    def copy_selected_name(self):
        name = self.get_selected_name()
        if name:
            self.clipboard_clear()
            self.clipboard_append(name)

    def copy_containing_folder(self):
        path = self.get_selected_path()
        if path:
            self.clipboard_clear()
            self.clipboard_append(os.path.dirname(path))

    def destroy(self):
        try:
            self.idle_widget.destroy()
        except Exception:
            pass
        super().destroy()


# Compatibility alias for existing references
FloatingSearchWidget = GlassmorphismSearchWidget


class DriveStatusDialog(tk.Toplevel):
    def __init__(self, parent, storage, scanner=None):
        super().__init__(parent)
        self.title("Drive & Indexing Status")
        self.geometry("680x440")
        self.transient(parent)
        self.grab_set()

        self.storage = storage
        self.scanner = scanner

        main_frame = ttk.Frame(self, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Discovered Drives & Status", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))

        columns = ("drive", "label", "fs", "status", "files", "free", "last_sync")
        self.tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=5)
        self.tree.heading("drive", text="Drive")
        self.tree.heading("label", text="Label")
        self.tree.heading("fs", text="FS")
        self.tree.heading("status", text="Status")
        self.tree.heading("files", text="Files")
        self.tree.heading("free", text="Free Space")
        self.tree.heading("last_sync", text="Last Sync")

        self.tree.column("drive", width=60, anchor=tk.CENTER)
        self.tree.column("label", width=100)
        self.tree.column("fs", width=60, anchor=tk.CENTER)
        self.tree.column("status", width=90, anchor=tk.CENTER)
        self.tree.column("files", width=80, anchor=tk.E)
        self.tree.column("free", width=90, anchor=tk.E)
        self.tree.column("last_sync", width=140)

        self.tree.pack(fill=tk.BOTH, expand=False, pady=(0, 12))

        ttk.Label(main_frame, text="Inaccessible / Access-Denied Locations", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(6, 4))
        self.inaccessible_box = tk.Listbox(main_frame, font=("Segoe UI", 9), height=7)
        self.inaccessible_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.RIGHT)

        self.populate_data()

    def populate_data(self):
        drives = self.storage.get_drives()
        for d in drives:
            free_str = format_size(d.get("free_bytes", 0)) if d.get("free_bytes") else "N/A"
            sync_str = format_mtime(d.get("last_sync_time", 0))
            self.tree.insert("", tk.END, values=(
                d.get("drive_letter", ""),
                d.get("label", ""),
                d.get("fs_type", ""),
                d.get("status", "unknown").capitalize(),
                f"{d.get('file_count', 0):,}",
                free_str,
                sync_str
            ))

        if self.scanner and self.scanner.inaccessible_paths:
            for p in self.scanner.inaccessible_paths:
                self.inaccessible_box.insert(tk.END, p)
        else:
            self.inaccessible_box.insert(tk.END, "(No inaccessible locations reported)")


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, storage, on_exclusions_changed=None, on_corner_changed=None):
        super().__init__(parent)
        self.title("Settings & Exclusions")
        self.geometry("620x530")
        self.transient(parent)
        self.grab_set()

        self.storage = storage
        self.on_exclusions_changed = on_exclusions_changed
        self.on_corner_changed = on_corner_changed

        main_frame = ttk.Frame(self, padding="14")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Autostart checkbox
        self.autostart_var = tk.BooleanVar(value=AutostartManager.is_enabled())
        autostart_chk = ttk.Checkbutton(
            main_frame,
            text="Launch Findora automatically on Windows startup",
            variable=self.autostart_var,
            command=self.toggle_autostart
        )
        autostart_chk.pack(anchor=tk.W, pady=(0, 10))

        # Desktop Widget Corner Configuration
        corner_frame = ttk.LabelFrame(main_frame, text="Desktop Idle Widget Position", padding="8")
        corner_frame.pack(fill=tk.X, pady=(0, 12))

        current_corner = "bottom-right"
        if hasattr(self.storage, "get_metadata"):
            current_corner = self.storage.get_metadata("desktop_corner", "bottom-right") or "bottom-right"

        self.corner_var = tk.StringVar(value=current_corner)
        c_combo = ttk.Combobox(
            corner_frame,
            textvariable=self.corner_var,
            values=["bottom-right", "top-right", "bottom-left", "top-left", "hidden"],
            state="readonly",
            width=25
        )
        c_combo.pack(side=tk.LEFT, padx=(0, 8))
        c_combo.bind("<<ComboboxSelected>>", self._on_corner_selected)
        ttk.Label(corner_frame, text="(Configurable desktop corner)", font=("Segoe UI", 8)).pack(side=tk.LEFT)

        # Shortcut information
        hotkey_frame = ttk.LabelFrame(main_frame, text="Search Shortcut", padding="8")
        hotkey_frame.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(
            hotkey_frame,
            text="Global Shortcut: Ctrl + Alt + F\nPressing this shortcut summons the centered search interface from any application.",
            font=("Segoe UI", 9)
        ).pack(anchor=tk.W)

        # Exclusion list
        ex_frame = ttk.LabelFrame(main_frame, text="Excluded Folders & Patterns", padding="8")
        ex_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        self.ex_listbox = tk.Listbox(ex_frame, font=("Segoe UI", 9), selectmode=tk.SINGLE)
        self.ex_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=(0, 8))

        sb = ttk.Scrollbar(ex_frame, orient=tk.VERTICAL, command=self.ex_listbox.yview)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        self.ex_listbox.config(yscrollcommand=sb.set)

        ex_btn_frame = ttk.Frame(ex_frame)
        ex_btn_frame.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Button(ex_btn_frame, text="Add Folder...", command=self.add_folder_exclusion).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(ex_btn_frame, text="Add Pattern...", command=self.add_pattern_exclusion).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(ex_btn_frame, text="Remove", command=self.remove_exclusion).pack(fill=tk.X)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Done", command=self.destroy).pack(side=tk.RIGHT)

        self.populate_exclusions()

    def _on_corner_selected(self, event=None):
        val = self.corner_var.get()
        if hasattr(self.storage, "set_metadata"):
            self.storage.set_metadata("desktop_corner", val)
        if self.on_corner_changed:
            self.on_corner_changed(val)

    def toggle_autostart(self):
        if self.autostart_var.get():
            success = AutostartManager.enable()
            if not success:
                messagebox.showerror("Error", "Failed to enable autostart in Windows Registry.")
                self.autostart_var.set(False)
        else:
            success = AutostartManager.disable()
            if not success:
                messagebox.showerror("Error", "Failed to disable autostart in Windows Registry.")
                self.autostart_var.set(True)

    def populate_exclusions(self):
        self.ex_listbox.delete(0, tk.END)
        for item in self.storage.get_exclusions():
            self.ex_listbox.insert(tk.END, item["pattern"])

    def add_folder_exclusion(self):
        folder = filedialog.askdirectory(parent=self, title="Select Folder to Exclude")
        if folder:
            self.storage.add_exclusion(os.path.normpath(folder))
            self.populate_exclusions()
            if self.on_exclusions_changed:
                self.on_exclusions_changed()

    def add_pattern_exclusion(self):
        pattern_win = tk.Toplevel(self)
        pattern_win.title("Add Pattern Exclusion")
        pattern_win.geometry("380x130")
        pattern_win.transient(self)
        pattern_win.grab_set()

        f = ttk.Frame(pattern_win, padding="10")
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="Enter folder name, file pattern, or path:").pack(anchor=tk.W, pady=(0, 4))
        entry = ttk.Entry(f, width=40)
        entry.pack(fill=tk.X, pady=(0, 8))
        entry.focus()

        def save():
            pat = entry.get().strip()
            if pat:
                self.storage.add_exclusion(pat)
                self.populate_exclusions()
                if self.on_exclusions_changed:
                    self.on_exclusions_changed()
                pattern_win.destroy()

        b_frame = ttk.Frame(f)
        b_frame.pack(fill=tk.X)
        ttk.Button(b_frame, text="Add", command=save).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(b_frame, text="Cancel", command=pattern_win.destroy).pack(side=tk.RIGHT)

    def remove_exclusion(self):
        sel = self.ex_listbox.curselection()
        if sel:
            pattern = self.ex_listbox.get(sel[0])
            self.storage.remove_exclusion(pattern)
            self.populate_exclusions()
            if self.on_exclusions_changed:
                self.on_exclusions_changed()
