"""
Human-like Interaction - Mô phỏng hành vi người dùng thật
"""

import random
import time
import logging

logger = logging.getLogger(__name__)


def human_delay(min_ms: int = 50, max_ms: int = 150):
    """Random delay giữa các ký tự nhập."""
    delay = random.uniform(min_ms, max_ms) / 1000
    time.sleep(delay)


def type_like_human(page, selector: str, text: str):
    """
    Nhập text với tốc độ ngẫu nhiên như người thật.
    
    Args:
        page: Playwright page object
        selector: CSS selector của input
        text: Nội dung cần nhập
    """
    page.click(selector)
    for char in text:
        page.keyboard.type(char)
        human_delay()
    # Pause trước khi chuyển field
    time.sleep(random.uniform(0.3, 0.8))


def random_pause_before_submit():
    """Khoảng dừng ngẫu nhiên trước khi bấm nút submit."""
    delay = random.uniform(1.0, 3.5)
    logger.info(f"Delay {delay:.1f}s trước khi submit")
    time.sleep(delay)


def random_scroll(page):
    """Scroll ngẫu nhiên để mô phỏng hành vi thật."""
    scroll_amount = random.randint(100, 500)
    page.mouse.wheel(0, scroll_amount)
    time.sleep(random.uniform(0.5, 1.5))
