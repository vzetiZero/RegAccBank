"""
Grid Calculator - Tính toán vị trí cửa sổ dạng lưới cách đều.

Cửa sổ được đặt vị trí bằng API GPM (window_pos="x,y") nên không cần
thao tác Windows API. Kích thước thực tế trên màn hình = kích thước * scale.
"""

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


def get_screen_resolution() -> tuple[int, int]:
    """Lấy độ phân giải màn hình chính."""
    try:
        import screeninfo
        monitor = screeninfo.get_monitors()[0]
        return monitor.width, monitor.height
    except Exception:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except Exception:
            return 1920, 1080


def calculate_window_grid(
    n: int,
    win_w: int = 900,
    win_h: int = 1200,
    scale: float = 0.8,
    cols: Optional[int] = None,
) -> list[dict]:
    """
    Tính vị trí xếp lưới cách đều cho n cửa sổ.

    Args:
        n: Số luồng/cửa sổ.
        win_w, win_h: Kích thước cửa sổ (chưa nhân scale).
        scale: Tỉ lệ hiển thị (API window_scale).
        cols: Số cột cố định; None = tự động theo số luồng.

    Returns:
        list[dict]: [{"x", "y", "w", "h"}, ...]
                    x,y là toạ độ đặt cửa sổ; w,h là kích thước gốc (window_size).
    """
    if n <= 0:
        return []

    sw, sh = get_screen_resolution()

    # Kích thước hiển thị thực tế để xếp lưới không chồng lấn
    eff_w = max(1, int(round(win_w * scale)))
    eff_h = max(1, int(round(win_h * scale)))

    # Số cột: tự động = căn bậc hai, giới hạn theo bề rộng màn hình
    if cols is None or cols <= 0:
        cols = int(math.ceil(math.sqrt(n)))
    max_cols = max(1, sw // eff_w)
    cols = max(1, min(cols, max_cols))
    rows = int(math.ceil(n / cols))

    grid = []
    for i in range(n):
        r = i // cols
        c = i % cols
        grid.append({
            "x": c * eff_w,
            "y": r * eff_h,
            "w": win_w,
            "h": win_h,
        })

    logger.info(
        f"Grid {cols}x{rows} cho {n} cửa sổ | ô {eff_w}x{eff_h} (scale {scale}) | màn hình {sw}x{sh}"
    )
    return grid


def calculate_grid(n: int, cols: Optional[int] = None) -> list[dict]:
    """Tương thích ngược: chia đều màn hình cho n cửa sổ."""
    if n <= 0:
        return []
    sw, sh = get_screen_resolution()
    if cols is None or cols <= 0:
        cols = int(math.ceil(math.sqrt(n)))
    rows = int(math.ceil(n / cols))
    cell_w, cell_h = sw // cols, sh // rows
    return [
        {"x": (i % cols) * cell_w, "y": (i // cols) * cell_h, "w": cell_w, "h": cell_h}
        for i in range(n)
    ]
