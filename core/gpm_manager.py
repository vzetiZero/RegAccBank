"""
GPM Login API Client
Quản lý profiles thông qua local API server (mặc định: http://localhost:9495)
"""

import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

GPM_API_BASE = "http://localhost:9495"


def parse_proxy(proxy_str: str) -> dict:
    """
    Parse chuỗi proxy thành dict.
    
    Hỗ trợ formats:
        - ip:port (không auth)
        - ip:port:user:pass (có auth)
        - socks5://ip:port:user:pass
    
    Returns:
        dict: {"type": "http"|"socks5", "host": str, "port": int, "user": str|None, "pass": str|None}
    """
    proxy_str = proxy_str.strip()
    proxy_type = "http"
    
    if proxy_str.startswith("socks5://"):
        proxy_type = "socks5"
        proxy_str = proxy_str[9:]
    elif proxy_str.startswith("http://"):
        proxy_str = proxy_str[7:]
    
    parts = proxy_str.split(":")
    
    if len(parts) == 2:
        return {
            "type": proxy_type,
            "host": parts[0],
            "port": int(parts[1]),
            "user": None,
            "pass": None,
        }
    elif len(parts) == 4:
        return {
            "type": proxy_type,
            "host": parts[0],
            "port": int(parts[1]),
            "user": parts[2],
            "pass": parts[3],
        }
    else:
        raise ValueError(f"Format proxy không hợp lệ: {proxy_str}")


class GPMManager:
    """Client để tương tác với GPM Login local API."""
    
    def __init__(self, api_base: str = GPM_API_BASE, timeout: float = 30.0):
        self.api_base = api_base
        self.client = httpx.Client(base_url=api_base, timeout=timeout)
        logger.info(f"GPM Manager khởi tạo với API: {api_base}")
    
    def list_profiles(self, page: int = 1, size: int = 100) -> list[dict]:
        """Liệt kê tất cả profiles."""
        try:
            resp = self.client.get("/api/v3/profiles", params={"page": page, "size": size})
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", data) if isinstance(data, dict) else data
        except httpx.HTTPError as e:
            logger.error(f"Lỗi liệt kê profiles: {e}")
            return []
    
    def get_profile(self, profile_id: int) -> dict:
        """Lấy chi tiết profile."""
        resp = self.client.get(f"/api/v3/profiles/{profile_id}")
        resp.raise_for_status()
        return resp.json()
    
    def create_profile(
        self,
        name: str,
        proxy: Optional[dict] = None,
        group_id: str = "default",
        **kwargs
    ) -> dict:
        """
        Tạo profile mới.
        
        Args:
            name: Tên profile
            proxy: Dict proxy từ parse_proxy()
            group_id: ID của group
            **kwargs: Các tùy chọn khác (fingerprint, UA...)
        
        Returns:
            dict: Thông tin profile đã tạo (bao gồm id)
        """
        payload = {
            "name": name,
            "group_id": group_id,
        }
        if proxy:
            payload["proxy"] = proxy
        payload.update(kwargs)
        
        resp = self.client.post("/api/v3/profiles/create", json=payload)
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"Đã tạo profile: {name} (ID: {result.get('id')})")
        return result
    
    def update_profile(self, profile_id: int, **kwargs) -> dict:
        """Cập nhật profile (proxy, UA, fingerprint...)."""
        resp = self.client.put(f"/api/v3/profiles/{profile_id}", json=kwargs)
        resp.raise_for_status()
        return resp.json()
    
    def delete_profile(self, profile_id: int) -> bool:
        """
        Xóa profile khỏi GPM Login và ổ cứng.
        
        Args:
            profile_id: ID của profile cần xóa
        
        Returns:
            bool: True nếu xóa thành công
        """
        try:
            resp = self.client.delete(f"/api/v3/profiles/{profile_id}")
            resp.raise_for_status()
            logger.info(f"Đã xóa profile ID: {profile_id}")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Lỗi xóa profile {profile_id}: {e}")
            return False
    
    def start_browser(self, profile_id: int, headless: bool = False) -> dict:
        """
        Khởi động browser với profile.
        
        Args:
            profile_id: ID của profile
            headless: Chế độ ẩn
        
        Returns:
            dict: {browser_id, pid, cdp_port, ...}
        """
        resp = self.client.post(
            "/api/v3/profiles/start",
            params={"profile_id": profile_id, "headless": str(headless).lower()},
            timeout=60.0
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"Đã khởi động browser cho profile {profile_id}")
        return result
    
    def stop_browser(self, browser_id: int) -> bool:
        """Dừng browser."""
        try:
            resp = self.client.post(f"/api/v3/browser/{browser_id}/stop")
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Lỗi dừng browser {browser_id}: {e}")
            return False
    
    def get_browser_status(self, browser_id: int) -> dict:
        """Lấy trạng thái browser."""
        resp = self.client.get(f"/api/v3/browser/{browser_id}/status")
        resp.raise_for_status()
        return resp.json()
    
    def close(self):
        """Đóng HTTP client."""
        self.client.close()
