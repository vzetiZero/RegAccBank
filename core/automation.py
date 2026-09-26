"""
Automation - Điền form đăng ký, bấm submit và xử lý popup quảng cáo.
Thao tác trên Playwright page (kết nối CDP tới browser của GPM Login).
"""

import logging
import random
import time
from typing import Callable, Optional

from core.human import type_like_human, random_pause_before_submit, random_scroll

logger = logging.getLogger(__name__)

# Trạng thái kết quả đăng ký
STATUS_SUCCESS = "success"
STATUS_EXISTS = "exists"
STATUS_FAILED = "failed"

# Menu trên trang /home/mine sau khi đăng ký thành công
MINE_MENU_SELECTOR = 'span.mine-menulist-label:has-text("Quản Lý Rút Tiền")'

# Trang xác minh bảo mật (thiết lập PIN rút tiền)
WITHDRAW_PASS_SELECTOR = 'section[data-item-name="withdrawPass"]'
CONFIRM_WITHDRAW_PASS_SELECTOR = 'section[data-item-name="confirmWithdrawPass"]'
NUMBER_KEYBOARD_SELECTOR = "div.ui-number-keyboard"
NUMBER_KEY_CLASS = "div.ui-number-keyboard-key"

# Trang rút tiền - ô "Thêm Vào" tài khoản ngân hàng
ADD_ACCOUNT_SELECTOR = "#addAccountClick"

# Dialog "Thêm Vào" - nhập lại mật khẩu rút tiền
WITHDRAW_DIALOG_PASSWORD_SELECTOR = 'div.ui-dialog__content section[data-item-name="password"]'

# Form ngân hàng: ô search + danh sách option + nút Xác Nhận
BANK_SEARCH_SELECTOR = 'input[placeholder="Chọn ngân hàng phát hành"]'
BANK_OPTION_SELECTOR = "div.ui-options__option"
BANK_OPTION_TEXT_SELECTOR = "div.ui-options__option span.ui-options__option-content span"
BANK_CONFIRM_SELECTOR = "#bindWithdrawAccountNextClick"

# Selectors cố định cho form đăng ký (không cấu hình qua file nữa)
DEFAULT_SELECTORS = {
    "account": "input[data-input-name='account']",
    "password": "input[data-input-name='userpass']",
    "confirm_password": "input[data-input-name='confirmPassword']",
    "real_name": "input[data-input-name='realName']",
    "submit": "#insideRegisterSubmitClick",
    "popup_close": "",
    "success_indicator": 'span:has-text("Đăng ký Thành công!")',
    "already_exists_indicator": 'div.ui-dialog__message:has-text("Tên tài khoản đã tồn tại")',
}

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

    def __init__(
        self,
        selectors: Optional[dict],
        url: str,
        success_url: Optional[str] = None,
        withdraw_pin: Optional[str] = None,
        withdraw_url: Optional[str] = None,
        bank_mode: str = "csv",
        log: Optional[Callable] = None,
    ):
        self.selectors = {**DEFAULT_SELECTORS, **(selectors or {})}
        self.url = url
        self.success_url = success_url
        self.withdraw_pin = withdraw_pin
        self.withdraw_url = withdraw_url
        self.bank_mode = (bank_mode or "csv").lower()   # "random" | "csv"
        self.last_bank = ""
        self.log = log or (lambda m, level="info": logger.info(m))

    # ---------- navigation ----------
    def navigate(self, page, timeout: int = 60000):
        page.goto(self.url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(2500)
        self.log(f"Đã truy cập {self.url[:70]}", "info")

    def goto_success_url(self, page, timeout: int = 60000):
        """Truy cập trang sau khi đăng ký thành công (VD: /home/mine)."""
        if not self.success_url:
            return
        try:
            page.goto(self.success_url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(1500)
            self.log(f"Đã truy cập trang sau đăng ký: {self.success_url[:70]}", "info")
        except Exception as e:
            self.log(f"Không truy cập được trang sau đăng ký: {e}", "warning")

    def click_mine_menu(self, page, timeout: int = 20000) -> bool:
        """
        Trên trang /home/mine: chờ và bấm menu 'Quản Lý Rút Tiền'.
        Trả về True nếu bấm được.
        """
        try:
            loc = page.locator(MINE_MENU_SELECTOR).first
            loc.wait_for(state="visible", timeout=timeout)
            page.wait_for_timeout(800)
            if not self._try_click(loc):
                self.log("Không bấm được menu 'Quản Lý Rút Tiền'", "error")
                return False
            self.log("Đã bấm menu 'Quản Lý Rút Tiền'", "success")
            page.wait_for_timeout(2000)
            return True
        except Exception as e:
            self.log(f"Không thấy menu 'Quản Lý Rút Tiền': {e}", "warning")
            return False

    # ---------- PIN rút tiền (bàn phím số ảo) ----------
    def _click_keypad_digit(self, page, digit: str) -> bool:
        """Bấm 1 phím số trên bàn phím số ảo (không dùng bàn phím thật)."""
        sel = f'div.ui-number-keyboard:visible {NUMBER_KEY_CLASS}:text-is("{digit}")'
        js = """(digit) => {
            const kbs = Array.from(document.querySelectorAll('div.ui-number-keyboard'));
            const kb = kbs.find(k => k.offsetWidth > 0 && getComputedStyle(k).display !== 'none');
            if (!kb) return false;
            for (const k of kb.querySelectorAll('div.ui-number-keyboard-key')) {
                if ((k.textContent || '').trim() === digit) { k.click(); return true; }
            }
            return false;
        }"""
        for _ in range(3):
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and self._try_click(loc):
                    page.wait_for_timeout(120)
                    return True
            except Exception:
                pass
            try:
                if page.evaluate(js, digit):
                    page.wait_for_timeout(120)
                    return True
            except Exception:
                pass
            page.wait_for_timeout(250)
        return False

    def _open_keyboard(self, page, field_selector: str, timeout: int = 8000) -> bool:
        """
        Mở bàn phím số cho field. Chỉ click khi bàn phím CHƯA hiện
        (click khi đang hiện có thể làm bàn phím bị đóng).
        """
        if self._is_visible(page, NUMBER_KEYBOARD_SELECTOR):
            return True
        for _ in range(3):
            try:
                page.locator(f"{field_selector} .ui-password-input").first.click(timeout=3000)
            except Exception:
                try:
                    page.locator(field_selector).first.click(timeout=3000)
                except Exception:
                    pass
            page.wait_for_timeout(700)
            if self._is_visible(page, NUMBER_KEYBOARD_SELECTOR):
                return True
        return False

    def _pin_filled_count(self, page, field_selector: str) -> int:
        """Đếm số ký tự đã nhập của 1 ô PIN (số <i> đang hiển thị)."""
        try:
            return int(page.eval_on_selector(
                field_selector,
                "el => { let n=0; el.querySelectorAll('li i').forEach(i => { "
                "if (getComputedStyle(i).visibility !== 'hidden') n++; }); return n; }",
            ))
        except Exception:
            return -1

    def _click_button_by_text(self, page, text: str) -> bool:
        """Bấm nút theo text (duyệt từ cuối lên, chọn nút đang hiển thị)."""
        locs = page.locator(f'button:has-text("{text}")')
        for i in range(locs.count() - 1, -1, -1):
            el = locs.nth(i)
            try:
                if el.is_visible() and self._try_click(el):
                    return True
            except Exception:
                continue
        return False

    def setup_withdraw_pass(self, page) -> bool:
        """
        Thiết lập PIN rút tiền bằng bàn phím số ảo.

        Ô 1 đủ 6 số sẽ tự chuyển sang ô 2, nên chỉ cần bấm LIÊN TIẾP
        PIN hai lần (VD: 201198201198). Bấm chậm sẽ làm bàn phím ảo tự ẩn.
        """
        pin = str(self.withdraw_pin or "")
        if not pin:
            self.log("Chưa cấu hình PIN rút tiền — bỏ qua thiết lập PIN", "warning")
            return False

        if not self._open_keyboard(page, WITHDRAW_PASS_SELECTOR):
            self.log("Không mở được bàn phím số cho ô PIN", "error")
            return False

        page.wait_for_timeout(300)
        # Ô 1 đủ 6 số tự chuyển sang ô 2 -> bấm liên tiếp 2 lần PIN
        for ch in pin + pin:
            self._click_keypad_digit(page, ch)
        page.wait_for_timeout(500)

        w = self._pin_filled_count(page, WITHDRAW_PASS_SELECTOR)
        # Fallback: nếu ô 1 chưa đủ (bàn phím bị đóng), mở lại và nhập nốt
        if w < 6:
            if self._open_keyboard(page, WITHDRAW_PASS_SELECTOR):
                for ch in pin[max(w, 0):6]:
                    self._click_keypad_digit(page, ch)
                page.wait_for_timeout(400)
                w = self._pin_filled_count(page, WITHDRAW_PASS_SELECTOR)

        c = self._pin_filled_count(page, CONFIRM_WITHDRAW_PASS_SELECTOR)
        # Fallback: bấm vào ô 2 để mở lại bàn phím rồi nhập nốt
        if c < 6:
            if self._open_keyboard(page, CONFIRM_WITHDRAW_PASS_SELECTOR):
                for ch in pin[max(c, 0):6]:
                    self._click_keypad_digit(page, ch)
                page.wait_for_timeout(400)
                c = self._pin_filled_count(page, CONFIRM_WITHDRAW_PASS_SELECTOR)

        self.log(f"PIN đã nhập: ô 1 = {w}/6, ô 2 = {c}/6", "info")
        if w < 6 or c < 6:
            self.log("Chưa nhập đủ PIN ở cả 2 ô — dừng, không bấm Xác Nhận", "error")
            return False

        if not self._click_button_by_text(page, "Xác Nhận"):
            self.log("Không bấm được nút 'Xác Nhận'", "error")
            return False

        page.wait_for_timeout(2500)
        self.log(f"Đã thiết lập PIN rút tiền và bấm 'Xác Nhận' (URL: {page.url[:80]})", "success")
        return True

    def goto_withdraw_url(self, page, timeout: int = 60000):
        """Truy cập trang rút tiền."""
        if not self.withdraw_url:
            return
        try:
            page.goto(self.withdraw_url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(2000)
            self.log(f"Đã truy cập trang rút tiền: {self.withdraw_url[:70]}", "info")
        except Exception as e:
            self.log(f"Không truy cập được trang rút tiền: {e}", "warning")

    def add_bank_account(self, page, timeout: int = 20000) -> bool:
        """Trên trang rút tiền: bấm ô 'Thêm Vào' để thêm tài khoản ngân hàng."""
        try:
            loc = page.locator(ADD_ACCOUNT_SELECTOR).first
            loc.wait_for(state="visible", timeout=timeout)
            page.wait_for_timeout(600)
            if not self._try_click(loc):
                self.log("Không bấm được 'Thêm Vào' tài khoản ngân hàng", "error")
                return False
            self.log("Đã bấm 'Thêm Vào' tài khoản ngân hàng", "success")
            page.wait_for_timeout(2000)
            return True
        except Exception as e:
            self.log(f"Không thấy ô thêm tài khoản ngân hàng: {e}", "warning")
            return False

    def confirm_withdraw_password(self, page, timeout: int = 15000) -> bool:
        """
        Dialog 'Thêm Vào' yêu cầu nhập lại mật khẩu rút tiền (bàn phím ảo),
        sau đó bấm 'Tiếp Theo'.
        """
        pin = str(self.withdraw_pin or "")
        if not pin:
            return False
        try:
            page.locator(WITHDRAW_DIALOG_PASSWORD_SELECTOR).first.wait_for(
                state="visible", timeout=timeout
            )
        except Exception as e:
            self.log(f"Không thấy ô mật khẩu rút tiền trong dialog: {e}", "warning")
            return False

        if not self._open_keyboard(page, WITHDRAW_DIALOG_PASSWORD_SELECTOR):
            self.log("Không mở được bàn phím số cho dialog mật khẩu", "error")
            return False

        page.wait_for_timeout(300)
        for ch in pin:
            self._click_keypad_digit(page, ch)
        page.wait_for_timeout(500)

        filled = self._pin_filled_count(page, WITHDRAW_DIALOG_PASSWORD_SELECTOR)
        if filled < 6:
            self.log(f"Dialog mật khẩu mới nhập {filled}/6", "error")
            return False
        self.log("Đã nhập mật khẩu rút tiền trong dialog", "success")

        if not self._click_button_by_text(page, "Tiếp Theo"):
            self.log("Không bấm được nút 'Tiếp Theo'", "error")
            return False
        page.wait_for_timeout(2500)
        self.log(f"Đã bấm 'Tiếp Theo' (URL: {page.url[:80]})", "success")
        return True

    def fill_bank_account_number(self, page, stk: str, timeout: int = 15000) -> bool:
        """
        Form thêm tài khoản ngân hàng: điền số tài khoản (lấy từ cột 'stk').

        LƯU Ý: chưa chọn ngân hàng phát hành và chưa bấm 'Xác Nhận'
        (đang chờ hoàn thiện - xem PROGRESS.md).
        """
        if not stk:
            self.log("Thiếu số tài khoản (cột stk) — bỏ qua bước điền số tài khoản ngân hàng", "warning")
            return False

        candidates = [
            'input[placeholder="Vui lòng nhập số tài khoản ngân hàng"]',
            "input.ui-input__input",
        ]
        for c in candidates:
            if not c:
                continue
            try:
                loc = page.locator(c).first
                loc.wait_for(state="visible", timeout=timeout)
                loc.click(timeout=3000)
                loc.fill(str(stk))
                self.log(f"Đã điền số tài khoản ngân hàng: {stk}", "success")
                page.wait_for_timeout(500)
                return True
            except Exception:
                continue

        self.log("Không điền được số tài khoản ngân hàng", "warning")
        return False

    # ---------- ngân hàng ----------
    def _open_bank_dropdown(self, page, timeout: int = 10000):
        loc = page.locator(BANK_SEARCH_SELECTOR).first
        loc.wait_for(state="visible", timeout=timeout)
        loc.click(timeout=3000)
        page.wait_for_timeout(600)

    def list_banks(self, page) -> list:
        """Đọc danh sách ngân hàng từ dropdown."""
        try:
            self._open_bank_dropdown(page)
            texts = page.locator(BANK_OPTION_TEXT_SELECTOR).all_inner_texts()
            names = []
            for t in texts:
                t = (t or "").strip()
                if t and t not in names:
                    names.append(t)
            return names
        except Exception as e:
            self.log(f"Không lấy được danh sách ngân hàng: {e}", "warning")
            return []

    def select_bank(self, page, bank_name: str) -> bool:
        """Gõ tên ngân hàng và chọn option khớp trong dropdown."""
        bank_name = str(bank_name or "").strip()
        if not bank_name:
            return False
        try:
            inp = page.locator(BANK_SEARCH_SELECTOR).first
            inp.wait_for(state="visible", timeout=10000)
            inp.click(timeout=3000)
            page.wait_for_timeout(300)
            inp.fill("")
            inp.type(bank_name, delay=60)
            page.wait_for_timeout(900)

            opts = page.locator(BANK_OPTION_SELECTOR)
            n = opts.count()
            target = None
            for i in range(n):
                el = opts.nth(i)
                try:
                    txt = (el.inner_text() or "").strip()
                except Exception:
                    continue
                if txt and bank_name.lower() in txt.lower():
                    target = el
                    break
            if target is None:
                if n == 0:
                    self.log(f"Không tìm thấy ngân hàng '{bank_name}'", "error")
                    return False
                target = opts.first

            if not self._try_click(target):
                self.log(f"Không chọn được ngân hàng '{bank_name}'", "error")
                return False
            self.log(f"Đã chọn ngân hàng: {bank_name}", "success")
            page.wait_for_timeout(500)
            return True
        except Exception as e:
            self.log(f"Lỗi chọn ngân hàng: {e}", "warning")
            return False

    def choose_and_select_bank(self, page, account: dict) -> str:
        """
        Chọn ngân hàng theo chế độ:
            random -> lấy ngẫu nhiên trong danh sách
            csv    -> lấy cột 'bank' của tài khoản; nếu trống thì lấy ngẫu nhiên
        Trả về tên ngân hàng đã chọn (để ghi lại vào CSV).
        """
        name = ""
        if self.bank_mode == "random":
            banks = self.list_banks(page)
            if not banks:
                self.log("Không có danh sách ngân hàng để chọn ngẫu nhiên", "warning")
                return ""
            name = random.choice(banks)
        else:
            name = str(account.get("bank") or "").strip()
            if not name:
                banks = self.list_banks(page)
                if not banks:
                    self.log("CSV chưa có bank và không lấy được danh sách ngân hàng", "warning")
                    return ""
                name = random.choice(banks)
                self.log(f"CSV chưa có bank — chọn ngẫu nhiên: {name}", "info")

        if self.select_bank(page, name):
            self.last_bank = name
            return name
        return ""

    def bind_bank_account(self, page, timeout: int = 10000) -> bool:
        """Bấm 'Xác Nhận' (#bindWithdrawAccountNextClick) để lưu tài khoản ngân hàng."""
        try:
            loc = page.locator(BANK_CONFIRM_SELECTOR).first
            loc.wait_for(state="visible", timeout=timeout)
            ok = self._try_click(loc) or self._click_button_by_text(page, "Xác Nhận")
            if not ok:
                self.log("Không bấm được nút 'Xác Nhận' form ngân hàng", "error")
                return False
            self.log("Đã bấm 'Xác Nhận' lưu tài khoản ngân hàng", "success")
            page.wait_for_timeout(2500)
            return True
        except Exception as e:
            self.log(f"Không bấm được 'Xác Nhận' form ngân hàng: {e}", "warning")
            return False

    # ---------- form ----------
    def fill_form(self, page, account: dict) -> int:
        """
        Điền 4 trường theo form:
            account          <- CSV 'taikhoan'   (dict key: account)
            password         <- CSV 'matkhau'    (dict key: password)
            confirm_password <- CSV 'matkhau'
            real_name        <- CSV 'Tên tài khoản' (dict key: name)
        Trả về số trường điền thành công.
        """
        s = self.selectors
        fields = [
            ("account", s.get("account"), account.get("account")),
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
        """
        Bấm nút Đăng ký.

        Ưu tiên id thật của nút (#insideRegisterSubmitClick), rồi tới các
        selector dự phòng. Mỗi ứng viên thử lần lượt 3 cách:
            1. click thường (qua kiểm tra actionability)
            2. click force (bỏ qua actionability)
            3. kích hoạt click bằng JS (el.click())
        Trả về True nếu đã bấm được nút.
        """
        candidates = [
            self.selectors.get("submit"),
            "#insideRegisterSubmitClick",
            "button:has-text('Đăng Ký')",
            "button:has-text('Đăng ký')",
            "[class*='ui-button']:has-text('Đăng Ký')",
            "[role='button']:has-text('Đăng Ký')",
            "text=Đăng Ký",
        ]
        random_pause_before_submit()
        for c in candidates:
            if not c:
                continue
            try:
                loc = page.locator(c).first
                if loc.count() == 0 or not loc.is_visible():
                    continue

                try:
                    loc.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass

                if self._try_click(loc):
                    self.log(f"Đã bấm Đăng ký (selector: {c})", "success")
                    page.wait_for_timeout(1000)
                    return True
            except Exception:
                continue

        self.log("Không tìm thấy hoặc không bấm được nút Đăng ký", "error")
        return False

    @staticmethod
    def _try_click(loc) -> bool:
        """Thử bấm một locator bằng nhiều cách. True nếu thành công."""
        for method in ("normal", "force", "js"):
            try:
                if method == "normal":
                    loc.click(timeout=5000)
                elif method == "force":
                    loc.click(timeout=5000, force=True)
                else:
                    loc.evaluate("el => el.click()")
                return True
            except Exception:
                continue
        return False

    def _is_visible(self, page, selector: str) -> bool:
        try:
            loc = page.locator(selector).first
            return loc.count() > 0 and loc.is_visible()
        except Exception:
            return False

    def wait_result(self, page, timeout: int = 15000, interval: int = 300) -> str:
        """
        Chờ kết quả sau khi bấm Đăng ký.

        Trả về:
            STATUS_SUCCESS – thấy popup "Đăng ký Thành công!"
            STATUS_EXISTS  – thấy popup "Tên tài khoản đã tồn tại"
            STATUS_FAILED  – không thấy cả hai trong thời gian chờ
        """
        success_sel = self.selectors.get("success_indicator")
        exists_sel = self.selectors.get("already_exists_indicator")
        if not success_sel and not exists_sel:
            self.log("Chưa cấu hình chỉ báo thành công/đã tồn tại — không thể xác nhận", "warning")
            page.wait_for_timeout(3000)
            return STATUS_FAILED

        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            if exists_sel and self._is_visible(page, exists_sel):
                self.log("Tài khoản đã tồn tại trên hệ thống", "warning")
                return STATUS_EXISTS
            if success_sel and self._is_visible(page, success_sel):
                self.log("✔ Phát hiện popup 'Đăng ký Thành công!'", "success")
                return STATUS_SUCCESS
            page.wait_for_timeout(interval)

        self.log("Không thấy popup kết quả (thành công/đã tồn tại) trong thời gian chờ", "error")
        return STATUS_FAILED

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
    def run_register(self, page, account: dict) -> str:
        """
        Chạy toàn bộ: điền form -> submit -> chờ kết quả.

        Trả về STATUS_SUCCESS / STATUS_EXISTS / STATUS_FAILED.
        Chỉ truy cập trang sau đăng ký khi THÀNH CÔNG; nếu tài khoản
        đã tồn tại thì dừng, không thực hiện bước tiếp theo.
        """
        random_scroll(page)
        filled = self.fill_form(page, account)
        if filled == 0:
            self.log("Không điền được trường nào — kiểm tra lại selectors", "error")
            return STATUS_FAILED

        if not self.click_submit(page):
            return STATUS_FAILED

        outcome = self.wait_result(page)
        closed = self.close_popups(page)
        self.log(f"Đã đóng {closed} popup sau khi submit", "info")

        if outcome == STATUS_EXISTS:
            self.log(
                f"Tài khoản đã tồn tại: {account.get('account')} — bỏ qua các bước sau", "warning"
            )
            return STATUS_EXISTS

        if outcome == STATUS_SUCCESS:
            self.goto_success_url(page)
            self.click_mine_menu(page)
            if self.setup_withdraw_pass(page):
                self.goto_withdraw_url(page)
                self.add_bank_account(page)
                self.confirm_withdraw_password(page)
                self.fill_bank_account_number(page, account.get("stk"))
                if self.choose_and_select_bank(page, account):
                    self.bind_bank_account(page)
        return outcome
