# Kế hoạch xây dựng Hệ thống Tự động hóa Đăng ký Đa luồng (RegAcc)

> **Repo:** https://github.com/vzetiZero/RegAccBank  
> **Browser Engine:** GPM Login (Antidetect) — API local `http://localhost:9495`  
> **API Docs:** https://api-docs.gpmloginapp.com/

---

## 1. Kiến trúc hệ thống & Lựa chọn công nghệ

| Thành phần | Công nghệ | Lý do lựa chọn |
|---|---|---|
| **Giao diện (UI)** | CustomTkinter | Hiện đại, hỗ trợ Dark/Light mode, tích hợp đa luồng mượt, dễ đóng gói `.exe` |
| **Lõi Automation** | Python + GPM Login API | GPM Login cung cấp sẵn antidetect fingerprint, quản lý profile, hỗ trợ proxy. Không cần tự fake |
| **Xử lý Đa luồng** | `concurrent.futures.ThreadPoolExecutor` | Điều phối số lượng profile chạy đồng thời mà không làm đơ GUI |
| **Quản lý Cửa sổ** | `pygetwindow` + `pywin32` | Đo độ phân giải màn hình, tính toán tọa độ grid $(x, y, w, h)$ |
| **Định danh / Profile** | GPM Login Profile API | Tách biệt hoàn toàn cache, cookies, fingerprint cho từng profile |
| **Đọc dữ liệu** | `pandas` + `openpyxl` | Đọc CSV/Excel chứa danh sách tài khoản |
| **HTTP Client** | `httpx` hoặc `requests` | Gọi REST API của GPM Login |

---

## 2. Thiết kế Module & Luồng vận hành (Workflow)

```
┌─────────────────────────────────────────────────────────────┐
│                    Giao diện Dashboard (CTk)                 │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Tab 1:      │  │ Tab 2:       │  │ Tab 3:            │  │
│  │ Bảng điều   │  │ Trực quan    │  │ Cấu hình nâng cao │  │
│  │ khiển       │  │ hóa & Giám   │  │ (Selectors,       │  │
│  │             │  │ sát          │  │  Captcha, OTP)    │  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
│         │                                                   │
│         ▼  (Gửi lệnh qua ThreadPoolExecutor)                │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Bộ điều phối luồng (Dispatcher)                │
│  • Phân bồ: Account[i] + Proxy[i] + Profile[i]             │
│  • Tính toán vị trí hiển thị dạng lưới (Grid Calculator)    │
│  • Gọi GPM Login API để mở profile                          │
│  • Gán proxy vào profile (nếu profile chưa có sẵn proxy)     │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Browser Automation Worker (Thread)              │
│  • Khởi động GPM Login với profile_id                        │
│  • Chờ browser sẵn sàng → Resize & Move vào ô lưới           │
│  • Truy cập Link → Nhập form → Click Submit                  │
│  • Ghi nhận kết quả → Gửi Log về UI                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.1. Luồng giao tiếp với GPM Login API

```
┌──────────┐    POST /api/v1/profiles/create    ┌──────────────┐
│  App     │ ──────────────────────────────────▶ │  GPM Login   │
│ (Python) │                                     │  Local API   │
│          │    POST /api/v1/profiles/start     │  :9495       │
│          │ ──────────────────────────────────▶ │              │
│          │                                     │              │
│          │    GET  /api/v1/browser/{id}/stop  │              │
│          │ ──────────────────────────────────▶ │              │
└──────────┘                                     └──────────────┘
```

**Endpoints chính (dựa trên tài liệu GPM Login API):**

| Method | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/api/v1/profiles` | Tạo profile mới |
| `GET` | `/api/v1/profiles` | Liệt kê tất cả profiles |
| `GET` | `/api/v1/profiles/{id}` | Lấy chi tiết profile |
| `PUT` | `/api/v1/profiles/{id}` | Cập nhật profile (proxy, UA...) |
| `DELETE` | `/api/v1/profiles/{id}` | Xóa profile |
| `POST` | `/api/v1/profiles/start` | Khởi động browser với profile |
| `POST` | `/api/v1/browser/{browser_id}/stop` | Dừng browser |
| `GET` | `/api/v1/browser/{browser_id}/status` | Trạng thái browser |

> ⚠️ **Lưu ý:** Endpoint có thể khác nhau tùy phiên bản GPM Login. Cần kiểm tra lại https://api-docs.gpmloginapp.com/ khi triển khai.

---

## 3. Kế hoạch triển khai kỹ thuật chi tiết

### Bước 1: Xây dựng thuật toán xếp lưới cửa sổ (Window Grid)

**File:** `core/grid.py`

```python
import screeninfo  # hoặc ctypes.windll.user32

def get_screen_resolution() -> tuple[int, int]:
    """Lấy độ phân giải màn hình chính."""
    monitor = screeninfo.get_monitors()[0]
    return monitor.width, monitor.height

def calculate_grid(n: int, cols: int | None = None) -> list[dict]:
    """
    Tính toán tọa độ cho n cửa sổ.
    
    Args:
        n: Số lượng luồng/cửa sổ
        cols: Số cột (None = tự động tính gần sqrt(n))
    
    Returns:
        Danh sách dict: [{"x": int, "y": int, "w": int, "h": int}, ...]
    
    Ví dụ: 1920x1080, 4 luồng → 2x2:
        Ô 1: (0, 0, 960, 540)
        Ô 2: (960, 0, 960, 540)
        Ô 3: (0, 540, 960, 540)
        Ô 4: (960, 540, 960, 540)
    """
    sw, sh = get_screen_resolution()
    if cols is None:
        cols = int(math.ceil(math.sqrt(n)))
    rows = int(math.ceil(n / cols))
    
    cell_w = sw // cols
    cell_h = sh // rows
    
    grid = []
    for i in range(n):
        row = i // cols
        col = i % cols
        grid.append({
            "x": col * cell_w,
            "y": row * cell_h,
            "w": cell_w,
            "h": cell_h,
        })
    return grid
```

**Lưu ý:** Khi GPM Login mở browser, nó tự điều khiển `--window-position` và `--window-size`. Ta chỉ cần resize/move cửa sổ sau khi browser đã mở:

```python
import win32gui
import win32con

def move_browser_window(pid: int, x: int, y: int, w: int, h: int):
    """Tìm cửa sổ theo PID và move/resize vào ô lưới."""
    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == pid:
                win32gui.MoveWindow(hwnd, x, y, w, h, True)
                extra.append(hwnd)
        return True
    
    hwnds = []
    win32gui.EnumWindows(callback, hwnds)
```

---

### Bước 2: Cơ chế gán Proxy & Fingerprint qua GPM Login

**File:** `core/gpm_manager.py`

```python
import httpx
from typing import Optional

GPM_API_BASE = "http://localhost:9495"

class GPMManager:
    def __init__(self, api_base: str = GPM_API_BASE):
        self.client = httpx.Client(base_url=api_base, timeout=30.0)
    
    def create_profile(
        self,
        name: str,
        proxy: Optional[dict] = None,
        **kwargs
    ) -> dict:
        """
        Tạo profile mới trong GPM Login.
        
        Proxy format: {"type": "http|socks5", "host": "...", "port": 8080, "user": "...", "pass": "..."}
        """
        payload = {
            "name": name,
            "group_id": kwargs.get("group_id", "default"),
            "proxy": proxy,
            # Các fingerprint options khác...
        }
        resp = self.client.post("/api/v1/profiles", json=payload)
        return resp.json()
    
    def start_browser(self, profile_id: int, headless: bool = False) -> dict:
        """Khởi động browser với profile_id. Trả về thông tin browser (cdp_pid, ...)."""
        resp = self.client.post(
            f"/api/v1/profiles/{profile_id}/start",
            params={"headless": str(headless).lower()}
        )
        return resp.json()
    
    def stop_browser(self, browser_id: int):
        """Dừng browser."""
        self.client.post(f"/api/v1/browser/{browser_id}/stop")
    
    def update_proxy(self, profile_id: int, proxy: dict):
        """Cập nhật proxy cho profile (chưa apply vào browser đang chạy)."""
        self.client.put(f"/api/v1/profiles/{profile_id}", json={"proxy": proxy})
    
    def list_profiles(self) -> list[dict]:
        resp = self.client.get("/api/v1/profiles")
        return resp.json()
```

**Format proxy input (UI nhập):**
- `ip:port` → không auth
- `ip:port:user:pass` → có auth

**Parse proxy:**
```python
def parse_proxy(proxy_str: str) -> dict:
    """Parse 'ip:port' hoặc 'ip:port:user:pass' thành dict."""
    parts = proxy_str.strip().split(":")
    proxy_type = "http"  # hoặc socks5 nếu prefix socks5://
    
    if proxy_str.startswith("socks5://"):
        proxy_type = "socks5"
        parts = proxy_str[9:].split(":")
    
    if len(parts) == 2:
        return {"type": proxy_type, "host": parts[0], "port": int(parts[1])}
    elif len(parts) == 4:
        return {
            "type": proxy_type,
            "host": parts[0],
            "port": int(parts[1]),
            "user": parts[2],
            "pass": parts[3],
        }
    raise ValueError(f"Proxy format không hợp lệ: {proxy_str}")
```

---

### Bước 3: Đảm bảo độ trễ tự nhiên (Human-like Interaction)

**File:** `core/human.py`

```python
import random
import time

def human_delay(min_ms: int = 50, max_ms: int = 150):
    """Random delay giữa các ký tự nhập."""
    time.sleep(random.uniform(min_ms, max_ms) / 1000)

def type_like_human(page, selector: str, text: str):
    """Nhập text với tốc độ ngẫu nhiên."""
    page.click(selector)
    for char in text:
        page.type(selector, char, delay=0)
        human_delay()
    # Pause trước khi chuyển field
    time.sleep(random.uniform(0.3, 0.8))

def random_pause_before_submit():
    """Khoảng dừng ngẫu nhiên trước khi bấm nút."""
    time.sleep(random.uniform(1.0, 3.5))
```

**Lưu ý quan trọng:** GPM Login sử dụng Chromium/Chrome nên có thể tương tác qua CDP (Chrome DevTools Protocol). Nếu cần tương tác sâu (nhập form, click), có thể dùng `playwright` kết nối qua CDP:

```python
from playwright.sync_api import sync_playwright

def connect_to_gpm_browser(cdp_url: str):
    """Kết nối Playwright vào browser đang chạy của GPM Login."""
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        return browser
```

---

### Bước 4: Thiết kế giao diện UI (CustomTkinter)

**File:** `ui/dashboard.py`

```python
import customtkinter as ctk

class Dashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.title("RegAcc - Hệ thống tự động hóa đăng ký")
        self.geometry("1200x800")
        
        self._build_tabview()
        self._build_dashboard_tab()
        self._build_monitor_tab()
        self._build_advanced_tab()
    
    def _build_tabview(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        self.tabview.add("Bảng điều khiển")
        self.tabview.add("Trực quan hóa & Giám sát")
        self.tabview.add("Cấu hình nâng cao")
```

#### Tab 1: Bảng điều khiển (Dashboard)

| Thành phần | Widget | Mô tả |
|---|---|---|
| **Input Link** | `CTkEntry` | Nhập URL đích cần đăng ký |
| **Data Source** | `CTkButton` + File Dialog | Chọn file `.csv`, `.xlsx`, `.txt` |
| **Proxy Manager** | `CTkTextbox` + `CTkButton` | Dán proxy, nút "Kiểm tra Proxy" |
| **Threading Controls** | `CTkSlider` (1-10) | Chọn số luồng đồng thời |
| **Grid Layout** | `CTkOptionMenu` | Tự động / 2x2 / 2x3 / 3x3 / Headless |
| **Start/Pause/Stop** | `CTkButton` (3 nút) | Điều khiển tiến trình |

#### Tab 2: Trực quan hóa & Giám sát

| Thành phần | Widget | Mô tả |
|---|---|---|
| **Data Table** | `CTkTable` (hoặc tự build) | Hàng chờ, Đang chạy, Thành công, Lỗi |
| **Live Console Log** | `CTkTextbox` (readonly) | Log màu: Xanh=OK, Đỏ=Lỗi, Vàng=Warning |

#### Tab 3: Cấu hình nâng cao

| Thành phần | Mô tả |
|---|---|
| **Selectors** | CSS/XPath cho ô Họ tên, Email, Nút Đăng ký |
| **Captcha API** | Chọn provider (2Captcha, CapSolver...) + API key |
| **OTP/Email** | IMAP config hoặc Temp Mail API |
| **Retry Policy** | Số lần retry, delay giữa các lần |

---

### Bước 5: Các tính năng mở rộng

#### 5.1. Tự động giải Captcha

**File:** `extensions/captcha.py`

```python
import httpx

class CaptchaSolver:
    def __init__(self, provider: str, api_key: str):
        self.provider = provider
        self.api_key = api_key
    
    def solve_recaptcha_v2(self, site_key: str, page_url: str) -> str:
        """Giải reCAPTCHA v2. Trả về token."""
        if self.provider == "2captcha":
            return self._solve_2captcha(site_key, page_url)
        elif self.provider == "capsolver":
            return self._solve_capsolver(site_key, page_url)
        raise NotImplementedError(f"Provider {self.provider} chưa hỗ trợ")
    
    def _solve_2captcha(self, site_key: str, page_url: str) -> str:
        # Step 1: Submit task
        resp = httpx.post("http://2captcha.com/in.php", data={
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "json": 1,
        })
        task_id = resp.json()["request"]
        
        # Step 2: Poll for result
        for _ in range(60):  # Max 5 phút
            time.sleep(5)
            result = httpx.get("http://2captcha.com/res.php", params={
                "key": self.api_key,
                "action": "get",
                "id": task_id,
                "json": 1,
            }).json()
            if result["status"] == 1:
                return result["request"]
        raise TimeoutError("Captcha solving timeout")
```

#### 5.2. Nhận mã OTP / Kích hoạt Email

**File:** `extensions/email_reader.py`

```python
import imaplib
import email
import re
import time

class EmailOTPReader:
    def __init__(self, email: str, password: str, imap_host: str = "imap.gmail.com"):
        self.email = email
        self.password = password
        self.imap_host = imap_host
    
    def get_latest_otp(self, timeout: int = 120, pattern: str = r"\b\d{6}\b") -> str:
        """Đọc email mới nhất, tìm mã OTP 6 số."""
        start = time.time()
        while time.time() - start < timeout:
            mail = imaplib.IMAP4_SSL(self.imap_host)
            mail.login(self.email, self.password)
            mail.select("inbox")
            
            _, data = mail.search(None, "UNSEEN")
            mail_ids = data[0].split()
            
            if mail_ids:
                # Đọc email mới nhất
                latest_id = mail_ids[-1]
                _, msg_data = mail.fetch(latest_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = msg.get_payload(decode=True).decode()
                
                match = re.search(pattern, body)
                if match:
                    return match.group()
            
            mail.logout()
            time.sleep(5)
        
        raise TimeoutError("Không nhận được OTP trong thời gian chờ")
```

#### 5.3. Cơ chế Retry thông minh

**File:** `core/dispatcher.py`

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

class Dispatcher:
    def __init__(self, max_workers: int = 5, max_retries: int = 3):
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.logger = logging.getLogger("Dispatcher")
    
    def run_batch(self, jobs: list[dict], gpm: GPMManager):
        """
        jobs: [{"account": {...}, "proxy": "...", "profile_id": int}, ...]
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_job = {}
            
            for job in jobs:
                future = executor.submit(self._process_job, job, gpm)
                future_to_job[future] = job
            
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Job failed: {e}")
                    # Retry logic
                    if job.get("retry_count", 0) < self.max_retries:
                        job["retry_count"] = job.get("retry_count", 0) + 1
                        # Đổi proxy mới nếu có
                        if job.get("backup_proxies"):
                            job["proxy"] = job["backup_proxies"].pop(0)
                        future = executor.submit(self._process_job, job, gpm)
                        future_to_job[future] = job
                    else:
                        results.append({"account": job["account"], "status": "failed", "error": str(e)})
        
        return results
    
    def _process_job(self, job: dict, gpm: GPMManager) -> dict:
        """Xử lý 1 job: start browser → navigate → fill form → submit → stop browser."""
        profile_id = job["profile_id"]
        
        # 1. Start browser
        browser_info = gpm.start_browser(profile_id, headless=job.get("headless", False))
        
        # 2. Move window to grid position
        if not job.get("headless"):
            move_browser_window(browser_info["pid"], **job["grid_cell"])
        
        # 3. Connect Playwright CDP và fill form
        page = connect_to_gpm_browser(browser_info["cdp_url"]).new_page()
        page.goto(job["url"])
        
        # Fill form với selectors từ config
        type_like_human(page, job["selectors"]["name"], job["account"]["name"])
        type_like_human(page, job["selectors"]["email"], job["account"]["email"])
        type_like_human(page, job["selectors"]["password"], job["account"]["password"])
        
        random_pause_before_submit()
        page.click(job["selectors"]["submit"])
        
        # 4. Check result
        time.sleep(3)
        success = page.locator(job["selectors"]["success_indicator"]).count() > 0
        
        # 5. Cleanup
        gpm.stop_browser(browser_info["id"])
        
        return {
            "account": job["account"],
            "status": "success" if success else "failed",
            "timestamp": datetime.now().isoformat(),
        }
```

#### 5.4. Export báo cáo kết quả

**File:** `core/reporter.py`

```python
import pandas as pd

def export_results(results: list[dict], output_dir: str = "results/"):
    """Xuất file success_accounts.xlsx và failed_accounts.xlsx."""
    df = pd.DataFrame(results)
    success_df = df[df["status"] == "success"]
    failed_df = df[df["status"] == "failed"]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    success_df.to_excel(f"{output_dir}/success_{timestamp}.xlsx", index=False)
    failed_df.to_excel(f"{output_dir}/failed_{timestamp}.xlsx", index=False)
```

#### 5.5. Tích hợp GPM Login API (thực tế port 9495)

GPM Login cung cấp local API server (mặc định `http://localhost:9495`). Dưới đây là mapping endpoints chính xác (cần verify lại qua Swagger UI tại `http://localhost:9495/docs` khi ứng dụng đang chạy):

**Endpoints chính:**

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/v3/profiles` | Liệt kè profiles (có pagination) |
| `POST` | `/api/v3/profiles/create` | Tạo profile mới (name, group_id, proxy, fingerprint) |
| `GET` | `/api/v3/profiles/{id}` | Chi tiết profile |
| `PUT` | `/api/v3/profiles/{id}` | Cập nhật proxy/UA/fingerprint |
| `DELETE` | `/api/v3/profiles/{id}` | Xóa profile |
| `POST` | `/api/v3/profiles/start` | Khởi động browser (params: profile_id, headless, auto_close) |
| `POST` | `/api/v3/browser/{browser_id}/stop` | Dừng browser |
| `GET` | `/api/v3/browser/{browser_id}/status` | Trạng thái browser (PID, CDP port) |

**Ví dụ tạo profile qua API:**

```python
import httpx

GPM_BASE = "http://localhost:9495"

def create_profile_with_proxy(name: str, proxy: dict) -> dict:
    """Tạo profile mới kèm proxy. Trả về profile_id."""
    resp = httpx.post(f"{GPM_BASE}/api/v3/profiles/create", json={
        "name": name,
        "group_id": "default",
        "proxy": {
            "type": "http",          # hoặc "socks5"
            "host": proxy["host"],
            "port": proxy["port"],
            "username": proxy.get("user"),
            "password": proxy.get("pass"),
        },
    }, timeout=30)
    return resp.json()  # {"id": 123, ...}

def start_browser(profile_id: int) -> dict:
    """Mở browser, trả về {browser_id, pid, cdp_port}."""
    resp = httpx.post(
        f"{GPM_BASE}/api/v3/profiles/start",
        params={"profile_id": profile_id, "headless": "false"},
        timeout=60
    )
    return resp.json()
```

**Lưu ý quan trọng:**
- GPM Login tự quản lý fingerprint (Canvas, WebGL, AudioContext...) — KHÔNG cần fake thủ công
- Profile có thể được gán proxy sẵn khi tạo hoặc cập nhật sau
- Browser của GPM Login expose CDP endpoint → dùng Playwright `connect_over_cdp()` để tương tác

#### 5.6. Tạo tài khoản hàng loạt qua GPM Login API

Khi không cần tương tác UI form (API-based registration), có thể tạo profile + gán proxy + start/stop hàng loạt:

```python
def batch_create_profiles(accounts: list[dict], proxies: list[str]) -> list[int]:
    """
    Tạo N profiles, mỗi profile gán 1 proxy riêng.
    Trả về list profile_ids.
    """
    profile_ids = []
    for i, (acc, proxy) in enumerate(zip(accounts, proxies)):
        proxy_info = parse_proxy(proxy) if proxy else None
        profile = create_profile_with_proxy(f"auto_acc_{i}", proxy_info)
        profile_ids.append(profile["id"])
    return profile_ids
```

Hoặc dùng sẵn profiles có sẵn trong GPM Login (tạo tay qua UI của GPM Login):

```python
def list_available_profiles() -> list[dict]:
    """Lấy tấ cả profiles hiện có trong GPM Login."""
    resp = httpx.get(f"{GPM_BASE}/api/v3/profiles", params={"page": 1, "size": 100})
    return resp.json()["items"]
```

#### 5.7. Cấu hình Selector linh hoạt

**File:** `config/selectors.json`

```json
{
  "default": {
    "name": "input[name='fullname']",
    "email": "input[name='email']",
    "password": "input[name='password']",
    "submit": "button[type='submit']",
    "success_indicator": ".success-message, .alert-success, [data-status='success']",
    "error_indicator": ".error-message, .alert-danger, [data-status='error']"
  },
  "bank_example_com": {
    "name": "#reg-fullname",
    "email": "#reg-email",
    "password": "#reg-password",
    "submit": "#btn-register",
    "success_indicator": ".registration-success"
  }
}
```

**UI cho phép import/export JSON này** để tái sử dụng cho nhiều trang web.

---

## 4. Cấu trúc thư mục dự án

```
RegAcc/
├── main.py                    # Entry point
├── requirements.txt           # Dependencies
├── README.md
├── PLAN.md                    # File này
├── config/
│   ├── selectors.json         # CSS/XPath selectors
│   └── settings.json          # Cấu hình mặc định
├── core/
│   ├── __init__.py
│   ├── grid.py                # Grid calculator
│   ├── gpm_manager.py         # GPM Login API client
│   ├── dispatcher.py          # ThreadPoolExecutor dispatcher
│   ├── human.py               # Human-like delays
│   └── reporter.py            # Export results
├── ui/
│   ├── __init__.py
│   ├── dashboard.py           # Main dashboard
│   ├── widgets.py             # Custom widgets
│   └── styles.py              # Theme/styles
├── extensions/
│   ├── __init__.py
│   ├── captcha.py             # 2Captcha, CapSolver
│   └── email_reader.py        # IMAP OTP reader
├── data/
│   ├── accounts.csv           # Danh sách tài khoản
│   └── proxies.txt            # Danh sách proxy
├── profiles/                  # GPM Login profiles (auto-created)
└── results/                   # Output files
    ├── success_*.xlsx
    └── failed_*.xlsx
```

---

## 5. Dependencies (requirements.txt)

```txt
customtkinter>=5.2.0
pandas>=2.0.0
openpyxl>=3.1.0
httpx>=0.27.0
screeninfo>=0.8.1
pygetwindow>=0.0.9
pywin32>=306
playwright>=1.40.0
```

---

## 6. Timeline triển khai (Gợi ý)

| Phase | Nội dung | Ước lượng |
|---|---|---|
| **Phase 1** | Setup project, GPM Login API integration, Grid calculator | 2-3 ngày |
| **Phase 2** | UI Dashboard (Tab 1 + Tab 2) | 3-4 ngày |
| **Phase 3** | Dispatcher + Worker (form filling, human-like) | 3-4 ngày |
| **Phase 4** | Captcha solving, OTP reader | 2-3 ngày |
| **Phase 5** | Retry logic, Export, Advanced config | 2-3 ngày |
| **Phase 6** | Testing, Bug fixing, Polish UI | 3-4 ngày |
| **Tổng** | | **~15-21 ngày** |

---

## 7. Lưu ý quan trọng

1. **GPM Login API Version:** Kiểm tra lại endpoint thực tế tại `http://localhost:9495/docs` (Swagger UI) khi GPM Login đang chạy.
2. **Proxy Format:** GPM Login có thể yêu cầu format proxy cụ thể. Xem docs để điều chỉnh `parse_proxy()`.
3. **CDP Connection:** Để tương tác với browser của GPM Login, ta kết nối qua CDP (Chrome DevTools Protocol) thay vì tự khởi tạo browser mới.
4. **Legal:** Hãy đảm bảo tuân thủ Điều khoản dịch vụ của trang web đích và pháp luật hiện hành khi sử dụng công cụ tự động hóa.
5. **Rate Limiting:** Nên giới hạn số luồng tối đa để tránh nhận diện bởi hệ thống chống bot của trang đích.

---

*Document created: 2026-09-27*  
*Last updated: 2026-09-27*
