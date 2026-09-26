"""
GPM Login API Client (GPMLogin Global)
Base URL: http://localhost:9495/api/v1

Tài liệu: https://api-docs.gpmloginapp.com/

Cấu trúc phản hồi chung:
    { "success": true, "data": {...}, "message": "OK", "sender": "GPMLogin Global v..." }
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GPM_API_BASE = "http://localhost:9495/api/v1"


class GPMApiError(RuntimeError):
    """Lỗi trả về từ GPM Login API."""


def parse_proxy(proxy_str: str) -> dict:
    """
    Parse chuỗi proxy thành dict để kiểm tra/normalize.

    Hỗ trợ: ip:port | ip:port:user:pass | socks5://... | http://...
    """
    raw = proxy_str.strip()
    scheme = "http"
    if raw.startswith("socks5://"):
        scheme, raw = "socks5", raw[len("socks5://"):]
    elif raw.startswith("socks4://"):
        scheme, raw = "socks4", raw[len("socks4://"):]
    elif raw.startswith("http://"):
        scheme, raw = "http", raw[len("http://"):]
    elif raw.startswith("https://"):
        scheme, raw = "https", raw[len("https://"):]

    # Nếu có dạng user:pass@host:port
    if "@" in raw:
        cred, hostport = raw.split("@", 1)
        user, _, pwd = cred.partition(":")
        host, _, port = hostport.partition(":")
        return {"type": scheme, "host": host, "port": int(port), "user": user, "pass": pwd}

    parts = raw.split(":")
    if len(parts) == 2:
        return {"type": scheme, "host": parts[0], "port": int(parts[1]), "user": None, "pass": None}
    if len(parts) == 4:
        return {"type": scheme, "host": parts[0], "port": int(parts[1]), "user": parts[2], "pass": parts[3]}
    raise ValueError(f"Format proxy không hợp lệ: {proxy_str}")


def to_raw_proxy(proxy_str: str) -> str:
    """
    Chuẩn hoá proxy về chuỗi raw_proxy mà GPM Login chấp nhận.

    GPM hỗ trợ: ip:port, ip:port:user:pass, http://user:pass@ip:port, socks5://ip:port
    """
    raw = proxy_str.strip()
    if not raw:
        return ""

    # Đã có scheme -> giữ nguyên (nhưng chuẩn hoá dạng user:pass@)
    if "://" in raw:
        p = parse_proxy(raw)
        if p["user"]:
            return f"{p['type']}://{p['user']}:{p['pass']}@{p['host']}:{p['port']}"
        return f"{p['type']}://{p['host']}:{p['port']}"

    p = parse_proxy(raw)
    if p["user"]:
        return f"http://{p['user']}:{p['pass']}@{p['host']}:{p['port']}"
    return f"{p['host']}:{p['port']}"


class GPMManager:
    """Client tương tác với GPM Login Local API."""

    def __init__(self, api_base: str = GPM_API_BASE, timeout: float = 60.0):
        self.api_base = api_base.rstrip("/")
        self.client = httpx.Client(base_url=self.api_base, timeout=timeout)
        logger.info(f"GPM Manager khởi tạo: {self.api_base}")

    # ---------- helpers ----------
    def _unwrap(self, resp: httpx.Response) -> dict:
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success", False):
            raise GPMApiError(body.get("message", "unknown error"))
        return body.get("data")

    # ---------- profiles ----------
    def list_profiles(self, page: int = 1, page_size: int = 100, search: str = "", sort: int = 0) -> dict:
        """Trả về object phân trang: {current_page, per_page, total, last_page, data:[...]}."""
        resp = self.client.get("/profiles", params={
            "page": page, "page_size": page_size, "search": search, "sort": sort,
        })
        return self._unwrap(resp) or {}

    def get_profile(self, profile_id: str) -> dict:
        resp = self.client.get(f"/profiles/{profile_id}")
        return self._unwrap(resp)

    def create_profile(
        self,
        name: str,
        raw_proxy: Optional[str] = None,
        group_id: Optional[str] = None,
        startup_urls: Optional[str] = None,
        task_bar_title: Optional[str] = None,
        **extra,
    ) -> dict:
        """
        Tạo profile mới. Chỉ `name` bắt buộc; fingerprint random tự động.

        Returns:
            dict profile đã tạo (có 'id').
        """
        payload: dict = {"name": name}
        if raw_proxy:
            payload["raw_proxy"] = raw_proxy
        if group_id:
            payload["group_id"] = group_id
        if startup_urls:
            payload["startup_urls"] = startup_urls
        if task_bar_title:
            payload["task_bar_title"] = task_bar_title
        payload.update(extra)

        resp = self.client.post("/profiles/create", json=payload)
        data = self._unwrap(resp)
        logger.info(f"Đã tạo profile: {name} (id={data.get('id')})")
        return data

    def update_profile(self, profile_id: str, **fields) -> dict:
        """Cập nhật một phần profile (trường bỏ qua giữ nguyên)."""
        resp = self.client.post(f"/profiles/update/{profile_id}", json=fields)
        return self._unwrap(resp)

    def delete_profile(self, profile_id: str, mode: str = "hard", retries: int = 8) -> bool:
        """
        Xoá profile. mode='soft' -> thùng rác, mode='hard' -> xoá vĩnh viễn cả dữ liệu đĩa.

        Profile vừa stop có thể cần vài giây mới giải phóng; trong lúc đó GPM trả về
        success=false (message kiểu "0/1"). Ta thử lại âm thầm và chỉ cảnh báo khi
        thất bại hoàn toàn (tránh log ồn ào).
        """
        import time as _time
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.client.get(f"/profiles/delete/{profile_id}", params={"mode": mode})
                self._unwrap(resp)
                logger.info(f"Đã xoá profile {profile_id} (mode={mode})")
                return True
            except (httpx.HTTPError, GPMApiError) as e:
                last_err = e
                # profile đang tắt dần -> chờ rồi thử lại (không log từng lần)
                if attempt < retries:
                    _time.sleep(1.0 + 0.5 * attempt)
        logger.warning(f"Không xoá được profile {profile_id} sau {retries} lần: {last_err}")
        return False

    # ---------- browser lifecycle ----------
    def start_browser(
        self,
        profile_id: str,
        window_size: Optional[str] = None,       # "900,1200"
        window_pos: Optional[str] = None,        # "x,y"
        window_scale: Optional[float] = None,    # 0.8
        remote_debugging_port: Optional[int] = None,
        skip_proxy_check: bool = True,
        addition_args: Optional[str] = None,
    ) -> dict:
        """
        Mở trình duyệt của profile.

        Returns data: {
            profile_id, driver_path, remote_debugging_port,
            websocket_debugging_url,
            addition_info: {process_id, profile_name, window_handle, exec_time}
        }
        """
        params: dict = {"skip_proxy_check": str(skip_proxy_check).lower()}
        if window_size:
            params["window_size"] = window_size
        if window_pos:
            params["window_pos"] = window_pos
        if window_scale is not None:
            params["window_scale"] = window_scale
        if remote_debugging_port:
            params["remote_debugging_port"] = remote_debugging_port
        if addition_args:
            params["addition_args"] = addition_args

        resp = self.client.get(f"/profiles/start/{profile_id}", params=params)
        data = self._unwrap(resp)
        logger.info(f"Đã mở browser cho profile {profile_id}")
        return data

    def stop_browser(self, profile_id: str) -> bool:
        """Đóng trình duyệt đang chạy của profile (theo profile_id)."""
        try:
            resp = self.client.get(f"/profiles/stop/{profile_id}")
            self._unwrap(resp)
            return True
        except (httpx.HTTPError, GPMApiError) as e:
            # Browser có thể đã tắt sẵn -> không coi là lỗi nghiêm trọng
            logger.debug(f"Không dừng được browser {profile_id}: {e}")
            return False

    # ---------- proxies ----------
    def create_proxy(self, raw_proxy: str) -> dict:
        resp = self.client.post("/proxies/create", json={"raw_proxy": raw_proxy})
        return self._unwrap(resp)

    def close(self):
        self.client.close()
