"""
Single Profile Tester - Mở 1 profile để test luồng đăng ký.
Giữ browser MỞ sau khi chạy để có thể bắt tiếp xpath / kiểm tra popup.
"""

import logging
import time
from typing import Callable, Optional

from core.gpm_manager import GPMManager, GPMApiError, to_raw_proxy
from core.automation import RegisterAutomation

logger = logging.getLogger(__name__)


class SingleTester:
    """
    Quản lý 1 profile test đang mở.

    Sau khi chạy, browser KHÔNG bị đóng — có thể gọi dump_current() để
    kết nối lại CDP và quét trang (bắt xpath), hoặc close_browser() để đóng.
    """

    def __init__(
        self,
        gpm: GPMManager,
        url: str,
        success_url: Optional[str] = None,
        withdraw_pin: Optional[str] = None,
        withdraw_url: Optional[str] = None,
        selectors: Optional[dict] = None,
        log_callback: Optional[Callable] = None,
        window_width: int = 900,
        window_height: int = 1200,
        window_scale: float = 0.8,
        window_pos: str = "0,0",
    ):
        self.gpm = gpm
        self.url = url
        self.success_url = success_url
        self.withdraw_pin = withdraw_pin
        self.withdraw_url = withdraw_url
        self.selectors = selectors or {}
        self.log = log_callback or (lambda m, level="info": logger.info(m))
        self.window_width = window_width
        self.window_height = window_height
        self.window_scale = window_scale
        self.window_pos = window_pos

        self.profile_id: Optional[str] = None
        self.remote_debugging_port: Optional[int] = None

    # ---------- helpers ----------
    def _connect(self):
        """Mở kết nối Playwright tới browser đang chạy. Trả (playwright, browser)."""
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{self.remote_debugging_port}")
        return p, browser

    # ---------- main test ----------
    def run_test(self, account: dict, proxy: Optional[str] = None) -> bool:
        """
        Tạo profile -> mở browser -> điền form -> Đăng ký -> đóng popup.
        Browser được GIỮ MỞ sau khi hàm kết thúc.
        """
        try:
            # 1. Tạo profile
            raw_proxy = to_raw_proxy(proxy) if proxy else None
            profile = self.gpm.create_profile(
                name=f"test_{account.get('email', 'user')}_{int(time.time())}",
                raw_proxy=raw_proxy,
                startup_urls=self.url,
                task_bar_title=account.get("name") or account.get("email", ""),
            )
            self.profile_id = profile.get("id")
            self.log(f"Đã tạo profile test: {self.profile_id}", "info")

            # 2. Mở browser vào vị trí lưới
            window_size = f"{self.window_width},{self.window_height}"
            info = self.gpm.start_browser(
                self.profile_id,
                window_size=window_size,
                window_pos=self.window_pos,
                window_scale=self.window_scale,
            )
            self.remote_debugging_port = info.get("remote_debugging_port")
            logger.info(f"start info: {info}")
            if not self.remote_debugging_port:
                self.log("Không lấy được remote_debugging_port", "error")
                return False

            # 3. Kết nối Playwright và chạy luồng đăng ký
            automation = RegisterAutomation(
                self.selectors, self.url, success_url=self.success_url,
                withdraw_pin=self.withdraw_pin, withdraw_url=self.withdraw_url,
                log=self.log,
            )
            p, browser = self._connect()
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                automation.navigate(page)
                automation.run_register(page, account)
                # Quét trang lần đầu để bắt popup/xpath
                self.log("—— Quét trang sau khi Đăng ký ——", "info")
                automation.dump(page)
            finally:
                # KHÔNG gọi browser.close() -> giữ browser mở
                try:
                    p.stop()
                except Exception:
                    pass

            self.log(
                f"Browser test vẫn đang MỞ (profile {self.profile_id}, cổng CDP {self.remote_debugging_port}). "
                f"Nhấn 'Quét trang' để bắt xpath hoặc 'Đóng browser test' để kết thúc.",
                "success",
            )
            return True

        except (GPMApiError, Exception) as e:
            self.log(f"Lỗi test profile: {e}", "error")
            return False

    # ---------- rescan ----------
    def dump_current(self) -> bool:
        """Kết nối lại CDP và quét trang hiện tại (bắt xpath popup)."""
        if not self.remote_debugging_port:
            self.log("Chưa có profile test nào đang mở", "warning")
            return False
        try:
            automation = RegisterAutomation(
                self.selectors, self.url, success_url=self.success_url,
                withdraw_pin=self.withdraw_pin, withdraw_url=self.withdraw_url,
                log=self.log,
            )
            p, browser = self._connect()
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.pages[-1] if ctx.pages else ctx.new_page()
                self.log("—— Quét lại trang hiện tại ——", "info")
                automation.dump(page)
                closed = automation.close_popups(page)
                if closed:
                    self.log(f"Đã đóng thêm {closed} popup", "info")
            finally:
                try:
                    p.stop()
                except Exception:
                    pass
            return True
        except Exception as e:
            self.log(f"Lỗi quét trang: {e}", "error")
            return False

    # ---------- close ----------
    def close_browser(self):
        """Đóng browser test và xoá profile (hard)."""
        if not self.profile_id:
            self.log("Không có browser test để đóng", "warning")
            return
        self.gpm.stop_browser(self.profile_id)
        self.gpm.delete_profile(self.profile_id, mode="hard")
        self.log(f"Đã đóng và xoá profile test {self.profile_id}", "success")
        self.profile_id = None
        self.remote_debugging_port = None
