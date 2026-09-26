"""
Grid Calculator - Tính toán vị trí cửa sổ dạng lưới
"""

import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_screen_resolution() -> tuple[int, int]:
    """Lấy độ phân giải màn hình chính."""
    try:
        import screeninfo
        monitor = screeninfo.get_monitors()[0]
        return monitor.width, monitor.height
    except Exception:
        # Fallback: dùng ctypes trên Windows
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def calculate_grid(n: int, cols: Optional[int] = None) -> list[dict]:
    """
    Tính toán tọa độ cho n cửa sổ dạng lưới.
    
    Args:
        n: Số lượng luồng/cửa sổ
        cols: Số cột (None = tự động tính gần sqrt(n))
    
    Returns:
        list[dict]: Danh sách [{"x": int, "y": int, "w": int, "h": int}, ...]
    
    Ví dụ: 1920x1080, 4 luồng → 2x2:
        Ô 1: (0, 0, 960, 540)
        Ô 2: (960, 0, 960, 540)
        Ô 3: (0, 540, 960, 540)
        Ô 4: (960, 540, 960, 540)
    """
    if n <= 0:
        return []
    
    sw, sh = get_screen_resolution()
    
    if cols is None:
        cols = int(math.ceil(math.sqrt(n)))
    rows = int(math.ceil(n / cols))
    
    cell_w = sw // cols
    cell_h = sh // rows
    
    grid = []
    for i in range(n):
        row = i // cols
        col = i % cols
        grid.append({
            "x": col * cell_w,
            "y": row * cell_h,
            "w": cell_w,
            "h": cell_h,
        })
    
    logger.info(f"Grid {cols}x{rows} cho {n} cửa sổ trên màn hình {sw}x{sh}")
    return grid


def move_browser_window(pid: int, x: int, y: int, w: int, h: int) -> bool:
    """
    Tìm cửa sổ theo PID và move/resize vào ô lưới.
    
    Args:
        pid: Process ID của browser
        x, y: Tọa độ góc trên bên trái
        w, h: Kích thước cửa sổ
    
    Returns:
        bool: True nếu tìm và di chuyển thành công
    """
    try:
        import win32gui
        import win32process
        
        def callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    win32gui.MoveWindow(hwnd, x, y, w, h, True)
                    extra.append(hwnd)
            return True
        
        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        
        if hwnds:
            logger.info(f"Đã move cửa sổ PID {pid} vào ({x}, {y}) kích thước {w}x{h}")
            return True
        else:
            logger.warning(f"Không tìm thấy cửa sổ với PID {pid}")
            return False
            
    except Exception as e:
        logger.error(f"Lỗi move cửa sổ: {e}")
        return False
