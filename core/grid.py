"""
Grid Calculator - Tính toán vị trí cửa sổ dạng lưới cách đều.

Cửa sổ được đặt vị trí bằng API GPM (window_pos="x,y", window_size="w,h").
Mỗi cửa sổ được cấp 1 "ô" (cell) trên màn hình; kích thước cửa sổ luôn
<= kích thước ô (trừ khe hở) nên các cửa sổ KHÔNG đè lên nhau.
"""

import ctypes
import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

GAP = 8            # khe hở giữa các cửa sổ (px)
MIN_COL_W = 300    # bề rộng ô tối thiểu để còn dùng được


def get_screen_resolution() -> tuple[int, int]:
    """Lấy độ phân giải màn hình chính."""
    try:
        import screeninfo
        monitor = screeninfo.get_monitors()[0]
        return monitor.width, monitor.height
    except Exception:
        try:
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except Exception:
            return 1920, 1080


def get_work_area() -> tuple[int, int, int, int]:
    """
    Trả về (x, y, w, h) vùng desktop dùng được (đã trừ taskbar).

    Dùng SPI_GETWORKAREA trên Windows; fallback về độ phân giải màn hình.
    """
    try:
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        SPI_GETWORKAREA = 0x0030
        rect = RECT()
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
        )
        if ok:
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 0 and h > 0:
                return rect.left, rect.top, w, h
    except Exception:
        pass

    sw, sh = get_screen_resolution()
    return 0, 0, sw, max(1, sh - 48)


def calculate_window_grid(
    n: int,
    win_w: int = 900,
    win_h: int = 1200,
    scale: float = 1.0,
    cols: Optional[int] = None,
    gap: int = GAP,
) -> list[dict]:
    """
    Tính vị trí + kích thước cho n cửa sổ xếp lưới cách đều, không đè nhau.

    Args:
        n: Số cửa sổ chạy ĐỒNG THỜI (số luồng), không phải tổng tài khoản.
        win_w, win_h: Kích thước cửa sổ MONG MUỐN (sẽ được thu nhỏ nếu ô nhỏ hơn).
        cols: Số cột cố định; None = tự động (căn bậc hai).
        gap: Khe hở giữa các cửa sổ.

    Returns:
        list[dict]: [{"x", "y", "w", "h"}, ...]
                    x,y: toạ độ đặt cửa sổ;  w,h: kích thước để đặt (window_size).
    """
    if n <= 0:
        return []

    ax, ay, sw, sh = get_work_area()

    # Số cột: tự động = căn bậc hai, giới hạn theo bề rộng màn hình
    if cols is None or cols <= 0:
        cols = int(math.ceil(math.sqrt(n)))
    cols = max(1, min(cols, n))
    max_cols = max(1, sw // MIN_COL_W)
    cols = min(cols, max_cols)
    rows = int(math.ceil(n / cols))

    # Nếu ô quá thấp mà vẫn còn chỗ tăng cột -> tăng cột để ô cao hơn
    while rows > 1 and (sh // rows) < 200 and cols < max_cols and cols < n:
        cols += 1
        rows = int(math.ceil(n / cols))

    cell_w = sw // cols
    cell_h = sh // rows

    # Kích thước cửa sổ: không vượt quá ô (trừ khe hở)
    avail_w = max(1, cell_w - gap)
    avail_h = max(1, cell_h - gap)
    size_w = max(1, min(int(win_w), avail_w))
    size_h = max(1, min(int(win_h), avail_h))

    # Canh giữa cửa sổ trong ô
    off_x = max(0, (cell_w - size_w) // 2)
    off_y = max(0, (cell_h - size_h) // 2)

    grid = []
    for i in range(n):
        r = i // cols
        c = i % cols
        grid.append({
            "x": ax + c * cell_w + off_x,
            "y": ay + r * cell_h + off_y,
            "w": size_w,
            "h": size_h,
        })

    logger.info(
        f"Grid {cols}x{rows} cho {n} cửa sổ | ô {cell_w}x{cell_h} | "
        f"cửa sổ {size_w}x{size_h} | vùng {sw}x{sh} tại ({ax},{ay})"
    )
    return grid


def calculate_grid(n: int, cols: Optional[int] = None) -> list[dict]:
    """Tương thích ngược: chia đều màn hình cho n cửa sổ."""
    return calculate_window_grid(n, win_w=10**6, win_h=10**6, cols=cols)
