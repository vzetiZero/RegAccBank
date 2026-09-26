"""
Dispatcher - Điều phối đa luồng với ThreadPoolExecutor.
Mỗi luồng: tạo profile -> mở browser (đặt vị trí lưới) -> điền form -> dọn dẹp.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Optional

from core.gpm_manager import GPMManager, GPMApiError, parse_proxy, to_raw_proxy
from core.grid import calculate_window_grid
from core.automation import RegisterAutomation

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://d3kwdbhwc3ma6l.cloudfront.net/home/register?dl=5amu0u"

# Kích thước cửa sổ mặc định theo yêu cầu
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 1200
WINDOW_SCALE = 0.8


class Dispatcher:
    """Điều phối các luồng automation."""

    def __init__(
        self,
        gpm: GPMManager,
        max_workers: int = 3,
        max_retries: int = 2,
        delete_after: bool = False,
        url: str = DEFAULT_URL,
        selectors: Optional[dict] = None,
        log_callback: Optional[Callable] = None,
        window_width: int = WINDOW_WIDTH,
        window_height: int = WINDOW_HEIGHT,
        window_scale: float = WINDOW_SCALE,
        grid_cols: Optional[int] = None,
        headless: bool = False,
    ):
        self.gpm = gpm
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.delete_after = delete_after
        self.url = url
        self.selectors = selectors or {}
        self.log_callback = log_callback or self._default_log
        self.window_width = window_width
        self.window_height = window_height
        self.window_scale = window_scale
        self.grid_cols = grid_cols
        self.headless = headless
        self._running = False

    # ---------- logging ----------
    def _default_log(self, message: str, level: str = "info"):
        getattr(logger, level if level in ("info", "warning", "error") else "info")(message)

    def _log(self, message: str, level: str = "info"):
        self.log_callback(message, level)

    # ---------- batch ----------
    def run_batch(self, accounts: list[dict], proxies: list[str]) -> list[dict]:
        n = len(accounts)
        self._running = True
        self._log(f"Bắt đầu batch: {n} tài khoản · {self.max_workers} luồng")

        # Tính lưới vị trí cửa sổ
        grid = calculate_window_grid(
            n,
            win_w=self.window_width,
            win_h=self.window_height,
            scale=self.window_scale,
            cols=self.grid_cols,
        )

        jobs = []
        for i, acc in enumerate(accounts):
            proxy = proxies[i] if i < len(proxies) else (proxies[0] if proxies else None)
            jobs.append({
                "account": acc,
                "proxy": proxy,
                "grid_cell": grid[i] if i < len(grid) else None,
                "retry_count": 0,
                "profile_id": None,
            })

        results: list[dict] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_job = {}
            for job in jobs:
                future_to_job[executor.submit(self._process_job, job)] = job

            for future in as_completed(future_to_job):
                if not self._running:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                job = future_to_job[future]
                try:
                    result = future.result()
                    results.append(result)
                    self._log(f"Xong: {result['account'].get('email')} → {result['status']}")
                except Exception as e:
                    self._log(f"Lỗi xử lý: {e}", "error")
                    if job.get("retry_count", 0) < self.max_retries:
                        job["retry_count"] += 1
                        self._log(f"Thử lại lần {job['retry_count']}...", "warning")
                        future_to_job[executor.submit(self._process_job, job)] = job
                    else:
                        results.append({
                            "account": job["account"], "status": "error",
                            "error": str(e), "timestamp": datetime.now().isoformat(),
                        })

        self._running = False
        self._log(f"Batch hoàn thành: {len(results)} kết quả")
        return results

    # ---------- single job ----------
    def _process_job(self, job: dict) -> dict:
        acc = job["account"]
        profile_id = job.get("profile_id")
        cell = job.get("grid_cell") or {}

        try:
            # 1. Tạo profile (kèm proxy) nếu chưa có
            if not profile_id:
                raw_proxy = to_raw_proxy(job["proxy"]) if job.get("proxy") else None
                profile = self.gpm.create_profile(
                    name=f"acc_{acc.get('email', 'user')}_{int(time.time())}",
                    raw_proxy=raw_proxy,
                    startup_urls=self.url,
                    task_bar_title=acc.get("name") or acc.get("email", ""),
                )
                profile_id = profile.get("id")
                job["profile_id"] = profile_id
                self._log(f"Đã tạo profile {profile_id} cho {acc.get('email')}")

            # 2. Mở browser và đặt vào ô lưới
            window_size = f"{self.window_width},{self.window_height}"
            window_pos = f"{cell.get('x', 0)},{cell.get('y', 0)}"
            start_info = self.gpm.start_browser(
                profile_id,
                window_size=window_size,
                window_pos=window_pos,
                window_scale=self.window_scale,
            )

            self._log(
                f"Mở browser {acc.get('email')} tại ({window_pos}) size {window_size} scale {self.window_scale}",
                "info",
            )

            # 3. Kết nối Playwright qua CDP, truy cập URL và điền form (nếu có selectors)
            success = self._run_automation(start_info, acc)

            # 4. Dọn dẹp: đóng browser
            self.gpm.stop_browser(profile_id)

            # 5. Xoá profile nếu bật tuỳ chọn
            if self.delete_after:
                self.gpm.delete_profile(profile_id, mode="hard")
                self._log(f"Đã xoá profile {profile_id} (mode=hard)")

            return {
                "account": acc,
                "status": "success" if success else "failed",
                "timestamp": datetime.now().isoformat(),
                "profile_id": profile_id,
            }

        except (GPMApiError, Exception) as e:
            self._log(f"Lỗi {acc.get('email')}: {e}", "error")
            # Cố gắng dọn dẹp nếu đã tạo profile
            if profile_id and self.delete_after:
                self.gpm.delete_profile(profile_id, mode="hard")
            return {
                "account": acc, "status": "error",
                "error": str(e), "timestamp": datetime.now().isoformat(),
                "profile_id": profile_id,
            }

    def _run_automation(self, start_info: dict, account: dict) -> bool:
        """
        Kết nối CDP tới browser của GPM, truy cập URL và chạy luồng đăng ký
        (điền form + submit + đóng popup) qua RegisterAutomation.

        Trả về True nếu phát hiện chỉ báo thành công (hoặc đã submit xong).
        """
        port = start_info.get("remote_debugging_port")
        if not port:
            self._log("Không lấy được remote_debugging_port từ GPM", "error")
            return False

        from playwright.sync_api import sync_playwright

        automation = RegisterAutomation(self.selectors, self.url, log=self._log)

        p = sync_playwright().start()
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            automation.navigate(page)
            automation.run_register(page, account)

            # Kiểm tra chỉ báo thành công (nếu có cấu hình)
            success = True
            sel_ok = (self.selectors or {}).get("success_indicator")
            if sel_ok:
                try:
                    page.wait_for_selector(sel_ok, timeout=5000)
                    success = True
                except Exception:
                    success = False
            return success
        finally:
            try:
                p.stop()
            except Exception:
                pass

    def stop(self):
        self._running = False
        self._log("Đang dừng tất cả...", "warning")
