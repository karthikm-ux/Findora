import os
import sys
import threading
import ctypes
from ctypes import wintypes
from typing import Dict, Tuple, Optional
from PIL import Image, ImageDraw, ImageTk


# Windows API constants
SHGFI_ICON = 0x000000100
SHGFI_LARGEICON = 0x000000000
SHGFI_SMALLICON = 0x000000001
SHGFI_USEFILEATTRIBUTES = 0x000000010
FILE_ATTRIBUTE_NORMAL = 0x00000080
DI_NORMAL = 0x0003


class SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


class WindowsIconProvider:
    """
    Retrieves dynamic, native Windows Shell file-type icons via SHGetFileInfoW
    for arbitrary file extensions without maintaining hardcoded lists.
    Uses SHGFI_USEFILEATTRIBUTES so files are never opened or launched on disk.
    Caches icon resources and cleanly destroys native HICON and GDI handles.
    """

    _cache: Dict[Tuple[str, int], ImageTk.PhotoImage] = {}
    _pil_cache: Dict[Tuple[str, int], Image.Image] = {}
    _lock = threading.Lock()

    @classmethod
    def normalize_extension(cls, ext_or_path: str) -> str:
        """Extracts and normalizes extension (e.g. '.docx', '.pdf', '.default')."""
        if not ext_or_path:
            return ".default"
        # If full path or filename passed
        _, ext = os.path.splitext(ext_or_path)
        if not ext:
            ext = ext_or_path if ext_or_path.startswith(".") else f".{ext_or_path}"
        ext_clean = ext.lower().strip()
        return ext_clean if ext_clean != "." else ".default"

    @classmethod
    def get_icon(cls, ext_or_path: str, size: int = 26) -> ImageTk.PhotoImage:
        """
        Retrieves the associated Windows file icon for the given extension or path,
        scaled to (size, size). Returns a cached PhotoImage if available.
        """
        ext = cls.normalize_extension(ext_or_path)
        cache_key = (ext, size)

        with cls._lock:
            if cache_key in cls._cache:
                return cls._cache[cache_key]

        # Get or generate PIL image
        pil_img = cls.get_pil_icon(ext, size)

        # Convert to PhotoImage (must be created on UI thread)
        with cls._lock:
            if cache_key not in cls._cache:
                photo = ImageTk.PhotoImage(pil_img)
                cls._cache[cache_key] = photo
            return cls._cache[cache_key]

    @classmethod
    def get_pil_icon(cls, ext_or_path: str, size: int = 26) -> Image.Image:
        """
        Returns a PIL RGBA Image for the file extension.
        Queries Windows Shell via SHGetFileInfoW, with fallback to vector drawing.
        """
        ext = cls.normalize_extension(ext_or_path)
        cache_key = (ext, size)

        with cls._lock:
            if cache_key in cls._pil_cache:
                return cls._pil_cache[cache_key]

        pil_img = None
        if sys.platform == "win32":
            try:
                pil_img = cls._extract_windows_shell_icon(ext, 32)
            except Exception:
                pil_img = None

        if pil_img is None:
            pil_img = cls._create_fallback_icon(ext, 32)

        # Scale to requested size preserving high visual quality
        if pil_img.size != (size, size):
            pil_img = pil_img.resize((size, size), Image.Resampling.LANCZOS)

        with cls._lock:
            cls._pil_cache[cache_key] = pil_img
            return cls._pil_cache[cache_key]

    @classmethod
    def _extract_windows_shell_icon(cls, ext: str, native_size: int = 32) -> Optional[Image.Image]:
        """
        Calls SHGetFileInfoW with SHGFI_USEFILEATTRIBUTES.
        Converts the resulting HICON to an RGBA PIL Image and releases native handles.
        """
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        sfi = SHFILEINFO()
        flags = SHGFI_ICON | SHGFI_LARGEICON | SHGFI_USEFILEATTRIBUTES

        # Use dummy filename so Windows Shell inspects file association without touching disk
        lookup_target = f"dummy{ext}" if ext != ".default" else "dummy"

        res = shell32.SHGetFileInfoW(
            lookup_target,
            FILE_ATTRIBUTE_NORMAL,
            ctypes.byref(sfi),
            ctypes.sizeof(sfi),
            flags,
        )

        if not res or not sfi.hIcon:
            return None

        hicon = sfi.hIcon
        try:
            # Create a 32-bit DIB section to render the icon with alpha channel
            hdc = user32.GetDC(0)
            mem_dc = gdi32.CreateCompatibleDC(hdc)

            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = native_size
            bmi.bmiHeader.biHeight = -native_size  # Top-down DIB
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0  # BI_RGB

            p_bits = ctypes.c_void_p()
            hbmp = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(p_bits), None, 0)
            old_bmp = gdi32.SelectObject(mem_dc, hbmp)

            # Draw the native icon into the DIB section
            user32.DrawIconEx(mem_dc, 0, 0, hicon, native_size, native_size, 0, 0, DI_NORMAL)

            # Copy pixel buffer from unmanaged memory
            raw_bytes = ctypes.string_at(p_bits.value, native_size * native_size * 4)

            # Clean up GDI objects
            gdi32.SelectObject(mem_dc, old_bmp)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(0, hdc)

            # Convert raw BGRA buffer into a PIL RGBA Image
            img = Image.frombuffer("RGBA", (native_size, native_size), raw_bytes, "raw", "BGRA", 0, 1).copy()
            return img

        finally:
            # Ensure the native icon handle is always destroyed to avoid GDI leaks
            user32.DestroyIcon(hicon)

    @classmethod
    def _create_fallback_icon(cls, ext: str, size: int = 32) -> Image.Image:
        """
        Creates an elegant vector document icon fallback when native Shell lookup is unavailable.
        """
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        w, h = int(size * 0.8), int(size * 0.95)
        x0 = (size - w) // 2
        y0 = (size - h) // 2
        x1 = x0 + w
        y1 = y0 + h

        # Document page
        d.rounded_rectangle([x0, y0, x1, y1], radius=3, fill=(248, 250, 252), outline=(203, 213, 225), width=1)
        # Folded top-right corner
        fold = int(w * 0.3)
        d.polygon([(x1 - fold, y0), (x1, y0 + fold), (x1 - fold, y0 + fold)], fill=(226, 232, 240))

        # Document lines
        line_x0 = x0 + int(w * 0.2)
        line_x1 = x1 - int(w * 0.2)
        d.line([(line_x0, y0 + int(h * 0.4)), (line_x1, y0 + int(h * 0.4))], fill=(148, 163, 184), width=2)
        d.line([(line_x0, y0 + int(h * 0.55)), (line_x1, y0 + int(h * 0.55))], fill=(148, 163, 184), width=2)
        d.line([(line_x0, y0 + int(h * 0.7)), (line_x0 + int(w * 0.4), y0 + int(h * 0.7))], fill=(148, 163, 184), width=2)

        return img

    @classmethod
    def preload_common_icons(cls, size: int = 26):
        """Pre-populates the cache with standard Windows file types in the background."""
        common_exts = [
            ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
            ".pdf", ".txt", ".py", ".exe", ".png", ".jpg",
            ".zip", ".mp3", ".mp4", ".default"
        ]
        for ext in common_exts:
            try:
                cls.get_pil_icon(ext, size)
            except Exception:
                pass

    @classmethod
    def clear_cache(cls):
        """Clears cached icon objects."""
        with cls._lock:
            cls._cache.clear()
            cls._pil_cache.clear()

    @classmethod
    def get_cache_size(cls) -> int:
        with cls._lock:
            return len(cls._cache)
