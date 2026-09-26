"""
Dispatcher - Điều phối đa luồng với ThreadPoolExecutor
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Optional

from core.gpm_manager import GPMManager, parse_proxy
from core.grid import calculate_grid, move_browser_window
from core.human import type_like_human, random_pause_before_submit

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://d3kwdbhwc3ma6l.cloudfront.net/home/register?dl=5amu0u"


class Dispatcher:
    """Điều phối các luồng automation."""
    
    def __init__(
        self,
        gpm: GPMManager,
        max_workers: int = 5,
        max_retries: int = 3,
        delete_after: bool = False,
        url: str = DEFAULT_URL,
        selectors: Optional[dict] = None,
        log_callback: Optional[Callable] = None,
    ):
        self.gpm = gpm
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.delete_after = delete_after
        self.url = url
        self.selectors = selectors or {}
        self.log_callback = log_callback or self._default_log
        self._running = False
    
    def _default_log(self, message: str, level: str = "info"):
        """Ghi log mặc định."""
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)
    
    def _log(self, message: str, level: str = "info"):
        """Ghi log qua callback."""
        self.log_callback(message, level)
    
    def run_batch(self, accounts: list[dict], proxies: list[str]):
        """
        Chạy batch các accounts với đa luồng.
        
        Args:
            accounts: Danh sách [{"name": "...", "email": "...", "password": "..."}, ...]
            proxies: Danh sách proxy strings
        
        Returns:
            list[dict]: Kết quả cho mỗi account
        """
        n = len(accounts)
        self._running = True
        
        self._log(f"Bắt đầu batch: {n} accounts, {self.max_workers} workers")
        
        # Tính grid positions
        grid = calculate_grid(n)
        
        # Tạo jobs
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
        
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_job = {}
            
            for job in jobs:
                future = executor.submit(self._process_job, job)
                future_to_job[future] = job
            
            for future in as_completed(future_to_job):
                if not self._running:
                    executor.shutdown(wait=False)
                    break
                
                job = future_to_job[future]
                try:
                    result = future.result()
                    results.append(result)
                    self._log(f"Hoàn thành: {result['account']['email']} -> {result['status']}")
                except Exception as e:
                    self._log(f"Lỗi: {e}", "error")
                    if job.get("retry_count", 0) < self.max_retries:
                        job["retry_count"] += 1
                        self._log(f"Retry lần {job['retry_count']}...", "warning")
                        future = executor.submit(self._process_job, job)
                        future_to_job[future] = job
                    else:
                        results.append({
                            "account": job["account"],
                            "status": "failed",
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                        })
        
        self._running = False
        self._log(f"Batch hoàn thành: {len(results)} kết quả")
        return results
    
    def _process_job(self, job: dict) -> dict:
        """Xử lý 1 job: tạo/mở profile → navigate → fill form → submit → dọn dẹp."""
        acc = job["account"]
        profile_id = job.get("profile_id")
        
        try:
            # 1. Tạo profile mới hoặc dùng profile có sẵn
            if not profile_id:
                proxy_info = parse_proxy(job["proxy"]) if job["proxy"] else None
                profile = self.gpm.create_profile(
                    name=f"auto_{acc['email'].split('@')[0]}_{int(time.time())}",
                    proxy=proxy_info
                )
                profile_id = profile.get("id")
                job["profile_id"] = profile_id
            
            # 2. Khởi động browser
            browser_info = self.gpm.start_browser(profile_id, headless=False)
            
            # 3. Move window vào grid
            if job.get("grid_cell") and not job.get("headless"):
                move_browser_window(browser_info.get("pid"), **job["grid_cell"])
            
            # 4. Kết nối CDP và fill form
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(
                    f"http://localhost:{browser_info.get('cdp_port', 9222)}"
                )
                page = browser.contexts[0].new_page()
                page.goto(self.url, wait_until="networkidle")
                
                # Fill form
                if self.selectors:
                    type_like_human(page, self.selectors["name"], acc["name"])
                    type_like_human(page, self.selectors["email"], acc["email"])
                    type_like_human(page, self.selectors["password"], acc["password"])
                    
                    random_pause_before_submit()
                    page.click(self.selectors["submit"])
                
                # Kiểm tra kết quả
                time.sleep(3)
                success = False
                if self.selectors.get("success_indicator"):
                    success = page.locator(self.selectors["success_indicator"]).count() > 0
                
                page.close()
            
            # 5. Dọn dẹp: stop browser
            self.gpm.stop_browser(browser_info.get("id"))
            
            # 6. Xóa profile nếu được yêu cầu
            if self.delete_after:
                self.gpm.delete_profile(profile_id)
                self._log(f"Đã xóa profile {profile_id}")
            
            return {
                "account": acc,
                "status": "success" if success else "failed",
                "timestamp": datetime.now().isoformat(),
                "profile_id": profile_id,
            }
            
        except Exception as e:
            self._log(f"Lỗi xử lý {acc['email']}: {e}", "error")
            return {
                "account": acc,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    def stop(self):
        """Dừng tất cả các luồng."""
        self._running = False
        self._log("Đang dừng tất cả...", "warning")
