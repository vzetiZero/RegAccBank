"""
Automation - Điền form đăng ký, bấm submit và xử lý popup quảng cáo.
Thao tác trên Playwright page (kết nối CDP tới browser của GPM Login).
"""

import logging
from typing import Callable, Optional

from core.human import type_like_human, random_pause_before_submit, random_scroll

logger = logging.getLogger(__name__)

# Các selector thử để đóng popup/quảng cáo (từ chung -> cụ thể)
POPUP_CLOSE_SELECTORS = [
    "[class*='popup'] [class*='close' i]",
    "[class*='modal'] [class*='close' i]",
    "[class*='dialog'] [class*='close' i]",
    "[class*='advert'] [class*='close' i]",
    "[class*='banner'] [class*='close' i]",
    ".ui-popover__close",
    "[class*='close' i]",
    "[aria-label*='close' i]",
    "img[class*='close' i]",
    "i[class*='close' i]",
    "svg[class*='close' i]",
]

# JS quét cấu trúc trang (popup, nút bấm, nút close) để hỗ trợ bắt xpath
DUMP_JS = r"""
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  };
  const cls = (el) => String(el.className || '').slice(0, 140);
  const out = { url: location.href, popups: [], buttons: [], closes: [], iframes: [] };

  document.querySelectorAll('*').forEach(el => {
    try {
      const st = getComputedStyle(el);
      const z = parseInt(st.zIndex) || 0;
      if ((st.position === 'fixed' || st.position === 'absolute') && z >= 100
          && visible(el) && el.offsetWidth > 80 && el.offsetHeight > 50) {
        if (out.popups.length < 20)
          out.popups.push({ tag: el.tagName, cls: cls(el), z: z, w: el.offsetWidth, h: el.offsetHeight });
      }
    } catch (e) {}
  });

  document.querySelectorAll("button, [role='button'], [class*='btn'], [class*='Button']").forEach(el => {
    if (out.buttons.length < 40 && visible(el)) {
      const t = (el.innerText || el.value || '').trim().slice(0, 40);
      if (t) out.buttons.push({ text: t, cls: cls(el) });
    }
  });

  document.querySelectorAll("[class*='close' i], [aria-label*='close' i]").forEach(el => {
    if (out.closes.length < 20 && visible(el)) out.closes.push({ tag: el.tagName, cls: cls(el) });
  });

  document.querySelectorAll('iframe').forEach(el => {
    if (out.iframes.length < 10 && visible(el)) out.iframes.push({ src: (el.src || '').slice(0, 120), cls: cls(el) });
  });

  return out;
}
"""


class RegisterAutomation:
    """Điền form đăng ký và xử lý popup trên một Playwright page."""

    def __init__(self, selectors: Optional[dict], url: str, log: Optional[Callable] = None):
        self.selectors = selectors or {}
        self.url = url
        self.log = log or (lambda m, level="info": logger.info(m))

    # ---------- navigation ----------
    def navigate(self, page, timeout: int = 60000):
        page.goto(self.url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(2500)
        self.log(f"Đã truy cập {self.url[:70]}", "info")

    # ---------- form ----------
    def fill_form(self, page, account: dict) -> int:
        """
        Điền 4 trường theo form:
            account          <- CSV 'taikhoan'   (dict key: email)
            password         <- CSV 'matkhau'    (dict key: password)
            confirm_password <- CSV 'matkhau'
            real_name        <- CSV 'Tên tài khoản' (dict key: name)
        Trả về số trường điền thành công.
        """
        s = self.selectors
        fields = [
            ("account", s.get("account"), account.get("email")),
            ("password", s.get("password"), account.get("password")),
            ("confirm_password", s.get("confirm_password"), account.get("password")),
            ("real_name", s.get("real_name"), account.get("name")),
        ]
        done = 0
        for label, selector, value in fields:
            if not selector:
                self.log(f"Chưa cấu hình selector cho '{label}'", "warning")
                continue
            if value in (None, ""):
                self.log(f"Thiếu dữ liệu cho '{label}'", "warning")
                continue
            try:
                type_like_human(page, selector, str(value))
                done += 1
                masked = "***" if "pass" in label else str(value)
                self.log(f"Đã điền {label} = {masked}", "info")
            except Exception as e:
                self.log(f"Không điền được '{label}' ({selector}): {e}", "error")
        return done

    def click_submit(self, page) -> bool:
        """Bấm nút Đăng ký. Thử nhiều selector dự phòng."""
        candidates = [
            self.selectors.get("submit"),
            "button:has-text('Đăng ký')",
            "[class*='btn']:has-text('Đăng ký')",
            "[role='button']:has-text('Đăng ký')",
            "text=Đăng Ký",
            "text=Đăng ký ngay",
        ]
        random_pause_before_submit()
        for c in candidates:
            if not c:
                continue
            try:
                loc = page.locator(c).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=5000)
                    self.log(f"Đã bấm Đăng ký (selector: {c})", "success")
                    return True
            except Exception:
                continue
        self.log("Không tìm thấy nút Đăng ký", "error")
        return False

    # ---------- popups ----------
    def close_popups(self, page, rounds: int = 4) -> int:
        """
        Đóng popup/quảng cáo. Trả về số popup đã đóng.
        Thử click theo selector + nhấn Escape.
        """
        closed = 0
        for _ in range(rounds):
            acted = False
            # Ưu tiên selector người dùng cấu hình
            selectors = ([self.selectors.get("popup_close")] if self.selectors.get("popup_close") else []) \
                + POPUP_CLOSE_SELECTORS
            for sel in selectors:
                if not sel:
                    continue
                try:
                    locs = page.locator(sel)
                    n = min(locs.count(), 5)
                    for i in range(n):
                        el = locs.nth(i)
                        try:
                            if el.is_visible():
                                el.click(timeout=1500)
                                closed += 1
                                acted = True
                                self.log(f"Đã đóng popup ({sel})", "info")
                        except Exception:
                            continue
                    if acted:
                        break
                except Exception:
                    continue

            # Thử Escape
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

            if not acted:
                break
            page.wait_for_timeout(700)
        return closed

    # ---------- page scan ----------
    def dump(self, page) -> dict:
        """Quét cấu trúc trang để hỗ trợ bắt xpath."""
        try:
            data = page.evaluate(DUMP_JS)
        except Exception as e:
            self.log(f"Không quét được trang: {e}", "error")
            return {}

        self.log(f"URL hiện tại: {data.get('url', '')}", "info")

        popups = data.get("popups", [])
        self.log(f"Phát hiện {len(popups)} popup/overlay:", "info")
        for p in popups:
            self.log(f"  • <{p['tag']}> z={p['z']} {p['w']}x{p['h']} class=\"{p['cls']}\"", "warning")

        closes = data.get("closes", [])
        self.log(f"Nút close khả dụng ({len(closes)}):", "info")
        for c in closes:
            self.log(f"  • <{c['tag']}> class=\"{c['cls']}\"", "info")

        buttons = data.get("buttons", [])
        self.log(f"Nút bấm trên trang ({len(buttons)}):", "info")
        for b in buttons:
            self.log(f"  • \"{b['text']}\" class=\"{b['cls']}\"", "info")

        iframes = data.get("iframes", [])
        if iframes:
            self.log(f"iframe ({len(iframes)}):", "info")
            for f in iframes:
                self.log(f"  • src=\"{f['src']}\"", "info")

        return data

    # ---------- full register flow ----------
    def run_register(self, page, account: dict) -> bool:
        """Chạy toàn bộ: navigate -> điền form -> submit -> đóng popup."""
        random_scroll(page)
        filled = self.fill_form(page, account)
        if filled == 0:
            self.log("Không điền được trường nào — kiểm tra lại selectors", "error")
            return False

        ok = self.click_submit(page)
        page.wait_for_timeout(4000)
        closed = self.close_popups(page)
        self.log(f"Đã đóng {closed} popup sau khi submit", "info")
        return ok
