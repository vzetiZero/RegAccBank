"""
Dispatcher - Điều phối đa luồng với ThreadPoolExecutor.
Mỗi luồng: tạo profile -> mở browser (đặt vị trí lưới) -> điền form -> dọn dẹp.
"""

import logging
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from typing import Callable, Optional

from core.gpm_manager import GPMManager, GPMApiError, parse_proxy, to_raw_proxy
from core.grid import calculate_window_grid
from core.automation import RegisterAutomation

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://d3kwdbhwc3ma6l.cloudfront.net/home/register?dl=5amu0u"
DEFAULT_SUCCESS_URL = "https://d3kwdbhwc3ma6l.cloudfront.net/home/mine?dl=5amu0u"
DEFAULT_WITHDRAW_PIN = "201198"
DEFAULT_WITHDRAW_URL = "https://d3kwdbhwc3ma6l.cloudfront.net/home/withdraw?dl=5amu0u&active=10"

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
        success_url: Optional[str] = None,
        withdraw_pin: Optional[str] = None,
        withdraw_url: Optional[str] = None,
        selectors: Optional[dict] = None,
        log_callback: Optional[Callable] = None,
        window_width: int = WINDOW_WIDTH,
        window_height: int = WINDOW_HEIGHT,
        window_scale: float = WINDOW_SCALE,
        grid_cols: Optional[int] = None,
        headless: bool = False,
        progress_callback: Optional[Callable] = None,
    ):
        self.gpm = gpm
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.delete_after = delete_after
        self.url = url
        self.success_url = success_url
        self.withdraw_pin = withdraw_pin
        self.withdraw_url = withdraw_url
        self.selectors = selectors or {}
        self.log_callback = log_callback or self._default_log
        self.window_width = window_width
        self.window_height = window_height
        self.window_scale = window_scale
        self.grid_cols = grid_cols
        self.headless = headless
        self.progress_callback = progress_callback
        self._running = False
        # Cờ tạm dừng: set() = đang chạy, clear() = tạm dừng
        self._pause_event = threading.Event()
        self._pause_event.set()

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
        done = 0

        future_to_job: dict = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for job in jobs:
                future_to_job[executor.submit(self._process_job, job)] = job

            pending = set(future_to_job.keys())
            while pending:
                if not self._running:
                    for f in pending:
                        f.cancel()
                    break

                finished, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in finished:
                    job = future_to_job.pop(future, None)
                    if job is None:
                        continue
                    try:
                        result = future.result()
                        results.append(result)
                        done += 1
                        self._log(f"Xong: {result['account'].get('account')} → {result['status']}")
                        self._emit_progress(done, n, result)
                    except Exception as e:
                        self._log(f"Lỗi xử lý: {e}", "error")
                        if job.get("retry_count", 0) < self.max_retries:
                            job["retry_count"] += 1
                            self._log(f"Thử lại lần {job['retry_count']}...", "warning")
                            nf = executor.submit(self._process_job, job)
                            future_to_job[nf] = job
                            pending.add(nf)
                        else:
                            result = {
                                "account": job["account"], "status": "error",
                                "error": str(e), "timestamp": datetime.now().isoformat(),
                            }
                            results.append(result)
                            done += 1
                            self._emit_progress(done, n, result)

        self._running = False
        self._log(f"Batch hoàn thành: {len(results)} kết quả")
        return results

    # ---------- progress ----------
    def _emit_progress(self, done: int, total: int, result: Optional[dict]):
        """Báo tiến độ về UI (an toàn nếu callback lỗi)."""
        if not self.progress_callback:
            return
        try:
            self.progress_callback(done, total, result)
        except Exception:
            pass

    # ---------- pause / resume ----------
    def pause(self):
        """Tạm dừng: các job đang chạy sẽ dừng sau khi xong việc hiện tại."""
        self._pause_event.clear()
        self._log("Đã tạm dừng — chờ các luồng hoàn tất việc hiện tại", "warning")

    def resume(self):
        self._pause_event.set()
        self._log("Đã tiếp tục chạy", "info")

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    # ---------- single job ----------
    def _process_job(self, job: dict) -> dict:
        # Chặn job mới nếu đang tạm dừng
        self._pause_event.wait()
        acc = job["account"]
        profile_id = job.get("profile_id")
        cell = job.get("grid_cell") or {}

        try:
            # 1. Tạo profile (kèm proxy) nếu chưa có
            if not profile_id:
                raw_proxy = to_raw_proxy(job["proxy"]) if job.get("proxy") else None
                profile = self.gpm.create_profile(
                    name=f"acc_{acc.get('account', 'user')}_{int(time.time())}",
                    raw_proxy=raw_proxy,
                    startup_urls=self.url,
                    task_bar_title=acc.get("name") or acc.get("account", ""),
                )
                profile_id = profile.get("id")
                job["profile_id"] = profile_id
                self._log(f"Đã tạo profile {profile_id} cho {acc.get('account')}")

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
                f"Mở browser {acc.get('account')} tại ({window_pos}) size {window_size} scale {self.window_scale}",
                "info",
            )

            # 3. Kết nối Playwright qua CDP, truy cập URL và chạy luồng đăng ký
            status = self._run_automation(start_info, acc)

            # 4. Dọn dẹp: đóng browser
            self.gpm.stop_browser(profile_id)

            # 5. Xoá profile nếu bật tuỳ chọn
            if self.delete_after:
                self.gpm.delete_profile(profile_id, mode="hard")
                self._log(f"Đã xoá profile {profile_id} (mode=hard)")

            return {
                "account": acc,
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "profile_id": profile_id,
            }

        except (GPMApiError, Exception) as e:
            self._log(f"Lỗi {acc.get('account')}: {e}", "error")
            # Cố gắng dọn dẹp nếu đã tạo profile
            if profile_id and self.delete_after:
                self.gpm.delete_profile(profile_id, mode="hard")
            return {
                "account": acc, "status": "error",
                "error": str(e), "timestamp": datetime.now().isoformat(),
                "profile_id": profile_id,
            }

    def _run_automation(self, start_info: dict, account: dict) -> str:
        """
        Kết nối CDP tới browser của GPM, truy cập URL và chạy luồng đăng ký
        (điền form + submit + chờ kết quả) qua RegisterAutomation.

        Trả về: "success" (có popup thành công), "exists" (tài khoản đã tồn tại)
        hoặc "failed".
        """
        port = start_info.get("remote_debugging_port")
        if not port:
            self._log("Không lấy được remote_debugging_port từ GPM", "error")
            return "failed"

        from playwright.sync_api import sync_playwright

        automation = RegisterAutomation(
            self.selectors, self.url, success_url=self.success_url,
            withdraw_pin=self.withdraw_pin, withdraw_url=self.withdraw_url,
            log=self._log,
        )

        p = sync_playwright().start()
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            automation.navigate(page)
            return automation.run_register(page, account)
        finally:
            try:
                p.stop()
            except Exception:
                pass

    def stop(self):
        self._running = False
        self._pause_event.set()  # giải phóng luồng đang bị tạm dừng
        self._log("Đang dừng tất cả...", "warning")
