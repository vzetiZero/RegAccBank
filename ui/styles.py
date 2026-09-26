"""
Design System - Theme đen trắng hiện đại
Tập trung màu sắc, font, spacing nhất quán cho toàn bộ ứng dụng.
"""

# ============================================
# MÀU SẮC - Monochrome (đen trắng) + Accent
# ============================================

# Nền (backgrounds) - thang độ xám từ đen
BG_ROOT = "#0A0A0A"        # Nền tổng thể (gần đen tuyệt đối)
BG_SIDEBAR = "#111111"     # Nền sidebar
BG_SURFACE = "#161616"     # Nền surface/panel
BG_CARD = "#1E1E1E"        # Nền card
BG_ELEVATED = "#262626"    # Nền nổi (input, hover)
BG_HOVER = "#2E2E2E"       # Hover state

# Viền (borders)
BORDER = "#2A2A2A"         # Viền thường
BORDER_LIGHT = "#3A3A3A"   # Viền sáng
BORDER_FOCUS = "#FFFFFF"   # Viền khi focus

# Chữ (text)
TEXT_PRIMARY = "#FFFFFF"   # Chữ chính - trắng
TEXT_SECONDARY = "#A3A3A3" # Chữ phụ - xám
TEXT_MUTED = "#6B6B6B"     # Chữ mờ
TEXT_INVERT = "#0A0A0A"    # Chữ trên nền trắng

# Accent - màu nổi bật cho trạng thái
ACCENT_WHITE = "#FFFFFF"   # Accent chính (trắng)
ACCENT_HOVER = "#E5E5E5"   # Hover cho accent trắng
SUCCESS = "#22C55E"        # Xanh lá - thành công
SUCCESS_HOVER = "#16A34A"
DANGER = "#EF4444"         # Đỏ - lỗi/dừng
DANGER_HOVER = "#DC2626"
WARNING = "#F59E0B"        # Vàng cam - cảnh báo
WARNING_HOVER = "#D97706"
INFO = "#3B82F6"           # Xanh dương - thông tin
INFO_HOVER = "#2563EB"

# ============================================
# SPACING - Khoảng cách nhất quán (đơn vị px)
# ============================================
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_2XL = 32

# ============================================
# BORDER RADIUS - Bo góc
# ============================================
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14
RADIUS_XL = 20

# ============================================
# FONT
# ============================================
FONT_FAMILY = "Segoe UI"

FONT_TITLE = (FONT_FAMILY, 22, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 16, "bold")
FONT_HEADING = (FONT_FAMILY, 13, "bold")
FONT_BODY = (FONT_FAMILY, 12)
FONT_SMALL = (FONT_FAMILY, 11)
FONT_TINY = (FONT_FAMILY, 10)
FONT_BUTTON = (FONT_FAMILY, 13, "bold")
FONT_BUTTON_LG = (FONT_FAMILY, 15, "bold")
FONT_MONO = ("Consolas", 11)


def card_style() -> dict:
    """Style chung cho card/panel."""
    return {
        "fg_color": BG_CARD,
        "corner_radius": RADIUS_LG,
        "border_width": 1,
        "border_color": BORDER,
    }


def input_style() -> dict:
    """Style chung cho input/entry."""
    return {
        "fg_color": BG_ELEVATED,
        "border_color": BORDER_LIGHT,
        "border_width": 1,
        "corner_radius": RADIUS_MD,
        "text_color": TEXT_PRIMARY,
        "font": FONT_BODY,
    }


def primary_button_style() -> dict:
    """Nút chính - nền trắng chữ đen (nổi bật)."""
    return {
        "fg_color": ACCENT_WHITE,
        "hover_color": ACCENT_HOVER,
        "text_color": TEXT_INVERT,
        "font": FONT_BUTTON,
        "corner_radius": RADIUS_MD,
        "height": 42,
    }


def secondary_button_style() -> dict:
    """Nút phụ - nền xám chữ trắng."""
    return {
        "fg_color": BG_ELEVATED,
        "hover_color": BG_HOVER,
        "text_color": TEXT_PRIMARY,
        "border_width": 1,
        "border_color": BORDER_LIGHT,
        "font": FONT_BUTTON,
        "corner_radius": RADIUS_MD,
        "height": 42,
    }


def success_button_style() -> dict:
    return {
        "fg_color": SUCCESS,
        "hover_color": SUCCESS_HOVER,
        "text_color": "#FFFFFF",
        "font": FONT_BUTTON_LG,
        "corner_radius": RADIUS_MD,
        "height": 48,
    }


def danger_button_style() -> dict:
    return {
        "fg_color": DANGER,
        "hover_color": DANGER_HOVER,
        "text_color": "#FFFFFF",
        "font": FONT_BUTTON_LG,
        "corner_radius": RADIUS_MD,
        "height": 48,
    }


def warning_button_style() -> dict:
    return {
        "fg_color": WARNING,
        "hover_color": WARNING_HOVER,
        "text_color": "#FFFFFF",
        "font": FONT_BUTTON_LG,
        "corner_radius": RADIUS_MD,
        "height": 48,
    }
